import io
import time
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from PIL import Image, ImageTk
import httpx

from .styles import COLORS, FONTS, PLATFORM_COLORS, CURRENCY_SYMBOLS
from src.monitors import PLATFORM_NAMES

UNAVAILABLE_PLATFORMS = set()


def relative_time(dt_str: str) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc).astimezone()
    except (ValueError, TypeError):
        return dt_str[:16] if len(dt_str) >= 16 else dt_str
    now = datetime.now(dt.tzinfo)
    diff = (now - dt).total_seconds()
    if diff < 0:
        return "刚刚"
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    if diff < 604800:
        return f"{int(diff // 86400)}天前"
    return dt_str[:10]


class ImageCache:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, max_size=300, max_concurrent=5):
        self._cache = {}
        self._max_size = max_size
        self._lock = threading.Lock()
        self._loading = set()
        self._placeholder = None
        self._root = None
        self._semaphore = threading.Semaphore(max_concurrent)
        self._pending = []

    def set_root(self, root):
        self._root = root

    def _make_placeholder(self):
        img = Image.new("RGBA", (64, 64), (240, 242, 245, 255))
        return ImageTk.PhotoImage(img)

    def get_placeholder(self):
        if self._placeholder is None:
            self._placeholder = self._make_placeholder()
        return self._placeholder

    def get(self, url, callback=None):
        if not url:
            return self.get_placeholder()
        with self._lock:
            if url in self._cache:
                return self._cache[url]
            if url in self._loading:
                return self.get_placeholder()
            if callback and self._root:
                self._loading.add(url)
                threading.Thread(
                    target=self._load, args=(url, callback), daemon=True
                ).start()
        return self.get_placeholder()

    def _load(self, url, callback):
        with self._semaphore:
            try:
                resp = httpx.get(url, timeout=5.0, follow_redirects=True)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content))
                img = img.convert("RGBA")
                img.thumbnail((56, 56), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                with self._lock:
                    if len(self._cache) >= self._max_size:
                        oldest_key = next(iter(self._cache))
                        del self._cache[oldest_key]
                    self._cache[url] = photo
                    self._loading.discard(url)
                if self._root:
                    self._root.after(0, lambda: callback(url, photo))
            except Exception:
                with self._lock:
                    self._loading.discard(url)


class StatusBar(ttk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._labels = {}
        self._warning_var = tk.StringVar(value="")
        self._build()

    def _build(self):
        inner = tk.Frame(self, bg=COLORS["bg2"], height=32)
        inner.pack(fill="x", padx=12, pady=5)
        inner.pack_propagate(False)

        self._dot_canvas = tk.Canvas(inner, width=8, height=8,
                                     bg=COLORS["bg2"], highlightthickness=0)
        self._dot_canvas.pack(side="left", padx=(0, 6))
        self._dot = self._dot_canvas.create_oval(1, 1, 7, 7, fill=COLORS["text3"], outline="")

        self._status_var = tk.StringVar(value="就绪")
        tk.Label(inner, textvariable=self._status_var,
                 bg=COLORS["bg2"], fg=COLORS["text"],
                 font=FONTS["small"]).pack(side="left")

        self._warning_label = tk.Label(inner, textvariable=self._warning_var,
                                       bg=COLORS["bg2"], fg="#e6a817",
                                       font=FONTS["tiny"])
        
        self._last_check_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=self._last_check_var,
                 bg=COLORS["bg2"], fg=COLORS["text3"],
                 font=FONTS["tiny"]).pack(side="right", padx=(0, 0))

        self._stats_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=self._stats_var,
                 bg=COLORS["bg2"], fg=COLORS["text2"],
                 font=FONTS["small"]).pack(side="right", padx=16)

    def set_status(self, msg: str):
        self._status_var.set(msg)

    def set_warning(self, msg: str):
        self._warning_var.set(msg)
        self._warning_label.pack(side="left", padx=(12, 0))

    def clear_warning(self):
        self._warning_var.set("")
        self._warning_label.pack_forget()

    def set_stats(self, total: int, today: int):
        self._stats_var.set(f"总计 {total:,}  ·  今日 {today:,}")

    def set_last_check(self, t: str):
        self._last_check_var.set(f"上次检查: {t}" if t else "")

    def set_running(self, running: bool):
        color = COLORS["success"] if running else COLORS["text3"]
        self._dot_canvas.itemconfigure(self._dot, fill=color)


class StatsCard(tk.Frame):
    def __init__(self, parent, icon: str, label: str, value: str = "0",
                 color: str = None, **kw):
        super().__init__(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                         highlightthickness=1, **kw)
        self._value_var = tk.StringVar(value=value)
        self._color = color or COLORS["accent"]
        self._build(icon, label)

    def _build(self, icon, label):
        content = tk.Frame(self, bg=COLORS["card"])
        content.pack(fill="both", expand=True, padx=16, pady=14)

        tk.Label(content, text=icon, bg=COLORS["card"],
                 font=("Segoe UI", 18), fg=self._color).pack(anchor="w")

        tk.Label(content, textvariable=self._value_var, bg=COLORS["card"],
                 font=FONTS["stat_value"], fg=COLORS["text"]).pack(anchor="w", pady=(4, 0))

        tk.Label(content, text=label, bg=COLORS["card"],
                 font=FONTS["stat_label"], fg=COLORS["text2"]).pack(anchor="w")

    def set_value(self, value):
        self._value_var.set(str(value))


class PlatformBadge(tk.Label):
    def __init__(self, parent, platform: str, compact=False, **kw):
        color = PLATFORM_COLORS.get(platform, COLORS["accent"])
        name = PLATFORM_NAMES.get(platform, platform)
        if compact:
            short = {"mercari_jp": "MC", "bunjang": "BJ", "paypay_fleamarket": "PP",
                     "fril": "FR", "yahoo_auctions": "YA", "carousell": "CR"}
            name = short.get(platform, name[:2])
        font = FONTS["tiny"] if compact else FONTS["small"]
        padx = 5 if compact else 8
        pady = 1 if compact else 3
        super().__init__(parent, text=name, bg=color, fg="white",
                         font=font, padx=padx, pady=pady, relief="flat", **kw)


class ItemCard(tk.Frame):
    def __init__(self, parent, item: dict, open_cb=None, **kw):
        super().__init__(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                         highlightthickness=1, cursor="hand2", **kw)
        self.item = item
        self._open_cb = open_cb
        self._photo = None
        self._build()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._bind_click_recursive(self)

    def _bind_click_recursive(self, widget):
        widget.bind("<Button-1>", self._on_click)
        for child in widget.winfo_children():
            self._bind_click_recursive(child)

    def _on_enter(self, e):
        self.configure(highlightbackground=COLORS["accent"], highlightthickness=2)
        self._set_bg_recursive(self, COLORS["card_hover"])

    def _on_leave(self, e):
        self.configure(highlightbackground=COLORS["border"], highlightthickness=1)
        self._set_bg_recursive(self, COLORS["card"])

    def _set_bg_recursive(self, widget, bg_color):
        try:
            widget.configure(bg=bg_color)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            if isinstance(child, (tk.Label, tk.Frame)):
                self._set_bg_recursive(child, bg_color)

    def _on_click(self, e):
        if self._open_cb and self.item.get("url"):
            self._open_cb(self.item["url"])

    def _build(self):
        outer = tk.Frame(self, bg=COLORS["card"])
        outer.pack(fill="x", padx=12, pady=10)

        img_url = self.item.get("image_url", "")
        cache = ImageCache.get_instance()
        placeholder = cache.get_placeholder()
        img_frame = tk.Frame(outer, bg=COLORS["bg3"], width=64, height=64)
        img_frame.pack(side="left", padx=(0, 12))
        img_frame.pack_propagate(False)
        self._img_label = tk.Label(img_frame, image=placeholder, bg=COLORS["bg3"],
                                   relief="flat", bd=0)
        self._img_label.pack(expand=True)
        if img_url:
            cache.get(img_url, callback=self._on_image_loaded)

        right = tk.Frame(outer, bg=COLORS["card"])
        right.pack(side="left", fill="both", expand=True)

        name = self.item.get("name", "未知商品")
        if len(name) > 70:
            name = name[:70] + "…"
        name_row = tk.Frame(right, bg=COLORS["card"])
        name_row.pack(fill="x")
        tk.Label(name_row, text=name, bg=COLORS["card"], fg=COLORS["text"],
                 font=FONTS["item_name"], anchor="w",
                 wraplength=480, justify="left").pack(side="left")

        tags_row = tk.Frame(right, bg=COLORS["card"])
        tags_row.pack(fill="x", pady=(4, 0))

        is_auction = self.item.get("is_auction", False)
        is_price_drop = self.item.get("price_drop", False)
        watched_seller = self.item.get("watched_seller", False)

        if is_auction:
            tk.Label(tags_row, text="🚨拍卖", bg=COLORS["danger_light"],
                     fg=COLORS["danger"], font=FONTS["tiny"],
                     padx=4, pady=1).pack(side="left", padx=(0, 4))
        if is_price_drop:
            tk.Label(tags_row, text="📉降价", bg=COLORS["warning_light"],
                     fg=COLORS["warning"], font=FONTS["tiny"],
                     padx=4, pady=1).pack(side="left", padx=(0, 4))
        if watched_seller:
            tk.Label(tags_row, text="⭐关注", bg=COLORS["accent_bg"],
                     fg=COLORS["accent"], font=FONTS["tiny"],
                     padx=4, pady=1).pack(side="left", padx=(0, 4))

        bottom = tk.Frame(right, bg=COLORS["card"])
        bottom.pack(fill="x", pady=(6, 0))

        price = self.item.get("price", 0)
        currency = self.item.get("currency", "JPY")
        symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
        tk.Label(bottom, text=f"{symbol}{price:,}", bg=COLORS["card"],
                 fg=COLORS["danger"], font=FONTS["price"]).pack(side="left")

        PlatformBadge(bottom, self.item.get("platform", ""), compact=True).pack(
            side="left", padx=(12, 0))

        condition = self.item.get("condition", "")
        if condition:
            cond_text = condition[:15] + "..." if len(condition) > 15 else condition
            tk.Label(bottom, text=cond_text, bg=COLORS["card"],
                     fg=COLORS["text3"], font=FONTS["tiny"]).pack(side="left", padx=(8, 0))

        meta_row = tk.Frame(right, bg=COLORS["card"])
        meta_row.pack(fill="x", pady=(2, 0))

        kw_text = self.item.get("keyword", "")
        if kw_text:
            tk.Label(meta_row, text=f"#{kw_text}", bg=COLORS["card"],
                     fg=COLORS["accent"], font=FONTS["small"]).pack(side="left")

        found_at = self.item.get("found_at", "")
        time_text = relative_time(found_at)
        if time_text:
            tk.Label(meta_row, text=time_text, bg=COLORS["card"],
                     fg=COLORS["text3"], font=FONTS["tiny"]).pack(side="left", padx=(8, 0))

        if self._open_cb and self.item.get("url"):
            tk.Label(meta_row, text="查看 →", bg=COLORS["card"],
                     fg=COLORS["accent"], font=FONTS["small"],
                     cursor="hand2").pack(side="right")

    def _on_image_loaded(self, url, photo):
        try:
            self._photo = photo
            self._img_label.configure(image=photo)
        except tk.TclError:
            pass


class PlatformStatusItem(tk.Frame):
    def __init__(self, parent, platform: str, **kw):
        super().__init__(parent, bg=COLORS["bg2"], **kw)
        self._platform = platform
        name = PLATFORM_NAMES.get(platform, platform)
        color = PLATFORM_COLORS.get(platform, COLORS["accent"])
        unavailable = platform in UNAVAILABLE_PLATFORMS

        dot_color = COLORS["danger"] if unavailable else COLORS["text3"]
        self._dot_canvas = tk.Canvas(self, width=8, height=8,
                                     bg=COLORS["bg2"], highlightthickness=0)
        self._dot_canvas.pack(side="left", padx=(12, 8), pady=6)
        self._dot = self._dot_canvas.create_oval(1, 1, 7, 7, fill=dot_color, outline="")

        tk.Label(self, text=name, bg=COLORS["bg2"], fg=COLORS["text2"],
                 font=FONTS["small"]).pack(side="left")

        if unavailable:
            tk.Label(self, text="不可用", bg=COLORS["bg2"], fg=COLORS["danger"],
                     font=FONTS["tiny"]).pack(side="right", padx=(0, 12))

        self._active = False
        self._unavailable = unavailable

    def set_active(self, active: bool):
        self._active = active
        if self._unavailable:
            return
        color = COLORS["success"] if active else COLORS["text3"]
        self._dot_canvas.itemconfigure(self._dot, fill=color)


class EmptyState(tk.Frame):
    def __init__(self, parent, icon: str = "📦", title: str = "暂无数据",
                 subtitle: str = "", **kw):
        super().__init__(parent, bg=COLORS["bg"], **kw)

        container = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                            highlightthickness=1, padx=40, pady=30)
        container.pack(expand=True, pady=20)

        tk.Label(container, text=icon, bg=COLORS["card"], font=("Segoe UI", 42)).pack(pady=(0, 12))
        tk.Label(container, text=title, bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["heading"]).pack()
        if subtitle:
            tk.Label(container, text=subtitle, bg=COLORS["card"], fg=COLORS["text3"],
                     font=FONTS["small"], wraplength=320).pack(pady=(6, 0))


class LogPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=COLORS["bg"], **kw)
        self._error_counts: dict[str, int] = {}
        self._last_error_time: dict[str, float] = {}
        self._error_cooldown = 30.0
        self._build()

    def _build(self):
        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(header, text="运行日志", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(side="left")
        
        btn_frame = tk.Frame(header, bg=COLORS["bg"])
        btn_frame.pack(side="right")
        
        tk.Button(btn_frame, text="常见问题", bg=COLORS["bg3"], fg=COLORS["info"],
                  font=FONTS["small"], bd=0, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self._show_help).pack(side="right", padx=(4, 0))
        tk.Button(btn_frame, text="清空日志", bg=COLORS["bg3"], fg=COLORS["text2"],
                  font=FONTS["small"], bd=0, relief="flat", padx=10, pady=3,
                  cursor="hand2", command=self.clear).pack(side="right")

        text_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                             highlightthickness=1)
        text_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self.text = tk.Text(
            text_frame, bg=COLORS["card"], fg=COLORS["text2"],
            font=FONTS["mono"], bd=0, relief="flat", state="disabled",
            wrap="word", height=12, insertbackground=COLORS["text"],
            selectbackground=COLORS["accent_bg"],
            padx=12, pady=8,
        )
        scroll = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.text.tag_configure("error", foreground=COLORS["danger"])
        self.text.tag_configure("success", foreground=COLORS["success"])
        self.text.tag_configure("warning", foreground=COLORS["warning"])
        self.text.tag_configure("info", foreground=COLORS["info"])
        self.text.tag_configure("help", foreground="#6B7280", font=("Microsoft YaHei UI", 9))

    _ERROR_HINTS = {
        "429": ("请求过于频繁，平台暂时限流", 
               "系统会自动降低请求频率。如持续出现，请尝试：\n"
               "  • 稍后重启监控\n"
               "  • 检查是否使用了代理\n"
               "  • 在设置中增大该平台的轮询间隔"),
        "403": ("被平台反爬虫系统拦截",
               "该平台检测到自动化访问。建议：\n"
               "  • 使用代理（设置→代理配置）\n"
               "  • 增大轮询间隔到 5-10 秒\n"
               "  • 该平台可能暂时不可用"),
        "超时": ("网络请求超时",
               "网络连接不稳定或平台响应慢。建议：\n"
               "  • 检查网络连接\n"
               "  • 如使用代理，确认代理可用\n"
               "  • 尝试更换代理服务器\n"
               "  • 如仅个别平台超时，可能是该平台服务器繁忙"),
        "限速": ("触发平台频率限制",
               "请求速度过快被限制。系统正在自动降频处理。\n"
               "无需操作，等待几分钟后会自动恢复。"),
        "封禁": ("IP 被临时封禁",
               "当前 IP 已被平台临时封禁。建议：\n"
               "  • 更换代理 IP\n"
               "  • 等待 1-2 小时后重试\n"
               "  • 使用多个代理分散请求"),
        "Cloudflare": ("Cloudflare 防护拦截",
               "该平台使用 Cloudflare 高级防护。\n"
               "  • 当前技术手段难以绕过\n"
               "  • 建议暂时禁用该平台监控"),
        "获取失败": ("数据获取失败",
               "无法从该平台获取数据。可能原因：\n"
               "  • 平台临时维护或服务器故障\n"
               "  • 网络连接不稳定\n"
               "  • 该平台的页面结构已变更\n"
               "建议稍后重试，或增大轮询间隔"),
        "请求失败": ("API 请求失败",
               "向平台发送请求时出错。建议：\n"
               "  • 检查网络连接\n"
               "  • 确认代理设置正确\n"
               "  • 等待几分钟后自动恢复"),
        "备用接口也失败": ("备用接口同样失败",
               "主接口和备用接口都无法访问。说明：\n"
               "  • 该平台可能全面不可用\n"
               "  • 网络环境受限（如公司防火墙）\n"
               "建议检查网络或暂时关闭该平台"),
        "unknown": ("未知错误",
               "这是一个未知错误。建议：\n"
               "  • 检查网络连接\n"
               "  • 稍后重启监控\n"
               "  • 如持续出现，请联系技术支持"),
    }

    def _classify_error(self, msg: str) -> tuple[str, str]:
        for key, (hint, _) in self._ERROR_HINTS.items():
            if key in msg:
                return key, hint
        if "失败" in msg or "错误" in msg or "error" in msg.lower():
            return "unknown", ""
        return "", ""

    def append(self, msg: str):
        self.text.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        tag = ""
        lower = msg.lower()
        
        is_error = "错误" in lower or "失败" in lower or "error" in lower or "429" in msg or "403" in msg
        
        if is_error:
            tag = "error"
            err_key, hint = self._classify_error(msg)
            
            now = time.time()
            if err_key and err_key in self._last_error_time:
                if now - self._last_error_time[err_key] < self._error_cooldown:
                    self._error_counts[err_key] = self._error_counts.get(err_key, 1) + 1
                    self.text.configure(state="disabled")
                    return
                else:
                    count = self._error_counts.get(err_key, 1)
                    if count > 1:
                        self.text.insert("end", f"[{ts}] ⚠️ 上述错误已重复 {count} 次（已合并显示）\n", "warning")
                    self._error_counts[err_key] = 1
            
            if err_key:
                self._last_error_time[err_key] = now
                _, solution = self._ERROR_HINTS[err_key]
                if not solution:
                    solution = ("这是一个未知错误。建议：\n"
                              "  • 检查网络连接\n"
                              "  • 稍后重启监控\n"
                              "  • 如持续出现，请联系技术支持")
                self.text.insert("end", f"[{ts}] {msg}\n", tag)
                self.text.insert("end", f"  💡 提示: {solution}\n", "help")
                self.text.configure(state="disabled")
                return
                
        elif "新商品" in msg or "启动" in msg:
            tag = "success"
        elif "不可用" in lower or "拦截" in lower:
            tag = "warning"
        elif "开始" in msg or "完成" in msg:
            tag = "info"
            
        self.text.insert("end", f"[{ts}] {msg}\n", tag if tag else ())
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._error_counts.clear()
        self._last_error_time.clear()

    def _show_help(self):
        help_text = """📋 常见问题与解决方案

【红色错误】表示需要关注的问题：

1️⃣ 限速/封禁(429) — 请求太频繁
   → 系统会自动降频，也可手动调大间隔
   
2️⃣ 封禁(403) — 被 platform 拦截  
   → 使用代理或增大间隔

3️⃣ Cloudflare 拦截 — 高级防护
   → 该平台暂不可用，建议关闭

4️⃣ 超时 — 网络不稳
   → 检查代理/网络连接

【黄色警告】提示信息：
• 平台不可用 — 正常现象，部分平台有地区限制
• 重新生成密钥 — 自动行为，无需担心

【绿色】正常状态：
• 新商品发现、启动成功等"""

        top = tk.Toplevel(self)
        top.title("常见问题")
        top.geometry("520x450")
        top.configure(bg=COLORS["bg"])
        top.transient(self.winfo_toplevel())
        top.grab_set()
        
        frame = tk.Frame(top, bg=COLORS["card"], highlightbackground=COLORS["border"],
                        highlightthickness=1)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        text = tk.Text(frame, bg=COLORS["card"], fg=COLORS["text"],
                      font=("Microsoft YaHei UI", 10), bd=0, relief="flat",
                      wrap="word", padx=16, pady=16)
        text.pack(fill="both", expand=True)
        text.insert("1.0", help_text)
        text.configure(state="disabled")
        
        tk.Button(top, text="我知道了", bg=COLORS["accent"], fg="white",
                 font=FONTS["body_bold"], bd=0, relief="flat",
                 padx=30, pady=8, cursor="hand2",
                 command=top.destroy).pack(pady=(0, 16))