import asyncio
import inspect

import click
from quart import Quart, g, render_template, request
from quart_security import Security, SQLAlchemyUserDatastore
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import stk.commands as commands
import stk.extensions as ext
from stk.extensions import session
from stk.portal.views import portal
from stk.public.views import public
from stk.settings import Config
from stk.user.forms import ExtendedRegisterForm, OAuthAwareChangePasswordForm
from stk.user.models import Role, User, WebAuthn
from stk.user.views import bp_user
from stk.websocket import ws_bp


def create_app(config_object=Config):
    app = Quart(__name__)
    app.config.from_object(config_object)

    register_blueprints(app)
    register_extensions(app)
    register_errorhandlers(app)
    register_shellcontext(app)
    register_commands(app, commands)
    return app


def register_extensions(app):
    # Async SQLAlchemy engine + session factory
    ext.engine = create_async_engine(app.config["SQLALCHEMY_DATABASE_URI"])
    ext.async_session_factory = async_sessionmaker(ext.engine, expire_on_commit=False)

    @app.before_request
    async def _open_session():
        g.db_session = ext.async_session_factory()

    @app.after_request
    async def _close_session(response):
        db_session = g.pop("db_session", None)
        if db_session is not None:
            await db_session.close()
        return response

    @app.before_websocket
    async def _open_ws_session():
        g.db_session = ext.async_session_factory()

    @app.after_websocket
    async def _close_ws_session(response):
        db_session = g.pop("db_session", None)
        if db_session is not None:
            await db_session.close()
        return response

    @app.while_serving
    async def _lifespan():
        yield
        # quart-session initializes backend connections in before_serving,
        # but doesn't close them on shutdown. Ensure we always release them
        # so Ctrl+C exits cleanly in dev.
        session_interface = getattr(app, "session_interface", None)
        backend = getattr(session_interface, "backend", None)
        if backend is not None:
            close_method = getattr(backend, "aclose", None) or getattr(
                backend, "close", None
            )
            if close_method is not None:
                try:
                    close_result = close_method()
                    if inspect.isawaitable(close_result):
                        await close_result
                except Exception:
                    app.logger.exception("Error while closing session backend")

            pool = getattr(backend, "connection_pool", None)
            disconnect = getattr(pool, "disconnect", None) if pool else None
            if disconnect is not None:
                try:
                    disconnect_result = disconnect()
                    if inspect.isawaitable(disconnect_result):
                        await disconnect_result
                except Exception:
                    app.logger.exception("Error while disconnecting session pool")

        try:
            await asyncio.wait_for(ext.engine.dispose(), timeout=5)
        except asyncio.TimeoutError:
            app.logger.warning("Timed out while disposing SQLAlchemy engine")

    user_datastore = SQLAlchemyUserDatastore(
        lambda: g.db_session, User, Role, webauthn_model=WebAuthn
    )
    Security(
        app,
        user_datastore,
        register_form=ExtendedRegisterForm,
        change_password_form=OAuthAwareChangePasswordForm,
    )

    # Session initialization
    if app.config.get("SESSION_TYPE") == "redis":
        session.init_app(app)
    # For non-redis, fall back to Quart's built-in cookie sessions

    # Rate limit auth endpoints
    from stk.utils.ratelimit import check_security_rate_limit

    _auth_paths = frozenset({"/login", "/register", "/reset", "/confirm"})

    @app.before_request
    async def _rate_limit_auth():
        if request.path in _auth_paths and request.method == "POST":
            return await check_security_rate_limit()

    return None


def register_blueprints(app):
    app.register_blueprint(bp_user)
    app.register_blueprint(public)
    app.register_blueprint(portal)
    app.register_blueprint(ws_bp)
    return None


def register_errorhandlers(app):
    import logging

    logger = logging.getLogger(__name__)

    def _is_api_request():
        return (
            request.path.startswith("/api/")
            or request.accept_mimetypes.best == "application/json"
        )

    @app.errorhandler(Exception)
    async def handle_exception(error):
        db_session = g.pop("db_session", None)
        if db_session is not None:
            try:
                await db_session.rollback()
            except Exception:
                pass
            finally:
                await db_session.close()

        code = getattr(error, "code", 500)
        if code == 500:
            logger.exception("Unhandled exception")

        if _is_api_request():
            return {"message": "Internal server error"}, code
        return await render_template(f"{code}.html"), code

    async def render_error(error):
        error_code = getattr(error, "code", 500)
        if _is_api_request():
            return {
                "message": error.name if hasattr(error, "name") else "Error"
            }, error_code
        return await render_template(f"{error_code}.html"), error_code

    for errcode in [401, 404, 500]:
        app.errorhandler(errcode)(render_error)
    return None


def register_shellcontext(app):
    """Register shell context objects."""

    def shell_context():
        """Shell context objects."""
        return {"User": User, "Role": Role}

    app.shell_context_processor(shell_context)


def register_commands(app: Quart, commands_module):
    """Automatically register all Click commands and command groups."""
    for _name, obj in inspect.getmembers(commands_module):
        if isinstance(obj, click.Command | click.Group):
            app.cli.add_command(obj)
