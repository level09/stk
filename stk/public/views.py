import datetime
import secrets

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oidc.core import CodeIDToken
from joserfc import jwt
from joserfc.jwk import KeySet
from quart import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from quart_security import current_user
from quart_security.proxies import _security
from sqlalchemy import select

from stk.user.models import OAuth, User

public = Blueprint("public", __name__, static_folder="../static")


def get_real_ip():
    return request.remote_addr


def create_oauth_user(provider_data, ip_address):
    now = datetime.datetime.now()
    user = User(
        email=provider_data.get("email"),
        username=provider_data.get("email"),
        name=provider_data.get("name", ""),
        password=User.random_password(),
        password_set=False,
        active=True,
        confirmed_at=now,
        current_login_at=now,
        current_login_ip=ip_address,
        login_count=1,
    )
    return user


@public.route("/health")
async def health():
    import stk.extensions as ext

    status = {"status": "ok", "checks": {}}

    # DB check
    try:
        from sqlalchemy import text

        async with ext.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status["checks"]["database"] = "ok"
    except Exception:
        status["checks"]["database"] = "error"
        status["status"] = "degraded"

    # Redis check (if configured)
    session_interface = getattr(current_app, "session_interface", None)
    backend = getattr(session_interface, "backend", None)
    if backend is not None:
        try:
            await backend.ping()
            status["checks"]["redis"] = "ok"
        except Exception:
            status["checks"]["redis"] = "error"
            status["status"] = "degraded"

    code = 200 if status["status"] == "ok" else 503
    return status, code


@public.route("/")
async def index():
    return await render_template("index.html")


@public.route("/robots.txt")
async def static_from_root():
    return await send_from_directory(public.static_folder, request.path[1:])


# OAuth transactions use single-use server state and PKCE.
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


async def authentication_failed():
    await flash(
        "Authentication failed. Use your existing sign-in method.", category="error"
    )
    return redirect(url_for("security.login"))


async def handle_oauth_callback(provider_name, token, user_info):
    provider_user_id = (
        user_info.get("sub") if provider_name == "google" else user_info.get("id")
    )
    email = user_info.get("email")
    if (
        not token
        or not provider_user_id
        or not email
        or user_info.get("email_verified") is not True
    ):
        return await authentication_failed()
    account = await g.db_session.scalar(
        select(OAuth).where(
            OAuth.provider == provider_name,
            OAuth.provider_user_id == str(provider_user_id),
        )
    )
    if account:
        user = account.user
    else:
        # Email ownership at an IdP does not authorize linking local credentials.
        existing = await g.db_session.scalar(select(User).where(User.email == email))
        if existing:
            return await authentication_failed()
        user = create_oauth_user(
            {
                "email": email,
                "name": user_info.get("name") or user_info.get("login", ""),
            },
            get_real_ip(),
        )
        g.db_session.add_all(
            [
                user,
                OAuth(
                    provider=provider_name,
                    provider_user_id=str(provider_user_id),
                    user=user,
                ),
            ]
        )
        await g.db_session.commit()
    if not user.active or (
        user.locked_until
        and user.locked_until > datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    ):
        return await authentication_failed()
    if current_user.is_authenticated:
        await _security.logout_user()
    if current_app.config.get("SECURITY_TWO_FACTOR") and user.tf_primary_method:
        session["tf_user_id"] = await _security.state_store.put(
            {"user_id": user.get_id()}, ttl=300
        )
        return redirect(url_for("security.two_factor_token_validation"))
    await _security.login_user(user)
    return redirect(url_for("portal.dashboard"))


def get_google_client():
    return AsyncOAuth2Client(
        client_id=current_app.config.get("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=current_app.config.get("GOOGLE_OAUTH_CLIENT_SECRET"),
        code_challenge_method="S256",
    )


def get_github_client():
    return AsyncOAuth2Client(
        client_id=current_app.config.get("GITHUB_OAUTH_CLIENT_ID"),
        client_secret=current_app.config.get("GITHUB_OAUTH_CLIENT_SECRET"),
        code_challenge_method="S256",
    )


async def google_discovery():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(GOOGLE_DISCOVERY_URL)
        response.raise_for_status()
        return response.json()


async def start_oauth(provider):
    if current_user.is_authenticated or not current_app.config.get(
        f"{provider.upper()}_AUTH_ENABLED"
    ):
        return await authentication_failed()
    verifier, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    public_url = current_app.config.get("STK_PUBLIC_URL")
    redirect_uri = (
        (public_url.rstrip("/") + url_for(f"public.{provider}_callback"))
        if public_url
        else url_for(f"public.{provider}_callback", _external=True)
    )
    client = get_google_client() if provider == "google" else get_github_client()
    try:
        endpoint = (
            (await google_discovery())["authorization_endpoint"]
            if provider == "google"
            else GITHUB_AUTHORIZE_URL
        )
        auth_url, state = client.create_authorization_url(
            endpoint,
            redirect_uri=redirect_uri,
            scope="openid profile email"
            if provider == "google"
            else "read:user user:email",
            code_verifier=verifier,
            nonce=nonce,
        )
        session[f"oauth_{provider}"] = await _security.state_store.put(
            {
                "state": state,
                "verifier": verifier,
                "nonce": nonce,
                "redirect_uri": redirect_uri,
            },
            ttl=300,
        )
        return redirect(auth_url)
    finally:
        await client.aclose()


async def consume_oauth(provider):
    if not current_app.config.get(f"{provider.upper()}_AUTH_ENABLED"):
        return None
    token = session.pop(f"oauth_{provider}", None)
    state, code = request.args.get("state"), request.args.get("code")
    if not token or not state or not code:
        return None
    transaction = await _security.state_store.pop(token)
    if not transaction or not secrets.compare_digest(state, transaction["state"]):
        return None
    return transaction


@public.route("/login/google")
async def google_login():
    return await start_oauth("google")


@public.route("/login/github")
async def github_login():
    return await start_oauth("github")


@public.route("/login/google/callback")
async def google_callback():
    try:
        transaction = await consume_oauth("google")
        if transaction is None:
            return await authentication_failed()
        discovery = await google_discovery()
        async with get_google_client() as client:
            token = await client.fetch_token(
                discovery["token_endpoint"],
                code=request.args["code"],
                redirect_uri=transaction["redirect_uri"],
                code_verifier=transaction["verifier"],
            )
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(discovery["jwks_uri"])
            response.raise_for_status()
            decoded = jwt.decode(
                token["id_token"],
                KeySet.import_key_set(response.json()),
                algorithms=["RS256"],
            )
            claims = CodeIDToken(
                decoded.claims,
                decoded.header,
                options={
                    "iss": {
                        "essential": True,
                        "values": [
                            "https://accounts.google.com",
                            "accounts.google.com",
                        ],
                    },
                    "aud": {
                        "essential": True,
                        "value": current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
                    },
                },
                params={
                    "client_id": current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
                    "nonce": transaction["nonce"],
                    "access_token": token["access_token"],
                },
            )
            claims.validate(leeway=60)
        return await handle_oauth_callback("google", token, claims)
    except Exception:
        current_app.logger.exception("Google OAuth failed")
        return await authentication_failed()


@public.route("/login/github/callback")
async def github_callback():
    try:
        transaction = await consume_oauth("github")
        if transaction is None:
            return await authentication_failed()
        async with get_github_client() as client:
            token = await client.fetch_token(
                GITHUB_TOKEN_URL,
                code=request.args["code"],
                redirect_uri=transaction["redirect_uri"],
                code_verifier=transaction["verifier"],
            )
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {
                "Authorization": f"Bearer {token['access_token']}",
                "Accept": "application/json",
            }
            response = await client.get(f"{GITHUB_API_URL}/user", headers=headers)
            response.raise_for_status()
            user_info = response.json()
            response = await client.get(
                f"{GITHUB_API_URL}/user/emails", headers=headers
            )
            response.raise_for_status()
            primary = next(
                (
                    email
                    for email in response.json()
                    if email.get("primary") and email.get("verified")
                ),
                None,
            )
            if not primary:
                return await authentication_failed()
            user_info.update(email=primary["email"], email_verified=True)
        return await handle_oauth_callback("github", token, user_info)
    except Exception:
        current_app.logger.exception("GitHub OAuth failed")
        return await authentication_failed()
