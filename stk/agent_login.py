from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from quart import Blueprint, current_app, g, redirect, request
from quart_security.proxies import _security
from sqlalchemy import select

from stk.user.models import User

bp_agent_login = Blueprint("agent_login", __name__, url_prefix="/_test")
TOKEN_SALT = "stk-agent-login"


def agent_login_enabled(app):
    enabled = app.config.get("STK_ENABLE_AGENT_LOGIN", False)
    if not enabled:
        return False

    is_safe_env = app.testing or app.config.get("STK_ENV") == "development"
    if not is_safe_env:
        raise RuntimeError("agent login cannot be enabled outside development/testing")

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("agent login cannot be enabled without SECRET_KEY")

    return True


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _validate_local_next(next_path):
    if not next_path.startswith("/") or next_path.startswith("//"):
        raise ValueError("next path must be local")
    return next_path


def create_agent_login_token(email, next_path="/dashboard/"):
    return _serializer().dumps(
        {"email": email, "next": _validate_local_next(next_path)},
        salt=TOKEN_SALT,
    )


def read_agent_login_token(token, max_age):
    try:
        return _serializer().loads(token, salt=TOKEN_SALT, max_age=max_age)
    except SignatureExpired as exc:
        raise ValueError("agent login token expired") from exc
    except BadSignature as exc:
        raise ValueError("invalid agent login token") from exc


@bp_agent_login.get("/login")
async def agent_login():
    token = request.args.get("token")
    if not token:
        return "", 400

    try:
        payload = read_agent_login_token(
            token,
            max_age=current_app.config["STK_AGENT_LOGIN_MAX_TTL_SECONDS"],
        )
    except ValueError:
        return "", 400

    email = payload["email"]
    if not email.endswith("@example.com"):
        return "", 403

    user = (
        await g.db_session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is None or not user.active:
        return "", 403

    await _security.login_user(user)
    return redirect(payload["next"])
