from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db
from src.monitors import PLATFORM_NAMES

router = APIRouter()


class AccountCreate(BaseModel):
    platform: str
    account_name: str
    cookie: str = ""
    token: str = ""
    extra: str = ""


@router.get("")
def list_accounts(platform: str = None):
    accounts = db.get_platform_accounts(platform)
    return {
        "items": [
            {
                **a,
                "platform_name": PLATFORM_NAMES.get(a["platform"], a["platform"]),
            }
            for a in accounts
        ]
    }


@router.post("")
def add_account(data: AccountCreate):
    if data.platform not in PLATFORM_NAMES:
        raise HTTPException(400, f"未知平台: {data.platform}")
    ok = db.add_platform_account(
        data.platform, data.account_name, data.cookie, data.token, data.extra
    )
    if not ok:
        raise HTTPException(400, "账号添加失败")
    return {"ok": True}


@router.get("/{account_id:int}")
def get_account(account_id: int):
    account = db.get_platform_account_full(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")
    cookie_preview = account.get("cookie", "")
    if len(cookie_preview) > 20:
        cookie_preview = cookie_preview[:10] + "..." + cookie_preview[-10:]
    token_preview = account.get("token", "")
    if len(token_preview) > 20:
        token_preview = token_preview[:10] + "..." + token_preview[-10:]
    return {
        **account,
        "cookie_preview": cookie_preview,
        "token_preview": token_preview,
        "platform_name": PLATFORM_NAMES.get(account["platform"], account["platform"]),
    }


@router.delete("/{account_id:int}")
def remove_account(account_id: int):
    db.remove_platform_account(account_id)
    return {"ok": True}