from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.core.db import Db
from backend.core.errors import CadenceError, Unauthorized
from backend.core.security import User, current_user, db_dep, hash_password, login_failures, make_token, verify_password

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


class PasswordBody(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=128)


@router.post("/auth/password")
def change_password(body: PasswordBody, request: Request, user: User = Depends(current_user), db: Db = Depends(db_dep)) -> dict:
    row = db.q1("select password_hash from users where id = %s and active", (user["id"],))
    if not row or not verify_password(body.current, row["password_hash"]):
        if not login_failures.check(request.client.host if request.client else "unknown"):
            raise CadenceError("Too many attempts. Wait a minute and try again", code="rate_limited", status=429)
        raise Unauthorized("The current password is wrong", code="bad_credentials")
    db.x("update users set password_hash = %s where id = %s", (hash_password(body.new), user["id"]))
    return {"ok": True}
