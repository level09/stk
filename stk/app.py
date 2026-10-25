import asyncio
import functools
import hashlib
import importlib
import importlib.util
import inspect
import os
from pathlib import Path

from jinja2 import ChoiceLoader, FileSystemLoader, PrefixLoader
from quart import Quart, g, render_template, request, send_from_directory
from quart_security import Security, SQLAlchemyUserDatastore
from quart_security.views import _ensure_csrf_token
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.security import safe_join

import stk.extensions as ext
from stk.agent_login import agent_login_enabled, bp_agent_login
from stk.extensions import session
from stk.portal.views import portal
from stk.public.views import public
from stk.settings import Config
from stk.user.forms import ExtendedRegisterForm, OAuthAwareChangePasswordForm
from stk.user.models import Role, User, WebAuthn
from stk.user.views import bp_user
from stk.websocket import ws_bp

CORE_TEMPLATES = Path(__file__).parent / "templates"
CORE_STATIC = Path(__file__).parent / "static"


class Stk(Quart):
    """A Quart app with stk's core, then the app's extensions in list order.

    Each extension is a package exposing `init_app(app)`; its `models` module, if
    any, is imported first so migrations see its tables. Templates and static
    files resolve app first, then each extension's, then stk's. Core templates
    stay reachable as `stk/<name>`, so an override can extend the original.
    """

    def __init__(self, import_name, *, config=Config, extensions=()):
        super().__init__(
            import_name, static_folder=str(CORE_STATIC), template_folder=None
        )
        self.config.from_object(config)
        for key in ("SECRET_KEY", "SECURITY_PASSWORD_SALT"):
            if not self.config.get(key):
                raise ValueError(f"{key} is required: set it in .env")
        if not self.config.get("SQLALCHEMY_DATABASE_URI"):
            os.makedirs(self.instance_path, exist_ok=True)
            database = Path(self.instance_path) / "stk.db"
            self.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite+aiosqlite:///{database}"

        roots = [Path(self.root_path), *(Path(m.__path__[0]) for m in extensions)]
        self.template_folders = [
            *(path for root in roots if (path := root / "templates").is_dir()),
            CORE_TEMPLATES,
        ]
        self.static_folders = [
            *(path for root in roots if (path := root / "static").is_dir()),
            CORE_STATIC,
        ]
        # Sidebar pages the app adds; the layout places them under Dashboard.
        self.navigation = []

        register_blueprints(self)
        register_extensions(self)
        register_errorhandlers(self)
        register_static_versioning(self)
        register_navigation(self)

        for module in extensions:
            if importlib.util.find_spec(f"{module.__name__}.models"):
                importlib.import_module(f"{module.__name__}.models")
            module.init_app(self)

    @functools.cached_property
    def jinja_loader(self):
        return ChoiceLoader(
            [
                PrefixLoader({"stk": FileSystemLoader(CORE_TEMPLATES)}),
                *(FileSystemLoader(folder) for folder in self.template_folders),
            ]
        )

    def static_file(self, filename):
        """Return the first static file at `filename`, app first, or None."""
        for folder in self.static_folders:
            path = safe_join(str(folder), filename)
            if path is not None and os.path.isfile(path):
                return Path(path)
        return None

    async def send_static_file(self, filename):
        path = self.static_file(filename)
        if path is None:
            raise NotFound()
        return await send_from_directory(path.parent, path.name)


def register_extensions(app):
    # Async SQLAlchemy engine + session factory
    ext.engine = create_async_engine(app.config["SQLALCHEMY_DATABASE_URI"])
    ext.async_session_factory = async_sessionmaker(ext.engine, expire_on_commit=False)

    user_datastore = SQLAlchemyUserDatastore(
        ext.async_session_factory, User, Role, webauthn_model=WebAuthn
    )

    async def _open_session():
        g.db_session = user_datastore.session

    @app.after_request
    async def _close_session(response):
        db_session = g.pop("db_session", None)
        if db_session is not None:
            await db_session.close()
        return response

    async def _open_ws_session():
        g.db_session = user_datastore.session

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
        except TimeoutError:
            app.logger.warning("Timed out while disposing SQLAlchemy engine")

    from stk.security import register_security_controls
    from stk.utils.ratelimit import register_rate_limits

    register_rate_limits(app)
    register_security_controls(app)

    Security(
        app,
        user_datastore,
        register_form=ExtendedRegisterForm,
        change_password_form=OAuthAwareChangePasswordForm,
    )
    # The library resets its session before loading the user. Share that session
    # so signals and application routes participate in the same transaction.
    app.before_request(_open_session)
    app.before_websocket(_open_ws_session)

    # Session initialization
    if app.config.get("SESSION_TYPE") == "redis":
        session.init_app(app)
    # For non-redis, fall back to Quart's built-in cookie sessions

    # CSRF token for POSTs outside quart-security templates (e.g. logout form).
    # Uses the library's own get-or-create so tokens stay in sync.
    app.jinja_env.globals["csrf_token"] = _ensure_csrf_token

    return None


def register_blueprints(app):
    app.register_blueprint(bp_user)
    app.register_blueprint(public)
    app.register_blueprint(portal)
    app.register_blueprint(ws_bp)
    if agent_login_enabled(app):
        app.register_blueprint(bp_agent_login)
    return None


@functools.cache
def _static_digest(path, _mtime_ns):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def register_static_versioning(app):
    """Version `url_for('static', ...)` by content so a deploy never serves stale JS.

    Unversioned files carry no cache lifetime, so browsers keep them heuristically
    and an old component can blank every page until a hard reload.
    """

    @app.url_defaults
    def _version_static(endpoint, values):
        if endpoint == "static" and "filename" in values:
            path = app.static_file(values["filename"])
            if path is None:
                raise FileNotFoundError(f"no static file {values['filename']}")
            values["v"] = _static_digest(path, path.stat().st_mtime_ns)

    @app.after_request
    async def _cache_static(response):
        if request.path.startswith(f"{app.static_url_path}/"):
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
                if request.args.get("v")
                else "no-cache"
            )
        return response


CORE_NAVIGATION_START = [
    {"heading": "Main"},
    {"title": "Dashboard", "icon": "ti ti-home", "to": "/dashboard"},
]
CORE_NAVIGATION_END = [
    {"heading": "Account"},
    {"title": "Change Password", "icon": "ti ti-key", "to": "/change"},
    {"title": "Two-Factor Auth", "icon": "ti ti-shield-lock", "to": "/tf-setup"},
    {"title": "Recovery Codes", "icon": "ti ti-lifebuoy", "to": "/mf-recovery-codes"},
    {"heading": "Administration"},
    {
        "title": "User Management",
        "icon": "ti ti-users-group",
        "role": "admin",
        "children": [
            {"title": "Users", "icon": "ti ti-users", "to": "/users"},
            {"title": "Roles", "icon": "ti ti-shield", "to": "/roles"},
        ],
    },
    {
        "title": "Activity Logs",
        "icon": "ti ti-history",
        "to": "/activities",
        "role": "admin",
    },
]


def register_navigation(app):
    app.jinja_env.globals["stk_navigation"] = lambda: [
        *CORE_NAVIGATION_START,
        *app.navigation,
        *CORE_NAVIGATION_END,
    ]


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
                # Detach loaded instances first so rollback doesn't expire them;
                # error templates still read current_user after the session closes.
                db_session.expunge_all()
                await db_session.rollback()
            except Exception:
                logger.warning(
                    "Failed to rollback session during error handling", exc_info=True
                )
            finally:
                await db_session.close()

        # Only HTTP errors carry a status; SQLAlchemy errors also have a .code ("e3q8").
        code = error.code if isinstance(error, HTTPException) else 500
        if code == 500:
            logger.exception("Unhandled exception")

        if _is_api_request():
            return {
                "message": "Internal server error"
                if code == 500
                else getattr(error, "description", "Request failed")
            }, code
        # Fall back to 500.html for codes without a dedicated template (405, 403, ...)
        return await render_template([f"{code}.html", "500.html"]), code

    async def render_error(error):
        error_code = getattr(error, "code", 500)
        if _is_api_request():
            return {
                "message": error.name if hasattr(error, "name") else "Error"
            }, error_code
        return await render_template([f"{error_code}.html", "500.html"]), error_code

    for errcode in [401, 404, 500]:
        app.errorhandler(errcode)(render_error)
    return None
