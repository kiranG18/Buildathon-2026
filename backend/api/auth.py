from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.core.db import Db
from backend.core.errors import CadenceError, Unauthorized
from backend.core.security import db_dep, login_failures, make_token, verify_password

router = APIRouter()


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginBody, request: Request, db: Db = Depends(db_dep)) -> dict:
    key = request.client.host if request.client else "unknown"
    row = db.q1("select * from users where lower(email) = lower(%s)", (body.email.strip(),))
    if not row or not row["active"] or not verify_password(body.password, row["password_hash"]):
        if not login_failures.check(key):
            raise CadenceError("Too many attempts. Wait a minute and try again", code="rate_limited", status=429)
        raise Unauthorized("Email or password is wrong", code="bad_credentials")
    user = {"id": row["id"], "name": row["name"], "role": row["role"], "email": row["email"]}
    return {"token": make_token(user), "user": user}
