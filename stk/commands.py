"""Click commands."""

import asyncio
import secrets
import string

import click
from quart_security import hash_password
from rich.console import Console
from sqlalchemy import select

import stk.extensions as ext
from alembic import command
from stk.migrations import build_alembic_config
from stk.user.models import User

console = Console()


def run_async(coro):
    """Run an async function in sync context (for CLI commands)."""

    async def _wrapper():
        try:
            return await coro
        finally:
            if ext.engine:
                await ext.engine.dispose()

    return asyncio.run(_wrapper())


@click.command()
def create_db():
    """Apply all database migrations."""
    command.upgrade(build_alembic_config(), "head")
    console.print("[green]Database migrations applied successfully[/]")


@click.group()
def db():
    """Alembic-backed database migration commands."""


@db.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision):
    """Upgrade the database to a target revision."""
    command.upgrade(build_alembic_config(), revision)


@db.command("downgrade")
@click.argument("revision")
def db_downgrade(revision):
    """Downgrade the database to a target revision."""
    command.downgrade(build_alembic_config(), revision)


@db.command("revision")
@click.option("-m", "--message", required=True, help="Revision message")
@click.option(
    "--autogenerate/--empty",
    default=True,
    help="Autogenerate from model metadata or create an empty revision",
)
def db_revision(message, autogenerate):
    """Create a new migration revision."""
    command.revision(
        build_alembic_config(),
        message=message,
        autogenerate=autogenerate,
    )


@db.command("current")
def db_current():
    """Show the current database revision."""
    command.current(build_alembic_config())


@db.command("history")
def db_history():
    """Show migration history."""
    command.history(build_alembic_config())


@db.command("stamp")
@click.argument("revision", default="head")
def db_stamp(revision):
    """Stamp a database with a revision without running migrations."""
    command.stamp(build_alembic_config(), revision)


@click.command()
@click.option("-e", "--email", default=None, help="Admin email")
@click.option("-p", "--password", default=None, help="Admin password")
def install(email, password):
    """Install a default admin user and add an admin role to it."""

    async def _run():
        from stk.user.models import Role

        async with ext.async_session_factory() as session:
            admin_role = (
                await session.execute(select(Role).where(Role.name == "admin"))
            ).scalar_one_or_none()
            if not admin_role:
                admin_role = Role(name="admin")
                session.add(admin_role)
                await session.commit()

            admin_user = (
                await session.execute(
                    select(User).where(User.roles.any(Role.name == "admin"))
                )
            ).scalar_one_or_none()
            if admin_user:
                console.print(
                    f"[yellow]An admin user already exists:[/] [blue]{admin_user.email}[/]"
                )
                return

            nonlocal email, password
            if not email:
                email = click.prompt("Admin email", default="admin@example.com")

            generated = False
            if not password:
                password = "".join(
                    secrets.choice(string.ascii_letters + string.digits + "@#$%^&*")
                    for _ in range(32)
                )
                generated = True

            user = User(
                email=email,
                name="Super Admin",
                password=hash_password(password),
                active=True,
            )
            user.roles.append(admin_role)
            session.add(user)
            await session.commit()

            console.print("\n[green]✓[/] Admin user created successfully!")
            console.print(f"[blue]Email:[/] {email}")
            if generated:
                console.print(f"[blue]Password:[/] [red]{password}[/]")
                console.print(
                    "\n[yellow]⚠️  Please save this password securely - you will not see it again![/]"
                )

    run_async(_run())


@click.command()
@click.option("-e", "--email", prompt=True, default=None)
@click.option("-p", "--password", prompt=True, default=None)
def create(email, password):
    """Creates a user using an email."""

    async def _run():
        async with ext.async_session_factory() as session:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                console.print("[yellow]User already exists![/]")
            else:
                user = User(email=email, password=hash_password(password), active=True)
                session.add(user)
                await session.commit()

    run_async(_run())


@click.command()
@click.option("-e", "--email", prompt=True, default=None)
@click.option("-r", "--role", prompt=True, default="admin")
def add_role(email, role):
    """Adds a role to the specified user."""

    async def _run():
        from stk.user.models import Role

        async with ext.async_session_factory() as session:
            u = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if u is None:
                console.print("[red]Sorry, this user does not exist![/]")
            else:
                r = (
                    await session.execute(select(Role).where(Role.name == role))
                ).scalar_one_or_none()
                if r is None:
                    console.print("[yellow]Sorry, this role does not exist![/]")
                    answer = click.prompt(
                        "Would you like to create one? Y/N", default="N"
                    )
                    if answer.lower() == "y":
                        r = Role(name=role)
                        try:
                            session.add(r)
                            await session.commit()
                            console.print(
                                "[green]Role created successfully, you may add it now to the user[/]"
                            )
                        except Exception:
                            await session.rollback()
                if r:
                    u.roles.append(r)
                    await session.commit()

    run_async(_run())


@click.command("cleanup-sessions")
def cleanup_sessions():
    """Deactivate expired sessions and delete old rows."""
    from stk.tasks import cleanup_expired_sessions

    run_async(cleanup_expired_sessions())
    console.print("[green]Session cleanup complete[/]")


@click.command()
@click.option("-e", "--email", prompt="Email", default=None)
@click.option("-p", "--password", hide_input=True, prompt=True, default=None)
def reset(email, password):
    """Reset a user password using email"""
    try:
        pwd = hash_password(password)

        async def _run():
            async with ext.async_session_factory() as session:
                u = (
                    await session.execute(select(User).where(User.email == email))
                ).scalar_one_or_none()
                if not u:
                    console.print(f'[red]User with email "{email}" not found.[/]')
                    return

                u.password = pwd
                try:
                    await session.commit()
                    console.print(
                        "[green]User password has been reset successfully.[/]"
                    )
                except Exception:
                    await session.rollback()
                    console.print("[red]Error committing to database.[/]")

        run_async(_run())
    except Exception as e:
        console.print(f"[red]Error resetting user password: {e}[/]")


@click.command()
def migrate():
    """Apply all database migrations (legacy alias for upgrade head)."""
    command.upgrade(build_alembic_config(), "head")


@click.command("migration-status")
def migration_status():
    """Show the current Alembic migration revision."""
    command.current(build_alembic_config())
