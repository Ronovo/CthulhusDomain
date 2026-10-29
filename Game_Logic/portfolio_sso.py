"""Log in with a portfolio account.

The same file is in every Python portfolio app. The app sends the player to the portfolio's
/sso/authorize, which posts a short-lived token signed with the portfolio's private key back to the
app's /sso/callback. The app checks it with PORTFOLIO_SSO_PUBLIC_KEY. Without PORTFOLIO_SSO_URL and
PORTFOLIO_SSO_PUBLIC_KEY set, portfolio login is off and the app runs on its own, and PyJWT is only
imported once a token has to be checked.
"""
import base64
import os
import secrets
from functools import lru_cache
from typing import Optional
from urllib.parse import urlencode

ISSUER = "portfolio"


@lru_cache
def _public_key(raw: str):
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    return load_der_public_key(base64.b64decode(raw))


def enabled() -> bool:
    return bool(os.environ.get("PORTFOLIO_SSO_URL", "").strip()
                and os.environ.get("PORTFOLIO_SSO_PUBLIC_KEY", "").strip())


def portfolio_url() -> str:
    """The portfolio's address. Its /sso/me tells a page which portfolio account the browser is logged in to."""
    return os.environ["PORTFOLIO_SSO_URL"].strip().rstrip("/")


def new_state() -> str:
    return secrets.token_urlsafe(16)


def authorize_url(app_id: str, callback_url: str, state: str) -> str:
    query = urlencode({"app": app_id, "return": callback_url, "state": state})
    return f"{portfolio_url()}/sso/authorize?{query}"


def verify(token: str, app_id: str) -> Optional[dict]:
    """The portfolio account ({"sub", "username"}) a token was issued to for this app, or None"""
    if not enabled() or not token:
        return None
    import jwt
    try:
        claims = jwt.decode(token, _public_key(os.environ["PORTFOLIO_SSO_PUBLIC_KEY"].strip()), algorithms=["RS256"],
                            audience=app_id, issuer=ISSUER, options={"require": ["exp", "iss", "aud", "sub"]})
    except (jwt.InvalidTokenError, ValueError):
        return None
    return {"sub": claims["sub"], "username": claims.get("name", "")}


def add_flask_routes(app, app_id: str, on_login):
    """Adds /sso/login and /sso/callback to a Flask app. on_login(account) runs once a token checks out
    and returns the response."""
    from flask import abort, redirect, request, session, url_for

    @app.get("/sso/login")
    def sso_login():
        if not enabled():
            abort(404)
        session["portfolio_state"] = state = new_state()
        return redirect(authorize_url(app_id, url_for("sso_callback", _external=True), state))

    @app.post("/sso/callback")
    def sso_callback():
        state = session.pop("portfolio_state", None)
        if state is None or not secrets.compare_digest(state, request.form.get("state", "")):
            abort(400)
        account = verify(request.form.get("token", ""), app_id)
        if account is None:
            abort(400)
        return on_login(account)
