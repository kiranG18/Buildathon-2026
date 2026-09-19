import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Header, Request

from backend.core.config import get_settings
from backend.core.db import Db, tx
from backend.core.errors import Forbidden, Unauthorized

ITER = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITER).hex()
    return f"pbkdf2${ITER}${salt}${dk}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, dk = stored.split("$")
        cand = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters)).hex()
        return hmac.compare_digest(cand, dk)
    except ValueError:
        return False


def make_token(user: dict) -> str:
    payload = {"sub": user["id"], "role": user["role"], "exp": datetime.now(UTC) + timedelta(hours=12)}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise Unauthorized("Sign in again", code="invalid_token") from e


def secret_ok(provided: str | None, expected: str) -> bool:
    return bool(provided) and hmac.compare_digest(provided.encode(), expected.encode())


class User(dict):
    @property
    def is_rep(self) -> bool:
        return self["role"] == "Rep"


def current_user(authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthorized("Missing token", code="no_token")
    claims = decode_token(authorization.split(" ", 1)[1])
    with tx() as db:
        row = db.q1("select id, name, role, email, active, rep_limit as \"limit\" from users where id = %s", (claims["sub"],))
    if not row or not row["active"]:
        raise Unauthorized("Account is not active", code="invalid_token")
    return User(row)


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user["role"] not in roles:
            raise Forbidden("Your role cannot do this")
        return user

    return dep


def db_dep():
    with tx() as db:
        yield db


def webhook_guard(request: Request, x_cadence_secret: str | None = Header(default=None)) -> None:
    if not secret_ok(x_cadence_secret, get_settings().webhook_shared_secret):
        raise Unauthorized("Bad shared secret", code="bad_secret")


class RateLimiter:
    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self.hits.clear()


login_failures = RateLimiter(10, 60.0)


__all__ = ["Db"]
