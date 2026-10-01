import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

_PLATFORM_NAMES = {
    "mercari_jp": "Mercari JP", "bunjang": "Bunjang 번장",
    "paypay_fleamarket": "PayPay フリマ", "fril": "Fril (Rakuma)",
    "yahoo_auctions": "Yahoo! Auctions", "carousell": "Carousell",
    "surugaya": "駿河屋", "rakuten": "楽天市場",
    "yahoo_shopping": "Yahoo!ショッピング",
}

_PLATFORM_EMOJI = {
    "mercari_jp": "🇯🇵", "bunjang": "🇰🇷",
    "paypay_fleamarket": "🇯🇵", "fril": "🇯🇵",
    "yahoo_auctions": "🇯🇵", "carousell": "🌏",
    "surugaya": "🇯🇵", "rakuten": "🇯🇵",
    "yahoo_shopping": "🇯🇵",
}

_CURRENCY_SYMBOLS = {
    "JPY": "¥", "KRW": "₩", "SGD": "S$", "HKD": "HK$",
    "TWD": "NT$", "MYR": "RM", "AUD": "A$", "PHP": "₱",
}

_DEFAULT_RATES = {
    "JPY": "0.0473", "KRW": "0.0045", "SGD": "4.83",
    "HKD": "0.82", "TWD": "0.23", "MYR": "1.65",
    "AUD": "4.75", "PHP": "0.13",
}

_CONDITION_MAP = {
    "new": "全新", "like_new": "几乎全新", "very_good": "非常好",
    "good": "良好", "acceptable": "可接受", "poor": "较差",
    "未使用": "全新", "未使用に近い": "几乎全新",
    "目立った傷や汚れなし": "无明显划痕或污垢", "やや傷や汚れあり": "略有划痕或污垢",
    "傷や汚れあり": "有划痕或污垢", "全体的に状態が悪い": "整体状态较差",
    "新品、未使用": "全新/未使用", "未使用に近い": "接近未使用",
    "目立った傷や汚れなし": "无明显伤痕和污渍",
    "やや傷や汚れあり": "有轻微伤痕或污渍",
    "傷や汚れあり": "有伤痕或污渍",
    "全体的に状態が悪い": "整体状态不好",
    "Brand New": "全新", "Like New": "几乎全新", "Lightly Used": "轻度使用",
    "Well Used": "明显使用", "Heavily Used": "重度使用",
    "신품": "全新", "거의 새 것": "几乎全新", "사용감 적음": "使用感少",
    "사용감 많음": "使用感多", "하자 있음": "有瑕疵",
}


def _format_age(found_at: str) -> str:
    if not found_at:
        return ""
    try:
        if isinstance(found_at, (int, float)):
            ts = found_at / 1000 if found_at > 1e12 else found_at
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            s = str(found_at).strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(s)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        dt = datetime.strptime(s, fmt)
                        dt = dt.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
                else:
                    return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (datetime.now(timezone.utc) - dt).total_seconds()
        if delta < 0:
            return f"{found_at}（未来）"
        if delta < 60:
            return f"{int(delta)}秒前"
        if delta < 3600:
            return f"{int(delta // 60)}分{int(delta % 60)}秒前"
        if delta < 86400:
            return f"{int(delta // 3600)}小时{int((delta % 3600) // 60)}分前"
        return f"{int(delta // 86400)}天前"
    except Exception:
        return str(found_at)


def _format_found_at(found_at: str) -> str:
    if not found_at:
        return ""
    try:
        s = str(found_at).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
            else:
                return str(found_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(found_at)


class Notifier:
    def __init__(self, db=None):
        self._callbacks: list[Callable] = []
        self._lock = threading.Lock()
        self.telegram_enabled = False
        self.telegram_token = ""
        self.telegram_chat_id = ""
        self.discord_enabled = False
        self.discord_webhook_url = ""
        self.db = db
        self._http = httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0, read=5.0), follow_redirects=True, http2=False,
                                   limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
                                   verify=False)
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="notif")
        self._load_telegram_config()
        self._load_discord_config()

    def _load_telegram_config(self):
        if not self.db:
            return
        token = self.db.get_setting("telegram_token", "")
        chat_id = self.db.get_setting("telegram_chat_id", "")
        if token and chat_id:
            self.telegram_token = token
            self.telegram_chat_id = chat_id
            self.telegram_enabled = True

    def _load_discord_config(self):
        if not self.db:
            return
        webhook_url = self.db.get_setting("discord_webhook_url", "")
        if webhook_url:
            self.discord_webhook_url = webhook_url
            self.discord_enabled = True

    def add_callback(self, cb: Callable):
        with self._lock:
            self._callbacks.append(cb)

    def notify(self, item: dict):
        tasks = []
        
        if self.telegram_enabled and self.telegram_token and self.telegram_chat_id:
            tasks.append(self._executor.submit(self._send_telegram, item))

        if self.discord_enabled and self.discord_webhook_url:
            tasks.append(self._executor.submit(self._send_discord, item))

        if self._callbacks:
            def run_callbacks():
                with self._lock:
                    for cb in self._callbacks:
                        try:
                            cb(item)
                        except Exception:
                            pass
            tasks.append(self._executor.submit(run_callbacks))

        for t in tasks:
            try:
                t.result(timeout=5.0)
            except Exception as e:
                logger.warning(f"Notification task failed: {e}")

    def _get_exchange_rate(self, currency: str) -> float:
        if not self.db:
            return float(_DEFAULT_RATES.get(currency, "0"))
        rate_str = self.db.get_setting(f"exchange_rate_{currency.lower()}", _DEFAULT_RATES.get(currency, "0"))
        try:
            return float(rate_str)
        except (ValueError, TypeError):
            return 0.0

    def _build_caption(self, item: dict) -> str:
        platform = item.get("platform", "")
        platform_name = _PLATFORM_NAMES.get(platform, platform)
        emoji = _PLATFORM_EMOJI.get(platform, "📦")
        currency = item.get("currency", "JPY")
        price = item.get("price", 0)
        symbol = _CURRENCY_SYMBOLS.get(currency, currency + " ")

        cny_price = ""
        if price:
            rate = self._get_exchange_rate(currency)
            if rate > 0:
                cny_price = f" ≈¥{int(price * rate)}"

        name = item.get("name", "未知商品")
        url = item.get("url", "")
        found_at = item.get("found_at", "")
        seller = item.get("seller", "")
        is_auction = item.get("is_auction", False)
        is_price_drop = item.get("price_drop", False)
        is_ending = item.get("auction_ending", False)
        has_new_comment = item.get("new_comment", False)
        is_watched_seller = item.get("watched_seller", False)

        condition_raw = item.get("condition", "")
        condition = _CONDITION_MAP.get(condition_raw, condition_raw) if condition_raw else "未知"

        lines = []
        lines.append(f"[{symbol}] {name}")

        if is_price_drop:
            old_price = item.get("old_price", 0)
            if old_price:
                rate = self._get_exchange_rate(currency)
                old_cny = f" ≈¥{int(old_price * rate)}" if (rate > 0) else ""
                lines.append(f"{symbol}{old_price:,}{old_cny} → {symbol}{price:,}{cny_price}")
            else:
                lines.append(f"{symbol}{price:,}{cny_price}")
        else:
            lines.append(f"{symbol}{price:,}{cny_price}")

        if is_price_drop:
            lines.append("💸 降价提醒")
        elif is_ending:
            lines.append("⏰ 拍卖即将结束")
        elif has_new_comment:
            lines.append("💬 留言更新")
        elif is_watched_seller:
            lines.append(f"⭐ 关注卖家: {seller}")

        platform_display = f"{emoji} {platform_name}"
        if is_auction:
            platform_display += " 🚨拍卖"
        lines.append(f"平台: {platform_display}")

        if condition and condition != "未知":
            lines.append(f"成色: {condition}")

        if url:
            lines.append(f"链接: {url}")

        if found_at:
            found_time = _format_found_at(found_at)
            lines.append(f"上新时间: {found_time}")

        if seller:
            lines.append(f"卖家ID: {seller}")

        return "\n".join(lines)

    def _send_telegram(self, item: dict):
        image_url = item.get("image_url", "")
        caption = self._build_caption(item)

        self._executor.submit(self._tg_send_text, caption, image_url)

    def _tg_send_text(self, caption: str, image_url: str):
        try:
            api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            resp = self._http.post(api_url, json={
                "chat_id": self.telegram_chat_id,
                "text": caption,
                "disable_web_page_preview": True,
            })
            if resp.status_code != 200:
                logger.warning("Telegram text failed: %s", resp.text[:200])
        except Exception as e:
            logger.warning("Telegram text error: %s", e)

        if image_url:
            self._executor.submit(self._tg_send_photo, caption, image_url)

    def _tg_send_photo(self, caption: str, image_url: str):
        try:
            api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendPhoto"
            resp = self._http.post(api_url, json={
                "chat_id": self.telegram_chat_id,
                "photo": image_url,
                "caption": caption,
            }, timeout=8)
            if resp.status_code != 200:
                resp2 = self._http.post(api_url, data={
                    "chat_id": self.telegram_chat_id,
                    "photo": image_url,
                    "caption": caption,
                }, timeout=8)
                if resp2.status_code != 200:
                    logger.warning("Telegram photo failed: %s", resp2.text[:200])
        except Exception as e:
            logger.warning("Telegram photo error: %s", e)

    def test_telegram(self) -> tuple[bool, str]:
        if not self.telegram_token or not self.telegram_chat_id:
            return False, "请先填写 Token 和 Chat ID"

        try:
            api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            test_msg = (
                "✅ 二手监控助手 连接成功\n\n"
                "[¥] 测试商品名称（示例）\n"
                "¥10,000 ≈¥470\n"
                "平台: 🇯🇵 Mercari JP\n"
                "成色: 良好\n"
                "链接: https://example.com\n"
                "上新时间: 2024-07-15 12:30:00\n"
                "卖家ID: test_seller"
            )
            resp = self._http.post(api_url, json={
                "chat_id": self.telegram_chat_id,
                "text": test_msg,
            })
            if resp.status_code == 200:
                return True, "发送成功！请检查 Telegram 消息格式"
            else:
                data = resp.json()
                err = data.get("description", resp.text[:200])
                return False, f"发送失败: {err}"
        except Exception as e:
            return False, f"连接失败: {e}"

    def _send_discord(self, item: dict):
        image_url = item.get("image_url", "")
        embed = self._build_discord_embed(item)
        if image_url:
            embed["image"] = {"url": image_url}
        self._executor.submit(self._dc_send, embed)

    def _dc_send(self, embed: dict):
        try:
            resp = self._http.post(
                self.discord_webhook_url,
                json={"embeds": [embed]},
            )
            if resp.status_code != 204 and resp.status_code != 200:
                logger.warning("Discord send failed (%d): %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Discord error: %s", e)

    def _build_discord_embed(self, item: dict) -> dict:
        platform = item.get("platform", "")
        platform_name = _PLATFORM_NAMES.get(platform, platform)
        emoji = _PLATFORM_EMOJI.get(platform, "📦")
        currency = item.get("currency", "JPY")
        price = item.get("price", 0)
        symbol = _CURRENCY_SYMBOLS.get(currency, currency + " ")

        cny_price = ""
        if price:
            rate = self._get_exchange_rate(currency)
            if rate > 0:
                cny_price = f" ≈¥{int(price * rate)}"

        name = item.get("name", "未知商品")
        url = item.get("url", "")
        found_at = item.get("found_at", "")
        seller = item.get("seller", "")
        is_auction = item.get("is_auction", False)
        is_price_drop = item.get("price_drop", False)
        is_ending = item.get("auction_ending", False)
        has_new_comment = item.get("new_comment", False)
        is_watched_seller = item.get("watched_seller", False)

        condition_raw = item.get("condition", "")
        condition = _CONDITION_MAP.get(condition_raw, condition_raw) if condition_raw else "未知"

        color = 0x5865F2
        if is_price_drop:
            color = 0xFEE75C
        elif is_ending:
            color = 0xED4245
        elif has_new_comment:
            color = 0x57F287

        title = f"[{symbol}] {name}"

        description = ""
        if is_price_drop:
            description = "💸 降价提醒"
        elif is_ending:
            description = "⏰ 拍卖即将结束"
        elif has_new_comment:
            description = "💬 留言更新"
        elif is_watched_seller:
            description = f"⭐ 关注卖家: {seller}"

        price_display = f"{symbol}{price:,}{cny_price}"
        if is_price_drop and item.get("old_price", 0):
            old_price = item["old_price"]
            rate = self._get_exchange_rate(currency)
            old_cny = f" ≈¥{int(old_price * rate)}" if (rate > 0) else ""
            price_display = f"{symbol}{old_price:,}{old_cny} → {symbol}{price:,}{cny_price}"

        platform_display = f"{emoji} {platform_name}"
        if is_auction:
            platform_display += " 🚨拍卖"

        fields = [
            {"name": "💰 价格", "value": price_display, "inline": True},
            {"name": "🌐 平台", "value": platform_display, "inline": True},
            {"name": "📊 成色", "value": condition, "inline": True},
        ]

        if found_at:
            found_time = _format_found_at(found_at)
            fields.append({"name": "⏱ 上新时间", "value": found_time, "inline": True})

        if seller:
            fields.append({"name": "👤 卖家ID", "value": seller, "inline": True})

        if url:
            fields.append({"name": "🔗 链接", "value": url, "inline": False})

        embed = {
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {"text": "二手监控助手"},
        }

        if description:
            embed["description"] = description

        if url:
            embed["url"] = url

        return embed

    def test_discord(self) -> tuple[bool, str]:
        if not self.discord_webhook_url:
            return False, "请先填写 Discord Webhook URL"

        try:
            test_embed = {
                "embeds": [{
                    "title": "[¥] 测试商品名称（示例）",
                    "description": "✅ 二手监控助手 连接成功",
                    "color": 0x57F287,
                    "fields": [
                        {"name": "💰 价格", "value": "¥10,000 ≈¥470", "inline": True},
                        {"name": "🌐 平台", "value": "🇯🇵 Mercari JP", "inline": True},
                        {"name": "📊 成色", "value": "良好", "inline": True},
                        {"name": "🔗 链接", "value": "https://example.com", "inline": False},
                        {"name": "⏱ 上新时间", "value": "2024-07-15 12:30:00", "inline": True},
                        {"name": "👤 卖家ID", "value": "test_seller", "inline": True},
                    ],
                    "footer": {"text": "二手监控助手 - 测试消息"},
                }]
            }
            resp = self._http.post(self.discord_webhook_url, json=test_embed)
            if resp.status_code in [200, 204]:
                return True, "发送成功！请检查 Discord 消息格式"
            else:
                return False, f"发送失败: HTTP {resp.status_code} - {resp.text[:200]}"
        except Exception as e:
            return False, f"连接失败: {e}"

    def process_bot_command(self, text: str) -> bool:
        text = text.strip()
        if not text.startswith("/"):
            return False

        parts = text.split(maxsplit=2)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        extra = parts[2] if len(parts) > 2 else ""

        handlers = {
            "/help": self._cmd_help,
            "/start": self._cmd_start,
            "/status": self._cmd_status,
            "/add": self._cmd_add_keyword,
            "/bseller": self._cmd_ban_seller,
            "/bword": self._cmd_ban_word,
            "/watch": self._cmd_watch_seller,
            "/unwatch": self._cmd_unwatch_seller,
            "/list": self._cmd_list,
            "/keywords": self._cmd_list_keywords,
            "/sellers": self._cmd_list_sellers,
            "/blacklist": self._cmd_list_blacklist,
            "/remove": self._cmd_remove_keyword,
            "/unban": self._cmd_unban_seller,
            "/unbword": self._cmd_unban_word,
            "/setprice": self._cmd_set_price,
            "/setinterval": self._cmd_set_interval,
            "/toggle": self._cmd_toggle_keyword,
            "/noshops": self._cmd_noshops,
            "/blockitem": self._cmd_block_item,
            "/unblockitem": self._cmd_unblock_item,
            "/blocked": self._cmd_list_blocked_items,
            "/test": self._cmd_test,
        }

        handler = handlers.get(command)
        if handler:
            try:
                response = handler(args, extra)
                self._send_bot_response(response)
                return True
            except Exception as e:
                error_msg = f"❌ 命令执行错误: {str(e)}"
                self._send_bot_response(error_msg)
                logger.error("Bot command error: %s", e, exc_info=True)
                return True
        return False

    def _send_bot_response(self, message: str):
        if not self.telegram_enabled or not self.telegram_token or not self.telegram_chat_id:
            return

        def _do_send():
            try:
                api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                resp = self._http.post(api_url, json={
                    "chat_id": self.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                })
                if resp.status_code != 200:
                    logger.warning("Bot response failed: %s", resp.text[:200])
            except Exception as e:
                logger.warning("Bot response error: %s", e)

        self._executor.submit(_do_send)

    def _cmd_help(self, args: str, extra: str) -> str:
        return (
            "*🤖 二手监控助手 命令列表*\n\n"
            "*📋 基本命令*\n"
            "/help - 显示此帮助信息\n"
            "/status - 查看监控状态\n"
            "/test - 发送测试消息\n\n"
            "*🔍 关键词管理*\n"
            "/add `<关键词>` `[平台]` `[最低价]` `[最高价]` - 添加监控关键词\n"
            "/remove `<关键词>` - 删除关键词\n"
            "/keywords - 列出所有关键词\n"
            "/setprice `<关键词>` `<最低价>` `<最高价>` - 设置价格区间\n"
            "/setinterval `<关键词>` `<秒数>` - 设置轮询间隔\n"
            "/toggle `<关键词>` - 启用/禁用关键词\n"
            "/noshops `<关键词>` `<yes/no>` - 排除商家商品\n\n"
            "*👤 卖家管理*\n"
            "/watch `<卖家ID>` `[平台]` - 关注卖家\n"
            "/unwatch `<卖家ID>` - 取消关注卖家\n"
            "/sellers - 列出关注的卖家\n\n"
            "*🚫 黑名单管理*\n"
            "/bseller `<卖家ID>` - 屏蔽卖家\n"
            "/unban `<卖家ID>` - 取消屏蔽卖家\n"
            "/bword `<关键词>` - 屏蔽词\n"
            "/unbword `<关键词>` - 取消屏蔽词\n"
            "/blockitem `<商品ID>` - 屏蔽商品\n"
            "/unblockitem `<商品ID>` - 取消屏蔽商品\n"
            "/blocked - 列出屏蔽商品\n"
            "/blacklist - 列出黑名单(卖家+词)\n\n"
            "*📊 信息查询*\n"
            "/list - 显示所有配置摘要\n\n"
            "*平台代码*: mercari_jp, bunjang, paypay_fleamarket,\n"
            "fril, yahoo_auctions, carousell"
        )

    def _cmd_start(self, args: str, extra: str) -> str:
        welcome_msg = args if args else "欢迎使用二手监控助手！"
        return (
            f"*✨ {welcome_msg}*\n\n"
            "我可以通过命令帮您管理监控任务。\n"
            "输入 /help 查看所有可用命令。\n\n"
            "💡 *快速开始:*\n"
            "• `/add canon` - 添加关键词\n"
            "• `/bseller 12345` - 屏蔽卖家\n"
            "• `/status` - 查看状态"
        )

    def _cmd_status(self, args: str, extra: str) -> str:
        if not self.db:
            return "❌ 数据库未连接"

        keywords = self.db.get_keywords(None)
        sellers = self.db.get_watched_sellers()
        items = self.db.get_watched_items()
        blocked_items = self.db.get_blocked_items()
        blacklist_raw = self.db.get_setting("seller_blacklist", "")
        blacklist = [s.strip() for s in blacklist_raw.splitlines() if s.strip()]
        bword_raw = self.db.get_setting("blocked_words", "")
        bwords = [w.strip() for w in bword_raw.splitlines() if w.strip()]

        interval = self.db.get_setting("poll_interval", "0.3")
        tg_status = "✅ 已启用" if self.telegram_enabled else "❌ 未启用"

        return (
            "*📊 监控状态概览*\n\n"
            f"*🔍 关键词数量:* `{len(keywords)}` 个\n"
            f"*👤 关注卖家:* `{len(sellers)}` 个\n"
            f"*📦 关注商品:* `{len(items)}` 个\n"
            f"*🚫 屏蔽卖家:* `{len(blacklist)}` 个\n"
            f"*🚫 屏蔽词语:* `{len(bwords)}` 个\n"
            f"*🚫 屏蔽商品:* `{len(blocked_items)}` 个\n"
            f"*⏱ 轮询间隔:* `{interval}s`\n"
            f"*📱 Telegram:* {tg_status}\n\n"
            "💡 输入 /list 查看详细信息"
        )

    def _cmd_add_keyword(self, args: str, extra: str) -> str:
        if not args:
            return ("❌ 用法: `/add <关键词> [平台] [最低价] [最高价]`\n"
                    "示例: `/add canon mercari_jp 1000 5000`\n"
                    "示例: `/add ps5` (默认平台Mercari, 不限价格)\n"
                    "示例: `/add ポケモンカード mercari_jp 500` (仅最低价)")

        parts = args.strip().split()
        platform = "mercari_jp"
        min_price = 0
        max_price = 0
        keyword = ""

        last_part = parts[-1] if parts else ""
        if last_part in _PLATFORM_NAMES:
            platform = last_part
            keyword = " ".join(parts[:-1])
        else:
            last_two = " ".join(parts[-2:]) if len(parts) >= 2 else ""
            if last_two in _PLATFORM_NAMES:
                platform = last_two
                keyword = " ".join(parts[:-2])
            else:
                keyword = " ".join(parts)

        if extra:
            extra_parts = extra.strip().split()
            try:
                if len(extra_parts) >= 2:
                    min_price = int(extra_parts[0])
                    max_price = int(extra_parts[1])
                elif len(extra_parts) == 1:
                    min_price = int(extra_parts[0])
            except (ValueError, TypeError):
                pass

        if not keyword:
            return "❌ 请输入关键词"

        if not self.db:
            return "❌ 数据库未连接"

        ok = self.db.add_keyword(keyword, platform, min_price, max_price)
        if ok:
            platform_name = _PLATFORM_NAMES.get(platform, platform)
            price_info = ""
            if min_price and max_price:
                price_info = f"\n💰 价格区间: ¥{min_price:,} ~ ¥{max_price:,}"
            elif min_price:
                price_info = f"\n💰 最低价格: ¥{min_price:,}"
            return (
                f"✅ *关键词添加成功!*\n\n"
                f"🔑 关键词: `{keyword}`\n"
                f"🌐 平台: {platform_name}"
                f"{price_info}\n\n"
                "💡 已开始监控该关键词\n"
                "💡 使用 /setprice 修改价格区间\n"
                "💡 使用 /bword 添加屏蔽词"
            )
        else:
            return f"❌ 关键词 '{keyword}' 已存在或添加失败"

    def _cmd_remove_keyword(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/remove <关键词>`\n示例: `/remove canon`"

        keyword = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        ok = self.db.delete_keyword(keyword)
        if ok:
            return f"✅ 关键词 `{keyword}` 已删除"
        else:
            return f"❌ 未找到关键词 '{keyword}'"

    def _cmd_ban_seller(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/bseller <卖家ID>`\n示例: `/bseller 710134275`"

        seller_id = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        current = self.db.get_setting("seller_blacklist", "")
        sellers = [s.strip() for s in current.splitlines() if s.strip()]

        if seller_id in sellers:
            return f"⚠️ 卖家 `{seller_id}` 已在黑名单中"

        sellers.append(seller_id)
        self.db.set_setting("seller_blacklist", "\n".join(sellers))

        return (
            f"✅ *卖家已屏蔽!*\n\n"
            f"🚫 卖家ID: `{seller_id}`\n\n"
            "💡 该卖家的商品将不再推送"
        )

    def _cmd_unban_seller(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/unban <卖家ID>`\n示例: `/unban 710134275`"

        seller_id = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        current = self.db.get_setting("seller_blacklist", "")
        sellers = [s.strip() for s in current.splitlines() if s.strip()]

        if seller_id not in sellers:
            return f"⚠️ 卖家 `{seller_id}` 不在黑名单中"

        sellers.remove(seller_id)
        self.db.set_setting("seller_blacklist", "\n".join(sellers))

        return f"✅ 卖家 `{seller_id}` 已从黑名单移除"

    def _cmd_ban_word(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/bword <屏蔽词>`\n示例: `/bword 假货`"

        word = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        current = self.db.get_setting("blocked_words", "")
        words = [w.strip() for w in current.splitlines() if w.strip()]

        if word in words:
            return f"⚠️ 屏蔽词 '{word}' 已存在"

        words.append(word)
        self.db.set_setting("blocked_words", "\n".join(words))

        return (
            f"✅ *屏蔽词已添加!*\n\n"
            f"🚫 屏蔽词: `{word}`\n\n"
            "💡 包含该词的商品将不推送"
        )

    def _cmd_unban_word(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/unbword <屏蔽词>`\n示例: `/unbword 假货`"

        word = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        current = self.db.get_setting("blocked_words", "")
        words = [w.strip() for w in current.splitlines() if w.strip()]

        if word not in words:
            return f"⚠️ 屏蔽词 '{word}' 不存在"

        words.remove(word)
        self.db.set_setting("blocked_words", "\n".join(words))

        return f"✅ 屏蔽词 '{word}' 已移除"

    def _cmd_watch_seller(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/watch <卖家ID> [平台]`\n示例: `/watch 710134275` 或 `/watch 12345 bunjang`"

        seller_id = args.strip()
        platform = extra.strip() if extra and extra in _PLATFORM_NAMES else "mercari_jp"

        if not self.db:
            return "❌ 数据库未连接"

        alias = ""
        ok = self.db.add_watched_seller(seller_id, platform, alias)
        if ok:
            platform_name = _PLATFORM_NAMES.get(platform, platform)
            return (
                f"✅ *卖家关注成功!*\n\n"
                f"👤 卖家ID: `{seller_id}`\n"
                f"🌐 平台: {platform_name}\n\n"
                "💡 该卖家的新商品会优先推送"
            )
        else:
            return f"❌ 卖家 '{seller_id}' 已在关注列表或添加失败"

    def _cmd_unwatch_seller(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/unwatch <卖家ID>`\n示例: `/unwatch 710134275`"

        seller_id = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        ok = self.db.remove_watched_seller(seller_id)
        if ok:
            return f"✅ 卖家 `{seller_id}` 已取消关注"
        else:
            return f"❌ 未找到关注卖家 '{seller_id}'"

    def _cmd_list_keywords(self, args: str, extra: str) -> str:
        if not self.db:
            return "❌ 数据库未连接"

        keywords = self.db.get_keywords(None)

        if not keywords:
            return "📭 暂无监控关键词\n\n使用 /add <关键词> 添加"

        lines = ["*🔍 监控关键词列表*\n"]
        for i, kw in enumerate(keywords[:20], 1):
            keyword = kw.get("keyword", "")
            platform = kw.get("platform", "")
            platform_name = _PLATFORM_NAMES.get(platform, platform)
            status = "▶️" if kw.get("enabled") else "⏸️"
            lines.append(f"{i}. {status} `{keyword}` - {platform_name}")

        if len(keywords) > 20:
            lines.append(f"\n... 还有 {len(keywords) - 20} 个关键词")

        lines.append(f"\n*共 {len(keywords)} 个关键词*")
        return "\n".join(lines)

    def _cmd_list_sellers(self, args: str, extra: str) -> str:
        if not self.db:
            return "❌ 数据库未连接"

        sellers = self.db.get_watched_sellers()

        if not sellers:
            return "📭 暂无关注卖家\n\n使用 /watch <卖家ID> 添加"

        lines = ["*👤 关注卖家列表*\n"]
        for i, seller in enumerate(sellers[:20], 1):
            sid = seller.get("seller_id", "")
            platform = seller.get("platform", "")
            platform_name = _PLATFORM_NAMES.get(platform, platform)
            alias = seller.get("alias", "")
            display = alias if alias else sid[:12]
            lines.append(f"{i}. 👤 `{display}` - {platform_name}")

        if len(sellers) > 20:
            lines.append(f"\n... 还有 {len(sellers) - 20} 个卖家")

        lines.append(f"\n*共 {len(sellers)} 个卖家*")
        return "\n".join(lines)

    def _cmd_list_blacklist(self, args: str, extra: str) -> str:
        if not self.db:
            return "❌ 数据库未连接"

        blacklist_raw = self.db.get_setting("seller_blacklist", "")
        sellers = [s.strip() for s in blacklist_raw.splitlines() if s.strip()]

        bword_raw = self.db.get_setting("blocked_words", "")
        words = [w.strip() for w in bword_raw.splitlines() if w.strip()]

        lines = ["*🚫 黑名单列表*\n"]

        if sellers:
            lines.append("*👤 屏蔽卖家:*")
            for i, sid in enumerate(sellers[:10], 1):
                lines.append(f"  {i}. `{sid}`")
            if len(sellers) > 10:
                lines.append(f"  ... 还有 {len(sellers) - 10} 个")

        if words:
            lines.append("\n*🚫 屏蔽词语:*")
            for i, word in enumerate(words[:10], 1):
                lines.append(f"  {i}. `{word}`")
            if len(words) > 10:
                lines.append(f"  ... 还有 {len(words) - 10} 个")

        if not sellers and not words:
            lines.append("📭 黑名单为空")

        total = len(sellers) + len(words)
        lines.append(f"\n*共 {total} 条规则*")
        return "\n".join(lines)

    def _cmd_list(self, args: str, extra: str) -> str:
        status_text = self._cmd_status("", "") 
        keywords_preview = self._cmd_list_keywords("", "") 
        sellers_preview = self._cmd_list_sellers("", "") 

        return (
            f"{status_text}\n\n"
            "---\n\n"
            f"{keywords_preview}\n\n"
            "---\n\n"
            f"{sellers_preview}"
        )

    def _cmd_set_price(self, args: str, extra: str) -> str:
        if not args or not extra:
            return ("❌ 用法: `/setprice <关键词> <最低价> <最高价>`\n"
                    "示例: `/setprice canon 1000 5000`\n"
                    "示例: `/setprice ps5 0 30000` (取消价格限制)")

        keyword = args.strip()
        parts = extra.strip().split()
        try:
            min_price = int(parts[0]) if len(parts) >= 1 else 0
            max_price = int(parts[1]) if len(parts) >= 2 else 0
        except (ValueError, TypeError):
            return "❌ 价格必须是数字\n示例: `/setprice canon 1000 5000`"

        if not self.db:
            return "❌ 数据库未连接"

        keywords = self.db.get_keywords(None)
        matched = [kw for kw in keywords if kw["keyword"].lower() == keyword.lower()]
        if not matched:
            return f"❌ 未找到关键词 '{keyword}'\n使用 /keywords 查看所有关键词"

        kw = matched[0]
        ok = self.db.update_keyword(kw["id"], min_price=min_price, max_price=max_price)
        if ok:
            if min_price or max_price:
                price_str = f"¥{min_price:,} ~ ¥{max_price:,}" if max_price else f"≥ ¥{min_price:,}"
                return f"✅ 关键词 `{keyword}` 价格区间已设为 `{price_str}`"
            else:
                return f"✅ 关键词 `{keyword}` 已取消价格限制"
        else:
            return "❌ 设置失败"

    def _cmd_set_interval(self, args: str, extra: str) -> str:
        if not args:
            return ("❌ 用法: `/setinterval <关键词> <秒数>`\n"
                    "示例: `/setinterval canon 0.5` (0.5秒高频)\n"
                    "示例: `/setinterval ps5 5` (5秒低频)\n"
                    "设为 0 恢复默认间隔")

        keyword = args.strip()
        try:
            interval = float(extra.strip()) if extra else 0
        except (ValueError, TypeError):
            return "❌ 间隔秒数必须是数字\n示例: `/setinterval canon 0.5`"

        if interval < 0:
            return "❌ 间隔不能为负数"
        if interval > 0 and interval < 0.05:
            return "❌ 最小间隔为 0.05 秒"
        if interval > 60:
            return "❌ 最大间隔为 60 秒"

        if not self.db:
            return "❌ 数据库未连接"

        keywords = self.db.get_keywords(None)
        matched = [kw for kw in keywords if kw["keyword"].lower() == keyword.lower()]
        if not matched:
            return f"❌ 未找到关键词 '{keyword}'"

        kw = matched[0]
        ok = self.db.update_keyword(kw["id"], poll_interval=interval)
        if ok:
            if interval > 0:
                return f"✅ 关键词 `{keyword}` 轮询间隔已设为 `{interval}s`"
            else:
                return f"✅ 关键词 `{keyword}` 已恢复默认间隔"
        else:
            return "❌ 设置失败"

    def _cmd_toggle_keyword(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/toggle <关键词>`\n示例: `/toggle canon`"

        keyword = args.strip()

        if not self.db:
            return "❌ 数据库未连接"

        keywords = self.db.get_keywords(None)
        matched = [kw for kw in keywords if kw["keyword"].lower() == keyword.lower()]
        if not matched:
            return f"❌ 未找到关键词 '{keyword}'"

        kw = matched[0]
        new_state = not kw.get("enabled", True)
        self.db.toggle_keyword(kw["id"], new_state)
        state_text = "▶️ 启用" if new_state else "⏸️ 暂停"
        return f"✅ 关键词 `{keyword}` 已{state_text}"

    def _cmd_noshops(self, args: str, extra: str) -> str:
        if not args:
            return ("❌ 用法: `/noshops <关键词> <yes/no>`\n"
                    "示例: `/noshops canon yes` (排除商家商品)\n"
                    "示例: `/noshops ps5 no` (恢复包含商家)")

        keyword = args.strip()
        exclude = extra.strip().lower() if extra else ""
        if exclude not in ("yes", "no", "y", "n", "1", "0"):
            return "❌ 请指定 yes 或 no\n示例: `/noshops canon yes`"

        noshops = exclude in ("yes", "y", "1")

        if not self.db:
            return "❌ 数据库未连接"

        keywords = self.db.get_keywords(None)
        matched = [kw for kw in keywords if kw["keyword"].lower() == keyword.lower()]
        if not matched:
            return f"❌ 未找到关键词 '{keyword}'"

        kw = matched[0]
        ok = self.db.update_keyword(kw["id"], noshops=noshops)
        if ok:
            state = "排除商家" if noshops else "包含商家"
            return f"✅ 关键词 `{keyword}` 已设为 `{state}`"
        else:
            return "❌ 设置失败"

    def _cmd_block_item(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/blockitem <商品ID>`\n示例: `/blockitem m12345678901`"

        item_id = args.strip()
        platform = extra.strip() if extra and extra in _PLATFORM_NAMES else "mercari_jp"

        if not self.db:
            return "❌ 数据库未连接"

        ok = self.db.add_blocked_item(item_id, platform, "手动屏蔽")
        if ok:
            platform_name = _PLATFORM_NAMES.get(platform, platform)
            return (
                f"✅ *商品已屏蔽!*\n\n"
                f"🚫 商品ID: `{item_id}`\n"
                f"🌐 平台: {platform_name}\n\n"
                "💡 该商品不再推送"
            )
        else:
            return f"⚠️ 商品 `{item_id}` 已在屏蔽列表中"

    def _cmd_unblock_item(self, args: str, extra: str) -> str:
        if not args:
            return "❌ 用法: `/unblockitem <商品ID>`\n示例: `/unblockitem m12345678901`"

        item_id = args.strip()
        platform = extra.strip() if extra and extra in _PLATFORM_NAMES else "mercari_jp"

        if not self.db:
            return "❌ 数据库未连接"

        self.db.remove_blocked_item(item_id, platform)
        return f"✅ 商品 `{item_id}` 已取消屏蔽"

    def _cmd_list_blocked_items(self, args: str, extra: str) -> str:
        if not self.db:
            return "❌ 数据库未连接"

        items = self.db.get_blocked_items()
        if not items:
            return "📭 暂无屏蔽商品\n\n使用 /blockitem <商品ID> 添加"

        lines = ["*🚫 屏蔽商品列表*\n"]
        for i, item in enumerate(items[:20], 1):
            iid = item.get("item_id", "")
            reason = item.get("reason", "")
            r = f" - {reason}" if reason else ""
            lines.append(f"{i}. `{iid}`{r}")

        if len(items) > 20:
            lines.append(f"\n... 还有 {len(items) - 20} 个")

        lines.append(f"\n*共 {len(items)} 个屏蔽商品*")
        return "\n".join(lines)

    def _cmd_test(self, args: str, extra: str) -> str:
        success, msg = self.test_telegram()
        if success:
            return "✅ 测试消息已发送！\n\n请检查您的 Telegram 是否收到消息"
        else:
            return f"❌ 测试失败: {msg}"