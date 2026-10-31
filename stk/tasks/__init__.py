"""Async background tasks, and durable jobs that survive a restart.

Usage:
    from stk.tasks import enqueue, job, run_in_background

    await run_in_background(send_welcome_email(user_id=123))  # this process only

    @job
    async def send_report(session, user_id): ...

    await enqueue("send_report", user_id=123)  # `stk worker` runs it
"""

import asyncio
import logging
import signal
import traceback
from datetime import datetime, timedelta

from sqlalchemy import select, update

import stk.extensions as ext
from stk.tasks.models import Job

logger = logging.getLogger(__name__)

JOBS = {}
TIMEOUT = 3600
POLL_SECONDS = 2
RECOVER_SECONDS = 60
# A live worker cancels its job at its timeout; the grace covers recording that.
LEASE_GRACE = timedelta(seconds=60)


async def run_in_background(coro):
    """Fire-and-forget async task with error logging.

    Use for work that doesn't need a result: emails, webhooks, cache warming, etc.
    The task runs in the current event loop, no extra processes, no Redis.
    """
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)
    return task


async def run_with_session(coro_factory):
    """Fire-and-forget async task that gets its own DB session.

    coro_factory is an async callable that takes a session argument:
        async def my_task(session):
            await session.execute(...)

        await run_with_session(my_task)
    """
    import stk.extensions as ext

    async def _wrapper():
        async with ext.async_session_factory() as session:
            try:
                await coro_factory(session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return await run_in_background(_wrapper())


def _log_task_exception(task: asyncio.Task):
    if not task.cancelled() and task.exception():
        logger.error(
            "Background task failed: %s", task.exception(), exc_info=task.exception()
        )


async def cleanup_expired_sessions():
    """Deactivate expired sessions and delete very old rows."""
    from datetime import datetime, timedelta

    from sqlalchemy import delete, update

    import stk.extensions as ext
    from stk.user.models import Session

    async with ext.async_session_factory() as session:
        lifetime = 3600
        cutoff = datetime.now() - timedelta(seconds=lifetime)
        delete_cutoff = datetime.now() - timedelta(days=30)

        await session.execute(
            update(Session)
            .where(Session.is_active == True, Session.created_at < cutoff)  # noqa: E712
            .values(is_active=False)
        )
        await session.execute(delete(Session).where(Session.created_at < delete_cutoff))
        await session.commit()
        logger.info("Session cleanup complete")


def job(fn):
    """Register an async `fn(session, **payload)` as a durable job named `fn.__name__`."""
    if fn.__name__ in JOBS:
        raise ValueError(f"job {fn.__name__!r} is already registered")
    JOBS[fn.__name__] = fn
    return fn


async def enqueue(name, **payload):
    """Store a job for `stk worker` and return its id. The payload must be JSON."""
    if name not in JOBS:
        raise ValueError(f"no job named {name!r}: register it with @job")
    async with ext.async_session_factory() as session:
        row = Job(name=name, payload=payload)
        session.add(row)
        await session.commit()
        return row.id


def _owned(job_id, lease):
    """The job, only while this worker's claim on it still stands."""
    return update(Job).where(
        Job.id == job_id, Job.status == "running", Job.locked_until == lease
    )


async def _release(job_id, lease, **values):
    async with ext.async_session_factory() as session:
        await session.execute(_owned(job_id, lease).values(locked_until=None, **values))
        await session.commit()


async def run_next(timeout=TIMEOUT):
    """Claim the next due job and run it; False when none is due.

    The job's writes and its `done` mark commit together. A failure rolls the
    job back, records the traceback, and retries after 30s, 60s, ... until
    `max_attempts`, then leaves it `failed`.
    """
    now = datetime.now()
    lease = now + timedelta(seconds=timeout) + LEASE_GRACE
    due = (
        select(Job.id)
        .where(Job.status == "queued", Job.run_after <= now)
        .order_by(Job.run_after)
        .limit(1)
        # ponytail: SQLite drops FOR UPDATE; its single write lock keeps the claim
        # atomic but serializes workers. Run one worker there, PostgreSQL for more.
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    claim = (
        update(Job)
        .where(Job.id == due)
        .values(status="running", attempts=Job.attempts + 1, locked_until=lease)
        .returning(Job.id, Job.name, Job.payload, Job.attempts, Job.max_attempts)
        .execution_options(synchronize_session=False)
    )
    async with ext.async_session_factory() as session:
        claimed = (await session.execute(claim)).one_or_none()
        await session.commit()
    if claimed is None:
        return False

    job_id, name, payload, attempts, max_attempts = claimed
    async with ext.async_session_factory() as session:
        try:
            async with asyncio.timeout(timeout):
                await JOBS[name](session, **payload)
            done = await session.execute(
                _owned(job_id, lease).values(
                    status="done", locked_until=None, last_error=None
                )
            )
            if done.rowcount != 1:
                # Recovered and handed to another worker meanwhile: its run wins.
                await session.rollback()
                logger.warning("Job %s (%s) lost its claim; discarded", job_id, name)
                return True
            await session.commit()
        except asyncio.CancelledError:
            # Stopped by SIGTERM or Ctrl-C: hand it back without spending an attempt.
            await session.rollback()
            await _release(job_id, lease, status="queued", attempts=attempts - 1)
            raise
        except Exception:
            await session.rollback()
            logger.exception("Job %s (%s) failed", job_id, name)
            retry = attempts < max_attempts
            await _release(
                job_id,
                lease,
                status="queued" if retry else "failed",
                run_after=datetime.now() + timedelta(seconds=30 * 2 ** (attempts - 1)),
                last_error=traceback.format_exc(),
            )
    return True


async def recover():
    """Requeue jobs whose worker died (their lease ran out), or fail them at the cap."""
    stale = (Job.status == "running", Job.locked_until < datetime.now())
    lost = "worker lost: its claim expired before the job finished"
    async with ext.async_session_factory() as session:
        await session.execute(
            update(Job)
            .where(*stale, Job.attempts >= Job.max_attempts)
            .values(status="failed", locked_until=None, last_error=lost)
        )
        await session.execute(
            update(Job)
            .where(*stale)
            .values(status="queued", locked_until=None, last_error=lost)
        )
        await session.commit()


async def work(timeout=TIMEOUT):
    """Run due jobs one at a time until SIGTERM or Ctrl-C."""
    asyncio.get_running_loop().add_signal_handler(
        signal.SIGTERM, asyncio.current_task().cancel
    )
    recovered = None
    while True:
        # Also between jobs, so a queue that never empties still recovers.
        if recovered is None or datetime.now() - recovered >= timedelta(
            seconds=RECOVER_SECONDS
        ):
            await recover()
            recovered = datetime.now()
        if not await run_next(timeout):
            await asyncio.sleep(POLL_SECONDS)
