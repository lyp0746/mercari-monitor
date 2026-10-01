from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


def get_current_user(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        user = db.verify_token(token)
        if user:
            return user
    return None


def require_auth(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "未登录或登录已过期")
    return user


@router.get("/status")
def auth_status(request: Request):
    has_users = db.has_users()
    user = get_current_user(request)
    return {
        "enabled": has_users,
        "logged_in": user is not None,
        "username": user["username"] if user else None,
    }


@router.post("/register")
def register(data: RegisterRequest):
    if db.has_users():
        raise HTTPException(403, "管理员已存在，请联系管理员")
    if len(data.username) < 2 or len(data.password) < 4:
        raise HTTPException(400, "用户名至少2位，密码至少4位")
    ok = db.create_user(data.username, data.password, is_admin=True)
    if not ok:
        raise HTTPException(400, "用户名已存在")
    user = db.verify_user(data.username, data.password)
    token = db.create_token(user["id"])
    return {"ok": True, "token": token, "username": user["username"]}


@router.post("/login")
def login(data: LoginRequest):
    user = db.verify_user(data.username, data.password)
    if not user:
        raise HTTPException(401, "用户名或密码错误")
    token = db.create_token(user["id"])
    return {"ok": True, "token": token, "username": user["username"]}