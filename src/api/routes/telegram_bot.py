from fastapi import APIRouter, Request
from pydantic import BaseModel
import json
import logging

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.api.deps import db, notifier

logger = logging.getLogger(__name__)

router = APIRouter()

class BotCommand(BaseModel):
    text: str
    chat_id: str = None

class WebhookUpdate(BaseModel):
    update_id: int
    message: dict = None

@router.post("/command")
def handle_command(cmd: BotCommand):
    if not notifier.telegram_enabled:
        return {"ok": False, "error": "Telegram未启用"}

    processed = notifier.process_bot_command(cmd.text)
    if processed:
        return {"ok": True, "message": "命令已处理"}
    else:
        return {"ok": False, "error": "无法识别的命令"}

@router.post("/webhook")
async def handle_webhook(request: Request, update: WebhookUpdate):
    try:
        body = await request.body()
        data = json.loads(body)

        if "message" not in data:
            return {"ok": True}

        message = data["message"]
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = message.get("text", "")

        if not text or not text.startswith("/"):
            return {"ok": True}

        if not notifier.telegram_enabled:
            logger.warning("Received bot command but Telegram is not enabled")
            return {"ok": False}

        original_chat_id = notifier.telegram_chat_id
        try:
            if chat_id != original_chat_id:
                notifier.telegram_chat_id = chat_id

            processed = notifier.process_bot_command(text)

            if not processed and text.lower() in ["/start", "/help"]:
                notifier.process_bot_command("/help")

        finally:
            notifier.telegram_chat_id = original_chat_id

        return {"ok": True}

    except Exception as e:
        logger.error("Webhook error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}

@router.get("/info")
def get_bot_info():
    return {
        "enabled": notifier.telegram_enabled,
        "configured": bool(notifier.telegram_token and notifier.telegram_chat_id),
        "commands_available": [
            "/help", "/status", "/test",
            "/add", "/remove", "/keywords",
            "/watch", "/unwatch", "/sellers",
            "/bseller", "/unban", "/bword", "/unbword", "/blacklist",
            "/list"
        ]
    }

@router.post("/set_webhook")
def set_webhook(webhook_url: str = None):
    if not notifier.telegram_token:
        return {"ok": False, "error": "Token未设置"}

    try:
        import httpx
        api_url = f"https://api.telegram.org/bot{notifier.telegram_token}/setWebhook"

        payload = {}
        if webhook_url:
            payload["url"] = webhook_url
            payload["allowed_updates"] = ["message"]
        else:
            payload["url"] = ""

        with httpx.Client(timeout=10) as client:
            resp = client.post(api_url, json=payload)
            result = resp.json()

            if result.get("ok"):
                action = "设置" if webhook_url else "删除"
                return {
                    "ok": True,
                    "message": f"Webhook已{action}",
                    "webhook_url": webhook_url or "",
                    "result": result.get("description", "")
                }
            else:
                return {
                    "ok": False,
                    "error": result.get("description", "未知错误"),
                    "result": result
                }

    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.delete("/webhook")
def delete_webhook():
    return set_webhook(None)

@router.post("/get_webhook_info")
def get_webhook_info():
    if not notifier.telegram_token:
        return {"ok": False, "error": "Token未设置"}

    try:
        import httpx
        api_url = f"https://api.telegram.org/bot{notifier.telegram_token}/getWebhookInfo"

        with httpx.Client(timeout=10) as client:
            resp = client.get(api_url)
            result = resp.json()

            if result.get("ok"):
                return {
                    "ok": True,
                    "info": result.get("result", {})
                }
            else:
                return {
                    "ok": False,
                    "error": result.get("description", "未知错误")
                }

    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.post("/poll")
async def poll_updates(offset: int = 0, timeout: int = 30, limit: int = 10):
    if not notifier.telegram_token:
        return {"ok": False, "updates": [], "error": "Token未设置"}

    try:
        import httpx
        api_url = f"https://api.telegram.org/bot{notifier.telegram_token}/getUpdates"

        params = {
            "offset": offset,
            "timeout": timeout,
            "limit": limit,
            "allowed_updates": ["message"]
        }

        with httpx.Client(timeout=timeout + 5) as client:
            resp = client.get(api_url, params=params)
            result = resp.json()

            if not result.get("ok"):
                return {
                    "ok": False,
                    "updates": [],
                    "error": result.get("description", "获取更新失败")
                }

            updates = result.get("result", [])
            processed_count = 0

            for update in updates:
                update_id = update.get("update_id")
                message = update.get("message")

                if message:
                    text = message.get("text", "")
                    if text and text.startswith("/"):
                        chat = message.get("chat", {})
                        chat_id = str(chat.get("id", ""))

                        original_chat_id = notifier.telegram_chat_id
                        try:
                            if chat_id:
                                notifier.telegram_chat_id = chat_id
                            notifier.process_bot_command(text)
                            processed_count += 1
                        finally:
                            notifier.telegram_chat_id = original_chat_id

            new_offset = max([u.get("update_id", 0) for u in updates]) + 1 if updates else offset

            return {
                "ok": True,
                "updates_received": len(updates),
                "commands_processed": processed_count,
                "next_offset": new_offset
            }

    except Exception as e:
        logger.error("Poll error: %s", e, exc_info=True)
        return {"ok": False, "updates": [], "error": str(e)}