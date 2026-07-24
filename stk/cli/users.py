"""User, role, and session commands."""

import secrets
import string
from datetime import datetime

import click
from quart_security import hash_password
from sqlalchemy import select

import stk.extensions as ext
from stk.agent_login import create_agent_login_token
from stk.cli.base import console, run_async
from stk.user.models import User


@click.group("browser-token")
def browser_token():
    """Create test-only browser login URLs."""


@browser_token.command("create")
@click.option("--user", "email", required=True, help="Test user email.")
@click.option("--ttl", default=60, type=int, help="Token TTL in seconds.")
@click.option("--next", "next_path", default="/dashboard/", help="Local redirect path.")
def browser_token_create(email, ttl, next_path):
    """Create a signed test-only browser login URL."""
    from stk.app import create_app

    app = create_app()
    if ttl > app.config["STK_AGENT_LOGIN_MAX_TTL_SECONDS"]:
        raise click.ClickException("ttl exceeds STK_AGENT_LOGIN_MAX_TTL_SECONDS")
    if not app.config["STK_ENABLE_AGENT_LOGIN"]:
        raise click.ClickException("agent login is disabled")

    async def _create_token():
        async with app.app_context():
            return create_agent_login_token(email, next_path)

    token = run_async(_create_token())
    click.echo(f"/_test/login?token={token}")


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
                confirmed_at=datetime.now(),
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
                user = User(
                    email=email,
                    password=hash_password(password),
                    active=True,
                    confirmed_at=datetime.now(),
                )
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


@click.command("cleanup-sessions")
def cleanup_sessions():
    """Deactivate expired sessions and delete old rows."""
    from stk.tasks import cleanup_expired_sessions

    run_async(cleanup_expired_sessions())
    console.print("[green]Session cleanup complete[/]")
