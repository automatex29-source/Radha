"""Sign in with Google.

The login page shows Google's own button. When someone picks their Google account, Google hands the page a
signed token saying who they are; the server checks Google's signature on it and that it was made for this
app, then signs the person in (making the account the first time). An existing email account with the same,
Google-confirmed address is the same account, so people who signed up with a password can use either.

Set on the server (Render > Environment):
  GOOGLE_CLIENT_ID   the "Client ID" of a Web OAuth client from Google Cloud Console
                     (APIs & Services > Credentials), ending in .apps.googleusercontent.com
Without it the Google button is hidden and email sign-in works as before.
"""
import os

import anyio

ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleSignInError(Exception):
    """The token wasn't a valid Google sign-in for this app."""


def client_id() -> str:
    return os.environ.get("GOOGLE_CLIENT_ID", "").strip()


def enabled() -> bool:
    return bool(client_id())


def _verify_sync(credential: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
    try:
        return id_token.verify_oauth2_token(credential, google_requests.Request(), client_id())
    except ValueError as exc:
        raise GoogleSignInError(str(exc))


async def verify(credential: str) -> dict:
    """Check the token from Google's button and return {email, name, sub, picture}."""
    if not enabled():
        raise GoogleSignInError("Google sign-in isn't switched on.")
    info = await anyio.to_thread.run_sync(_verify_sync, credential)
    if info.get("iss") not in ISSUERS:
        raise GoogleSignInError("Token not issued by Google")
    if not info.get("email") or not info.get("email_verified"):
        raise GoogleSignInError("This Google account has no confirmed email")
    return {"email": info["email"].lower(), "name": (info.get("name") or info["email"].split("@")[0])[:80],
            "sub": info["sub"], "picture": info.get("picture")}
