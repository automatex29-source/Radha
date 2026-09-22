"""Authentication: bcrypt password hashing + JWT bearer tokens."""
import os
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_DAYS = 7


def _secret() -> str:
    return os.environ["AUTH_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
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
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_user_id_from_request(request: Request) -> str:
    payload = decode_token(_extract_token(request))
    return payload["sub"]
