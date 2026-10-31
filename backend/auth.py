"""Authentication: bcrypt password hashing + JWT bearer tokens.

Every sign-in token records when it was made. When a password is reset (or the account is deleted) the
account's older tokens stop working, so anyone who got into the account is signed out everywhere.
"""
import os
import time
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_DAYS = 7

# user id -> unix second; sign-in tokens made before it are refused. Filled from the database at startup
# (users.tokensValidAfter) and kept up to date by revoke_sessions().
_valid_after: dict = {}


def revoke_sessions(user_id: str) -> int:
    """Make every sign-in token this account already has stop working. Returns the cut-off to store."""
    cutoff = int(time.time())
    _valid_after[user_id] = cutoff
    return cutoff


def load_revocations(rows) -> None:
    for row in rows:
        if row.get("id") and row.get("tokensValidAfter"):
            _valid_after[row["id"]] = int(row["tokensValidAfter"])


def _secret() -> str:
    secret = os.environ.get("AUTH_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="Server misconfigured: AUTH_SECRET is not set")
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed stored hash: treat as a failed login rather than a 500.
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "iat": int(time.time()),
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    token = request.query_params.get("token")
    if token:
        return token
    raise HTTPException(status_code=401, detail="Not authenticated")


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        cutoff = _valid_after.get(payload.get("sub"))
        if cutoff and int(payload.get("iat") or 0) < cutoff:
            raise HTTPException(status_code=401, detail="Signed out. Please sign in again.")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_user_id_from_request(request: Request) -> str:
    payload = decode_token(_extract_token(request))
    return payload["sub"]
