"""Durable jobs: enqueue, claim, retry, failure, and recovery of a dead worker's job."""

import asyncio
import unittest
from datetime import datetime, timedelta

import orjson
from quart import g
from sqlalchemy import select, update

import stk.extensions as ext
from stk.app import Stk
from stk.settings import TestingConfig
from stk.tasks import enqueue, job, recover, run_next
from stk.tasks.models import Job
from stk.user.models import Activity, Base, User
from stk.user.views import api_jobs

calls = []


@job
async def jobs_test_record(session, user_id, action):
    session.add(Activity(user_id=user_id, action=action))
    calls.append(action)


@job
async def jobs_test_explode(session, user_id):
    session.add(Activity(user_id=user_id, action="never committed"))
    raise RuntimeError("boom")


@job
async def jobs_test_slow(session):
    await asyncio.sleep(5)


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        calls.clear()
        self.app = Stk(__name__, config=TestingConfig)
        async with ext.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            user = User(email="jobs@example.com", password="x", active=True)
            db.add(user)
            await db.commit()
            self.user_id = user.id

    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def get(self, job_id):
        async with ext.async_session_factory() as db:
            return await db.get(Job, job_id)

    async def activities(self):
        async with ext.async_session_factory() as db:
            return list(await db.scalars(select(Activity.action)))

    async def make_due(self, job_id):
        async with ext.async_session_factory() as db:
            await db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(run_after=datetime.now() - timedelta(seconds=1))
            )
            await db.commit()

    async def test_enqueue_rejects_unregistered_name(self):
        with self.assertRaises(ValueError):
            await enqueue("jobs_test_missing")

    async def test_runs_job_and_commits_its_writes(self):
        job_id = await enqueue("jobs_test_record", user_id=self.user_id, action="sent")
        self.assertEqual((await self.get(job_id)).status, "queued")

        self.assertTrue(await run_next())
        self.assertFalse(await run_next())

        row = await self.get(job_id)
        self.assertEqual((row.status, row.attempts, row.locked_at), ("done", 1, None))
        self.assertEqual(calls, ["sent"])
        self.assertIn("sent", await self.activities())

    async def test_claims_in_run_after_order_and_skips_future_jobs(self):
        later = await enqueue("jobs_test_record", user_id=self.user_id, action="b")
        first = await enqueue("jobs_test_record", user_id=self.user_id, action="a")
        async with ext.async_session_factory() as db:
            await db.execute(
                update(Job)
                .where(Job.id == later)
                .values(run_after=datetime.now() + timedelta(hours=1))
            )
            await db.commit()

        self.assertTrue(await run_next())
        self.assertFalse(await run_next())
        self.assertEqual(calls, ["a"])
        self.assertEqual((await self.get(first)).status, "done")
        self.assertEqual((await self.get(later)).status, "queued")

    async def test_failure_rolls_back_retries_with_backoff_then_fails(self):
        job_id = await enqueue("jobs_test_explode", user_id=self.user_id)

        with self.assertLogs("stk.tasks", "ERROR"):
            self.assertTrue(await run_next())
        row = await self.get(job_id)
        self.assertEqual((row.status, row.attempts), ("queued", 1))
        self.assertIn("RuntimeError: boom", row.last_error)
        self.assertGreater(row.run_after, datetime.now() + timedelta(seconds=20))
        self.assertFalse(await run_next(), "backoff keeps the retry out of reach")
        self.assertNotIn("never committed", await self.activities())

        for _ in range(2):
            await self.make_due(job_id)
            with self.assertLogs("stk.tasks", "ERROR"):
                self.assertTrue(await run_next())
        row = await self.get(job_id)
        self.assertEqual((row.status, row.attempts), ("failed", 3))
        await self.make_due(job_id)
        self.assertFalse(await run_next(), "a failed job is never claimed again")

    async def test_timeout_cancels_and_records_the_job(self):
        job_id = await enqueue("jobs_test_slow")
        with self.assertLogs("stk.tasks", "ERROR"):
            self.assertTrue(await run_next(timeout=0.05))
        row = await self.get(job_id)
        self.assertEqual(row.status, "queued")
        self.assertIn("TimeoutError", row.last_error)

    async def test_stopping_the_worker_hands_the_job_back(self):
        job_id = await enqueue("jobs_test_slow")
        task = asyncio.create_task(run_next())
        await asyncio.sleep(0.1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        row = await self.get(job_id)
        self.assertEqual((row.status, row.attempts, row.locked_at), ("queued", 0, None))

    async def test_recovers_job_left_running_by_a_dead_worker(self):
        lost = await enqueue("jobs_test_record", user_id=self.user_id, action="lost")
        spent = await enqueue("jobs_test_record", user_id=self.user_id, action="spent")
        alive = await enqueue("jobs_test_record", user_id=self.user_id, action="alive")
        stale = datetime.now() - timedelta(hours=2)
        async with ext.async_session_factory() as db:
            for job_id, attempts, locked_at in [
                (lost, 1, stale),
                (spent, 3, stale),
                (alive, 1, datetime.now()),
            ]:
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(status="running", attempts=attempts, locked_at=locked_at)
                )
            await db.commit()

        await recover(timeout=3600)

        self.assertEqual((await self.get(lost)).status, "queued")
        self.assertIn("worker lost", (await self.get(lost)).last_error)
        self.assertEqual((await self.get(spent)).status, "failed")
        self.assertEqual((await self.get(alive)).status, "running")
        self.assertTrue(await run_next())
        self.assertEqual(calls, ["lost"])

    async def test_admin_lists_failed_jobs(self):
        failed = await enqueue("jobs_test_record", user_id=self.user_id, action="x")
        await enqueue("jobs_test_record", user_id=self.user_id, action="y")
        async with ext.async_session_factory() as db:
            await db.execute(
                update(Job).where(Job.id == failed).values(status="failed")
            )
            await db.commit()

        anonymous = await self.app.test_client().get("/api/jobs")
        self.assertNotEqual(anonymous.status_code, 200)

        async with self.app.test_request_context("/api/jobs?status=failed"):
            async with ext.async_session_factory() as db:
                g.db_session = db
                response = await api_jobs()
        body = orjson.loads(await response.get_data())
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["id"], failed)


if __name__ == "__main__":
    unittest.main()
