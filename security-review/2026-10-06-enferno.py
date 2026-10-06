"""Compare local Enferno controls using an in-memory database and mocked IdP."""

import html
import json
import re
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])

from enferno.app import create_app
from enferno.extensions import db
from enferno.public.views import oauth_logged_in
from enferno.settings import Config
from enferno.user.models import OAuth, Role, User
from flask_security import hash_password


class ReviewConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_TYPE = "sqlalchemy"
    GOOGLE_AUTH_ENABLED = False
    GITHUB_AUTH_ENABLED = False
    MAIL_SUPPRESS_SEND = True


PASSWORD = "ReviewPassword123!"
app = create_app(ReviewConfig)


@app.get("/_review/oauth")
def oauth_fixture():
    with patch(
        "enferno.public.views.get_oauth_user_data",
        return_value={
            "id": "fixture-id",
            "email": "user@example.com",
            "name": "Fixture",
        },
    ):
        return oauth_logged_in(
            SimpleNamespace(name="google"), {"access_token": "fixture-token"}
        )


def login(client, email):
    page = client.get("/login").get_data(as_text=True)
    csrf = html.unescape(
        re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page).group(1)
    )
    response = client.post(
        "/login", data={"email": email, "password": PASSWORD, "csrf_token": csrf}
    )
    assert response.status_code == 302, response.status_code


with app.app_context():
    db.create_all()
    admin = User(
        email="admin@example.com",
        password=hash_password(PASSWORD),
        active=True,
        confirmed_at=datetime.now(),
    )
    admin.roles.append(Role(name="admin"))
    user = User(
        email="user@example.com",
        password=hash_password(PASSWORD),
        active=True,
        confirmed_at=datetime.now(),
    )
    db.session.add_all([admin, user])
    db.session.commit()
    admin_id, user_id = admin.id, user.id

client = app.test_client()
login(client, "admin@example.com")
results = {
    "api_no_csrf_foreign_origin": client.post(
        "/api/role/",
        json={"item": {"name": "review-role"}},
        headers={"Origin": "https://other.example"},
    ).status_code
}
page = client.get("/users/").get_data(as_text=True)
csrf = re.search(r'X-CSRFToken"\] = "([^"]+)"', page).group(1)
results["clear_admin_roles_response"] = client.post(
    f"/api/user/{admin_id}", json={"item": {"roles": []}}, headers={"X-CSRFToken": csrf}
).status_code
results["admin_access_after_clear_roles"] = client.get("/api/users").status_code
with app.app_context():
    user = db.session.get(User, user_id)
    user.tf_primary_method = "authenticator"
    user.tf_totp_secret = "fixture-secret"
    db.session.commit()
oauth_client = app.test_client()
results["oauth_link_response"] = oauth_client.get("/_review/oauth").status_code
results["oauth_access_without_totp"] = oauth_client.get("/dashboard/").status_code
with app.app_context():
    linked = db.session.execute(db.select(OAuth)).scalar_one()
    results["email_linked_to_existing_user"] = linked.user_id == user_id

app.config["DISABLE_MULTIPLE_SESSIONS"] = True
first = app.test_client()
login(first, "admin@example.com")
login(app.test_client(), "admin@example.com")
results["single_session_previous_access"] = first.get("/dashboard/").status_code

attacker = app.test_client()
attacker.get("/login")
known_sid = attacker.get_cookie("session").value
victim = app.test_client()
victim.set_cookie("session", known_sid)
login(victim, "admin@example.com")
results["server_sid_preserved_on_login"] = (
    victim.get_cookie("session").value == known_sid
)
results["pre_login_cookie_access_after_victim_login"] = attacker.get(
    "/dashboard/"
).status_code

print(json.dumps(results, indent=2))
