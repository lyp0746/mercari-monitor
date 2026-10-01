import asyncio
import logging
import threading
import time

logger = logging.getLogger(__name__)

class TelegramBotService:
    def __init__(self, notifier):
        self.notifier = notifier
        self._running = False
        self._thread: threading.Thread = None
        self._poll_interval = 2.0

    def start(self):
        if self._running:
            return

        if not self.notifier.telegram_enabled or not self.notifier.telegram_token:
            logger.info("Telegram Bot未配置，不启动轮询服务")
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram Bot轮询服务已启动")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Telegram Bot轮询服务已停止")

    def _poll_loop(self):
        offset = 0
        consecutive_errors = 0

        while self._running:
            try:
                import httpx
                api_url = f"https://api.telegram.org/bot{self.notifier.telegram_token}/getUpdates"

                params = {
                    "offset": offset,
                    "timeout": min(30, max(1, int(self._poll_interval))),
                    "limit": 10,
                    "allowed_updates": ["message"]
                }

                with httpx.Client(timeout=self._poll_interval + 5) as client:
                    resp = client.get(api_url, params=params)
                    result = resp.json()

                    if not result.get("ok"):
                        error_desc = result.get("description", "")
                        if "409" in str(result) or "conflict" in error_desc.lower():
                            logger.warning("Webhook冲突，尝试删除webhook")
                            self._delete_webhook()
                        else:
                            logger.warning("获取更新失败: %s", error_desc)
                        consecutive_errors += 1
                        time.sleep(min(60, 2 ** consecutive_errors))
                        continue

                    updates = result.get("result", [])
                    processed_count = 0

                    for update in updates:
                        update_id = update.get("update_id")
                        message = update.get("message")

                        if message and update_id > offset:
                            text = message.get("text", "")

                            if text and text.startswith("/"):
                                chat = message.get("chat", {})
                                chat_id = str(chat.get("id", ""))
                                user = message.get("from", {})
                                username = user.get("username", "") or user.get("first_name", "未知用户")

                                original_chat_id = self.notifier.telegram_chat_id
                                try:
                                    if chat_id and chat_id != original_chat_id:
                                        logger.info("处理来自用户 %s (%s) 的命令: %s",
                                                   username, chat_id, text)

                                    if chat_id:
                                        self.notifier.telegram_chat_id = chat_id

                                    self.notifier.process_bot_command(text)
                                    processed_count += 1
                                except Exception as e:
                                    logger.error("处理命令错误: %s", e, exc_info=True)
                                finally:
                                    self.notifier.telegram_chat_id = original_chat_id

                    if updates:
                        offset = max([u.get("update_id", 0) for u in updates]) + 1
                        consecutive_errors = 0

                    if processed_count > 0:
                        logger.info("本轮处理了 %d 个Bot命令", processed_count)

            except Exception as e:
                consecutive_errors += 1
                wait_time = min(60, 2 ** consecutive_errors)
                logger.error("轮询错误(%d次): %s 等待%ds", consecutive_errors, e, wait_time)
                time.sleep(wait_time)

    def _delete_webhook(self):
        try:
            import httpx
            api_url = f"https://api.telegram.org/bot{self.notifier.telegram_token}/deleteWebhook"
            with httpx.Client(timeout=10) as client:
                client.post(api_url)
                logger.info("已删除冲突的Webhook")
        except Exception as e:
            logger.warning("删除Webhook失败: %s", e)


_bot_service: TelegramBotService = None

def init_bot_service(notifier):
    global _bot_service
    _bot_service = TelegramBotService(notifier)
    return _bot_service

def get_bot_service():
    return _bot_service

def start_bot_polling():
    if _bot_service:
        _bot_service.start()

def stop_bot_polling():
    if _bot_service:
        _bot_service.stop()