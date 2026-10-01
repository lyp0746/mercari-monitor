import asyncio
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

from .styles import COLORS, FONTS, PLATFORM_COLORS, apply_theme
from .widgets import (
    StatusBar, StatsCard, ItemCard, LogPanel,
    PlatformBadge, PlatformStatusItem, EmptyState, ImageCache,
)
from src.monitors import PLATFORM_MONITORS, PLATFORM_NAMES
from src.database import Database
from src.notifier import Notifier
from src.config import config


NAV_ITEMS = [
    ("dashboard", "📊", "仪表盘"),
    ("keywords", "🔑", "关键词"),
    ("watchlist", "⭐", "关注列表"),
    ("stats", "📈", "统计"),
    ("log", "📋", "日志"),
    ("settings", "⚙️", "设置"),
]


class MonitorApp:
    def __init__(self):
        self.db = Database()
        config.sync_from_db(self.db)
        self.notifier = Notifier(self.db)
        self.notifier.add_callback(self._on_new_item)
        self.notifier.telegram_enabled = config.get("telegram_enabled", False)
        self.notifier.telegram_token = config.get("telegram_token", "")
        self.notifier.telegram_chat_id = config.get("telegram_chat_id", "")
        self.notifier.discord_webhook_url = config.get("discord_webhook_url", "")
        if self.notifier.discord_webhook_url:
            self.notifier.discord_enabled = True

        self.root = tk.Tk()
        self.root.title("二手监控助手")
        self.root.geometry("1200x800")
        self.root.minsize(960, 640)
        self.root.withdraw()

        apply_theme(self.root)

        ImageCache.get_instance().set_root(self.root)

        self._monitors: dict = {}
        self._tasks: dict = {}
        self._loop: asyncio.AbstractEventLoop = None
        self._thread: threading.Thread = None
        self._running = False
        self._item_cards: list = []
        self._session_new = 0
        self._page = 0
        self._page_size = 20
        self._has_more = False

        self._active_platform_filter = tk.StringVar(value="all")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._refresh_items())
        self._active_view = "dashboard"

        self._show_login()

    def _show_login(self):
        try:
            if not self.db.has_users():
                self._create_default_admin()
            
            login_dialog = LoginDialog(self.root, self.db, on_success=self._on_login_success)
            self.root.wait_window(login_dialog)
            
            if hasattr(self, '_auth_token') and self._auth_token:
                self.root.deiconify()
                self._build_ui()
                self._start_async_loop()
                self._refresh_items()
                self._refresh_stats()
                self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            else:
                self.root.destroy()
        except Exception as e:
            print(f"登录过程出错: {e}")
            self.root.destroy()

    def _create_default_admin(self):
        default_username = "admin"
        default_password = "admin123"
        
        try:
            ok = self.db.create_user(default_username, default_password, is_admin=True)
            if ok:
                print(f"已创建默认管理员: {default_username} / {default_password}")
            else:
                print("默认管理员创建失败")
        except Exception as e:
            print(f"创建默认管理员出错: {e}")

    def _on_login_success(self, token, user):
        self._current_user = user
        self._auth_token = token

    def _build_ui(self):
        self._build_header()
        body = tk.Frame(self.root, bg=COLORS["bg"])
        body.pack(fill="both", expand=True)
        sidebar = self._build_sidebar(body)
        sidebar.pack(side="left", fill="y")
        self._content_area = tk.Frame(body, bg=COLORS["bg"])
        self._content_area.pack(side="left", fill="both", expand=True)
        self._views = {}
        self._build_dashboard_view()
        self._build_keywords_view()
        self._build_watchlist_view()
        self._build_stats_view()
        self._build_log_view()
        self._build_settings_view()
        self._switch_view("dashboard")
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill="x", side="bottom")

    def _build_header(self):
        bar = tk.Frame(self.root, bg=COLORS["bg2"], height=56)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        logo_frame = tk.Frame(bar, bg=COLORS["bg2"])
        logo_frame.pack(side="left", padx=20, pady=10)
        tk.Label(logo_frame, text="🔍", bg=COLORS["bg2"],
                 font=("Segoe UI", 18)).pack(side="left")
        tk.Label(logo_frame, text="二手监控助手", bg=COLORS["bg2"],
                 fg=COLORS["accent"], font=FONTS["logo"]).pack(side="left", padx=(8, 0))

        search_frame = tk.Frame(bar, bg=COLORS["bg2"])
        search_frame.pack(side="left", padx=40, fill="x", expand=True)
        search_inner = tk.Frame(search_frame, bg=COLORS["input_bg"],
                                highlightbackground=COLORS["border"],
                                highlightthickness=1)
        search_inner.pack(fill="x", pady=10)
        tk.Label(search_inner, text=" 🔎", bg=COLORS["input_bg"],
                 fg=COLORS["text3"], font=FONTS["body"]).pack(side="left", padx=(8, 0))
        search_entry = tk.Entry(search_inner, textvariable=self._search_var,
                                bg=COLORS["input_bg"], fg=COLORS["text"],
                                font=FONTS["body"], bd=0, relief="flat",
                                insertbackground=COLORS["text"])
        search_entry.pack(side="left", fill="x", expand=True, padx=4, pady=6)

        self._new_count_var = tk.StringVar(value="0")
        new_badge = tk.Frame(bar, bg=COLORS["success_light"])
        new_badge.pack(side="right", padx=(0, 16), pady=14)
        tk.Label(new_badge, textvariable=self._new_count_var, bg=COLORS["success_light"],
                 fg=COLORS["success"], font=FONTS["body_bold"], padx=12, pady=4).pack()

        self._start_btn = tk.Button(
            bar, text="▶ 开始监控", bg=COLORS["accent"], fg="white",
            font=FONTS["body_bold"], bd=0, relief="flat", padx=20, pady=6,
            activebackground=COLORS["accent3"], activeforeground="white",
            cursor="hand2", command=self._toggle_monitoring,
        )
        self._start_btn.pack(side="right", padx=(0, 12), pady=10)

    def _build_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=COLORS["bg2"], width=220)
        sidebar.pack_propagate(False)

        nav_frame = tk.Frame(sidebar, bg=COLORS["bg2"])
        nav_frame.pack(fill="x", padx=8, pady=(16, 0))
        self._nav_btns = {}
        for vid, icon, label in NAV_ITEMS:
            btn = tk.Button(
                nav_frame, text=f"  {icon}  {label}",
                bg=COLORS["bg2"], fg=COLORS["text2"],
                font=FONTS["body"], bd=0, relief="flat",
                anchor="w", padx=14, pady=8, cursor="hand2",
                activebackground=COLORS["bg3"], activeforeground=COLORS["text"],
                command=lambda v=vid: self._switch_view(v),
            )
            btn.pack(fill="x", pady=2)
            self._nav_btns[vid] = btn
        self._update_nav_style("dashboard")

        sep = tk.Frame(sidebar, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=16, pady=16)

        tk.Label(sidebar, text="平台状态", bg=COLORS["bg2"], fg=COLORS["text3"],
                 font=FONTS["subheading"]).pack(anchor="w", padx=18, pady=(0, 8))

        self._platform_status_items = {}
        for pid in PLATFORM_NAMES:
            item = PlatformStatusItem(sidebar, pid)
            item.pack(fill="x")
            self._platform_status_items[pid] = item

        sep2 = tk.Frame(sidebar, bg=COLORS["border"], height=1)
        sep2.pack(fill="x", padx=16, pady=16)

        kw_frame = tk.Frame(sidebar, bg=COLORS["bg2"])
        kw_frame.pack(fill="both", expand=True, padx=10)
        tk.Label(kw_frame, text="快速添加关键词", bg=COLORS["bg2"],
                 fg=COLORS["text3"], font=FONTS["subheading"]).pack(anchor="w", padx=4, pady=(0, 8))
        add_row = tk.Frame(kw_frame, bg=COLORS["card"], highlightbackground=COLORS["border"],
                          highlightthickness=1)
        add_row.pack(fill="x")
        self._quick_kw_var = tk.StringVar()
        kw_entry = tk.Entry(add_row, textvariable=self._quick_kw_var,
                            bg=COLORS["card"], fg=COLORS["text"],
                            font=FONTS["small"], bd=0, relief="flat",
                            insertbackground=COLORS["text"],
                            highlightbackground=COLORS["border"],
                            highlightthickness=0)
        kw_entry.pack(side="left", fill="x", expand=True, padx=(8, 4), ipady=5)
        kw_entry.bind("<Return>", lambda e: self._quick_add_keyword())
        tk.Button(add_row, text="+", bg=COLORS["accent"], fg="white",
                  font=FONTS["body_bold"], bd=0, relief="flat", width=3,
                  cursor="hand2", command=self._quick_add_keyword).pack(side="right", padx=(0, 4))

        return sidebar

    def _switch_view(self, view_id: str):
        self._active_view = view_id
        for vid, frame in self._views.items():
            if vid == view_id:
                frame.pack(fill="both", expand=True, in_=self._content_area)
            else:
                frame.pack_forget()
        self._update_nav_style(view_id)

    def _update_nav_style(self, active: str):
        for vid, btn in self._nav_btns.items():
            if vid == active:
                btn.configure(bg=COLORS["accent_bg"], fg=COLORS["accent"],
                              font=FONTS["body_bold"], activebackground=COLORS["accent_bg"])
            else:
                btn.configure(bg=COLORS["bg2"], fg=COLORS["text2"],
                              font=FONTS["body"], activebackground=COLORS["bg3"])

    def _build_dashboard_view(self):
        view = tk.Frame(self._content_area, bg=COLORS["bg"])
        self._views["dashboard"] = view

        stats_row = tk.Frame(view, bg=COLORS["bg"])
        stats_row.pack(fill="x", padx=20, pady=(20, 0))
        self._stat_total = StatsCard(stats_row, "📦", "总计商品", "0", COLORS["accent"])
        self._stat_total.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._stat_today = StatsCard(stats_row, "🆕", "今日新增", "0", COLORS["success"])
        self._stat_today.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._stat_platforms = StatsCard(stats_row, "🌐", "活跃平台", "0/6", COLORS["info"])
        self._stat_platforms.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._stat_session = StatsCard(stats_row, "⚡", "本次发现", "0", COLORS["warning"])
        self._stat_session.pack(side="left", fill="x", expand=True)

        filter_row = tk.Frame(view, bg=COLORS["bg"])
        filter_row.pack(fill="x", padx=20, pady=(16, 0))
        self._filter_btns = {}
        all_btn = tk.Button(
            filter_row, text="全部平台", bg=COLORS["accent"], fg="white",
            font=FONTS["body_bold"], bd=0, relief="flat", padx=14, pady=5,
            cursor="hand2", command=lambda: self._filter_platform("all"),
        )
        all_btn.pack(side="left", padx=(0, 6))
        self._filter_btns["all"] = all_btn
        for pid, pname in PLATFORM_NAMES.items():
            color = PLATFORM_COLORS.get(pid, COLORS["accent"])
            btn = tk.Button(
                filter_row, text=pname, bg=COLORS["card"], fg=COLORS["text2"],
                font=FONTS["small"], bd=0, relief="flat", padx=12, pady=5,
                highlightbackground=color, highlightthickness=1,
                cursor="hand2", command=lambda p=pid: self._filter_platform(p),
            )
            btn.pack(side="left", padx=3)
            self._filter_btns[pid] = btn

        feed_header = tk.Frame(view, bg=COLORS["bg"])
        feed_header.pack(fill="x", padx=20, pady=(16, 0))
        self._feed_count_var = tk.StringVar(value="商品流")
        tk.Label(feed_header, textvariable=self._feed_count_var, bg=COLORS["bg"],
                 fg=COLORS["text"], font=FONTS["heading"]).pack(side="left")
        tk.Button(feed_header, text="清空显示", bg=COLORS["card"], fg=COLORS["text2"],
                  font=FONTS["small"], bd=0, relief="flat", highlightbackground=COLORS["border"],
                  highlightthickness=1, padx=10, pady=4,
                  cursor="hand2", command=self._clear_feed).pack(side="right")

        container = tk.Frame(view, bg=COLORS["bg"])
        container.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        canvas = tk.Canvas(container, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self._scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw",
                             tags="scroll_window")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(e):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(e):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)
        self._feed_canvas = canvas

        def _on_canvas_configure(event):
            canvas.itemconfigure("scroll_window", width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_scroll(event):
            canvas.yview_moveto(scrollbar.get()[0])
            if scrollbar.get()[1] >= 0.95 and self._has_more:
                self._load_more_items()

        scrollbar.configure(command=lambda *args: (
            canvas.yview(*args), _on_scroll(None)
        ))

        self._empty_feed = EmptyState(
            self._scroll_frame, "📦", "暂无商品",
            "添加关键词并开始监控后，新商品将显示在这里"
        )
        self._empty_feed.pack(fill="x", pady=20)

    def _build_keywords_view(self):
        view = tk.Frame(self._content_area, bg=COLORS["bg"])
        self._views["keywords"] = view

        header = tk.Frame(view, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="关键词管理", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["title"]).pack(side="left")
        tk.Button(header, text="+ 添加关键词", bg=COLORS["accent"], fg="white",
                  font=FONTS["body_bold"], bd=0, relief="flat", padx=18, pady=7,
                  cursor="hand2", command=self._show_add_keyword_dialog).pack(side="right")

        kw_card = tk.Frame(view, bg=COLORS["card"], highlightbackground=COLORS["border"],
                          highlightthickness=1)
        kw_card.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._kw_tree = ttk.Treeview(
            kw_card, columns=("keyword", "platform", "price_range", "poll_interval", "noshops", "conditions", "status"),
            show="headings", selectmode="browse", height=18,
        )
        self._kw_tree.heading("keyword", text="关键词")
        self._kw_tree.heading("platform", text="平台")
        self._kw_tree.heading("price_range", text="价格范围")
        self._kw_tree.heading("poll_interval", text="轮询率(s)")
        self._kw_tree.heading("noshops", text="过滤商城")
        self._kw_tree.heading("conditions", text="成色筛选")
        self._kw_tree.heading("status", text="状态")
        self._kw_tree.column("keyword", width=140, minwidth=110)
        self._kw_tree.column("platform", width=110, minwidth=90)
        self._kw_tree.column("price_range", width=120, minwidth=90)
        self._kw_tree.column("poll_interval", width=80, minwidth=65)
        self._kw_tree.column("noshops", width=75, minwidth=65)
        self._kw_tree.column("conditions", width=90, minwidth=70)
        self._kw_tree.column("status", width=80, minwidth=60)

        kw_sb = ttk.Scrollbar(kw_card, orient="vertical",
                               command=self._kw_tree.yview)
        self._kw_tree.configure(yscrollcommand=kw_sb.set)
        self._kw_tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        kw_sb.pack(side="right", fill="y")

        actions = tk.Frame(view, bg=COLORS["bg"])
        actions.pack(fill="x", padx=16, pady=(0, 20))
        
        btn_style = {"bd": 0, "relief": "flat", "font": FONTS["body_bold"],
                    "padx": 14, "pady": 5, "cursor": "hand2"}
        
        tk.Button(actions, text="🗑️ 删除选中", bg="#ef4444", fg="white",
                  command=self._delete_keyword, **btn_style).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="✏️ 编辑选中", bg="#3b82f6", fg="white",
                  command=self._edit_keyword, **btn_style).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="⏯️ 启用/禁用", bg="#f59e0b", fg="white",
                  command=self._toggle_keyword, **btn_style).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="🔄 刷新列表", bg=COLORS["card"], fg=COLORS["text2"],
                  highlightbackground=COLORS["border"], highlightthickness=1,
                  command=self._refresh_keywords, **btn_style).pack(side="left")

        self._refresh_keywords()

    def _build_watchlist_view(self):
        view = tk.Frame(self._content_area, bg=COLORS["bg"])
        self._views["watchlist"] = view

        header = tk.Frame(view, bg=COLORS["bg"])
        header.pack(fill="x", padx=24, pady=(24, 0))
        tk.Label(header, text="关注列表", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["title"]).pack(side="left")

        sep = tk.Frame(view, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=24, pady=(16, 0))

        tab_frame = tk.Frame(view, bg=COLORS["bg"])
        tab_frame.pack(fill="x", padx=24, pady=(0, 16))

        self._watchlist_tab = tk.StringVar(value="sellers")
        tabs = [
            ("sellers", f"👤 关注卖家 ({len(self.db.get_watched_sellers())})"),
            ("items", f"📦 关注商品 ({len(self.db.get_watched_items())})"),
        ]
        for tab_val, tab_label in tabs:
            rb = tk.Radiobutton(
                tab_frame, text=tab_label, variable=self._watchlist_tab,
                value=tab_val, bg=COLORS["bg"], fg=COLORS["text2"],
                selectcolor=COLORS["accent"], activebackground=COLORS["bg"],
                activeforeground=COLORS["text"], font=FONTS["body"],
                command=self._switch_watchlist_tab,
            )
            rb.pack(side="left", padx=(0, 12))

        self._sellers_frame = tk.Frame(view, bg=COLORS["bg"])
        self._items_frame = tk.Frame(view, bg=COLORS["bg"])

        self._build_sellers_section(self._sellers_frame)
        self._build_items_section(self._items_frame)

        self._switch_watchlist_tab()

    def _build_sellers_section(self, parent):
        form_card = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                            highlightthickness=1)
        form_card.pack(fill="x", padx=16, pady=(0, 12))
        form_inner = tk.Frame(form_card, bg=COLORS["card"])
        form_inner.pack(fill="x", padx=14, pady=12)

        tk.Label(form_inner, text="➕ 添加关注卖家", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 8))

        row1 = tk.Frame(form_inner, bg=COLORS["card"])
        row1.pack(fill="x", pady=(0, 8))
        tk.Label(row1, text="卖家ID:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._seller_id_var = tk.StringVar()
        tk.Entry(row1, textvariable=self._seller_id_var, bg=COLORS["input_bg"],
                fg=COLORS["text"], font=FONTS["body"], bd=0, relief="flat",
                width=20).pack(side="left", padx=(8, 12))

        tk.Label(row1, text="平台:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._seller_platform_var = tk.StringVar(value="mercari_jp")
        platform_names_list = list(PLATFORM_NAMES.values())
        seller_platform_combo = ttk.Combobox(
            row1, textvariable=self._seller_platform_var,
            values=platform_names_list, state="readonly", width=12,
        )
        seller_platform_combo.pack(side="left", padx=(4, 12))

        tk.Label(row1, text="备注:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._seller_alias_var = tk.StringVar()
        tk.Entry(row1, textvariable=self._seller_alias_var, bg=COLORS["input_bg"],
                fg=COLORS["text"], font=FONTS["body"], bd=0, relief="flat",
                width=15).pack(side="left", padx=(4, 0))

        btn_row = tk.Frame(form_inner, bg=COLORS["card"])
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="✅ 添加卖家", bg=COLORS["accent"], fg="white",
                 font=FONTS["body_bold"], bd=0, relief="flat", padx=16, pady=6,
                 cursor="hand2", command=self._add_watched_seller).pack(side="left")

        list_card = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                            highlightthickness=1)
        list_card.pack(fill="both", expand=True, padx=16)
        self._sellers_tree = ttk.Treeview(
            list_card, columns=("seller_id", "platform", "alias"),
            show="headings", selectmode="browse", height=10,
        )
        self._sellers_tree.heading("seller_id", text="卖家 ID")
        self._sellers_tree.heading("platform", text="平台")
        self._sellers_tree.heading("alias", text="备注")
        self._sellers_tree.column("seller_id", width=200)
        self._sellers_tree.column("platform", width=120)
        self._sellers_tree.column("alias", width=150)

        sellers_sb = ttk.Scrollbar(list_card, orient="vertical", command=self._sellers_tree.yview)
        self._sellers_tree.configure(yscrollcommand=sellers_sb.set)
        self._sellers_tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        sellers_sb.pack(side="right", fill="y")

        actions = tk.Frame(parent, bg=COLORS["bg"])
        actions.pack(fill="x", padx=16, pady=(8, 16))
        tk.Button(actions, text="删除选中", bg=COLORS["danger"], fg="white",
                 font=FONTS["body_bold"], bd=0, relief="flat", padx=14, pady=5,
                 cursor="hand2", command=self._delete_watched_seller).pack(side="left")
        tk.Button(actions, text="刷新列表", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body_bold"], bd=0, relief="flat", highlightbackground=COLORS["border"],
                 highlightthickness=1, padx=14, pady=5,
                 cursor="hand2", command=self._refresh_sellers).pack(side="left", padx=8)

        self._refresh_sellers()

    def _build_items_section(self, parent):
        form_card = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                           highlightthickness=1)
        form_card.pack(fill="x", padx=16, pady=(0, 12))
        form_inner = tk.Frame(form_card, bg=COLORS["card"])
        form_inner.pack(fill="x", padx=14, pady=12)

        tk.Label(form_inner, text="📦 添加关注商品（监控留言/议价）", bg=COLORS["card"],
                 fg=COLORS["text2"], font=FONTS["subheading"]).pack(anchor="w", pady=(0, 8))

        row1 = tk.Frame(form_inner, bg=COLORS["card"])
        row1.pack(fill="x", pady=(0, 8))
        tk.Label(row1, text="商品ID:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._item_id_var = tk.StringVar()
        tk.Entry(row1, textvariable=self._item_id_var, bg=COLORS["input_bg"],
                fg=COLORS["text"], font=FONTS["body"], bd=0, relief="flat",
                width=18).pack(side="left", padx=(8, 12))

        tk.Label(row1, text="平台:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._item_platform_var = tk.StringVar(value="mercari_jp")
        item_platform_combo = ttk.Combobox(
            row1, textvariable=self._item_platform_var,
            values=list(PLATFORM_NAMES.values()), state="readonly", width=12,
        )
        item_platform_combo.pack(side="left", padx=(4, 12))

        tk.Label(row1, text="名称:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._item_name_var = tk.StringVar()
        tk.Entry(row1, textvariable=self._item_name_var, bg=COLORS["input_bg"],
                fg=COLORS["text"], font=FONTS["body"], bd=0, relief="flat",
                width=15).pack(side="left", padx=(4, 0))

        row2 = tk.Frame(form_inner, bg=COLORS["card"])
        row2.pack(fill="x", pady=(0, 8))
        tk.Label(row2, text="URL:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._item_url_var = tk.StringVar()
        tk.Entry(row2, textvariable=self._item_url_var, bg=COLORS["input_bg"],
                fg=COLORS["text"], font=FONTS["body"], bd=0, relief="flat",
                width=50).pack(side="left", padx=(8, 0), fill="x", expand=True)

        btn_row = tk.Frame(form_inner, bg=COLORS["card"])
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="✅ 添加商品", bg=COLORS["accent"], fg="white",
                 font=FONTS["body_bold"], bd=0, relief="flat", padx=16, pady=6,
                 cursor="hand2", command=self._add_watched_item).pack(side="left")

        hint = tk.Label(form_inner, text="💡 提示：关注商品后，系统会自动监控该商品的留言和议价更新，有新消息时推送通知",
                       bg=COLORS["card"], fg=COLORS["text3"], font=FONTS["small"])
        hint.pack(anchor="w", pady=(8, 0))

        list_card = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["border"],
                            highlightthickness=1)
        list_card.pack(fill="both", expand=True, padx=16)
        self._items_tree = ttk.Treeview(
            list_card, columns=("item_id", "platform", "name", "comments", "created_at"),
            show="headings", selectmode="browse", height=10,
        )
        self._items_tree.heading("item_id", text="商品 ID")
        self._items_tree.heading("platform", text="平台")
        self._items_tree.heading("name", text="商品名称")
        self._items_tree.heading("comments", text="留言数")
        self._items_tree.heading("created_at", text="添加时间")
        self._items_tree.column("item_id", width=150)
        self._items_tree.column("platform", width=100)
        self._items_tree.column("name", width=200)
        self._items_tree.column("comments", width=70)
        self._items_tree.column("created_at", width=140)

        items_sb = ttk.Scrollbar(list_card, orient="vertical", command=self._items_tree.yview)
        self._items_tree.configure(yscrollcommand=items_sb.set)
        self._items_tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        items_sb.pack(side="right", fill="y")

        actions = tk.Frame(parent, bg=COLORS["bg"])
        actions.pack(fill="x", padx=16, pady=(8, 16))
        tk.Button(actions, text="删除选中", bg=COLORS["danger"], fg="white",
                 font=FONTS["body_bold"], bd=0, relief="flat", padx=14, pady=5,
                 cursor="hand2", command=self._delete_watched_item).pack(side="left")
        tk.Button(actions, text="刷新列表", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body_bold"], bd=0, relief="flat", highlightbackground=COLORS["border"],
                 highlightthickness=1, padx=14, pady=5,
                 cursor="hand2", command=self._refresh_watchlist_items).pack(side="left", padx=8)

        self._refresh_watchlist_items()

    def _switch_watchlist_tab(self):
        tab = self._watchlist_tab.get()
        if tab == "sellers":
            self._sellers_frame.pack(fill="both", expand=True)
            self._items_frame.forget()
            self._sellers_frame.update_idletasks()
            self._refresh_sellers()
        else:
            self._items_frame.pack(fill="both", expand=True)
            self._sellers_frame.forget()
            self._items_frame.update_idletasks()
            self._refresh_watchlist_items()

    def _update_watchlist_tab_labels(self):
        if not hasattr(self, "_watchlist_tab"):
            return
        try:
            sellers_count = len(self.db.get_watched_sellers())
            items_count = len(self.db.get_watched_items())

            for widget in self._watchlist_tab.master.winfo_children():
                if isinstance(widget, tk.Radiobutton):
                    text = widget.cget("text")
                    if "关注卖家" in text:
                        widget.config(text=f"👤 关注卖家 ({sellers_count})")
                    elif "关注商品" in text:
                        widget.config(text=f"📦 关注商品 ({items_count})")
        except Exception:
            pass

    def _add_watched_seller(self):
        seller_id = self._seller_id_var.get().strip()
        if not seller_id:
            messagebox.showwarning("提示", "卖家ID不能为空")
            return
        platform_name = self._seller_platform_var.get()
        platform_id = None
        for pid, pname in PLATFORM_NAMES.items():
            if pname == platform_name:
                platform_id = pid
                break
        if not platform_id:
            return
        alias = self._seller_alias_var.get().strip()
        ok = self.db.add_watched_seller(seller_id, platform_id, alias)
        if ok:
            self.log_panel.append(f"已添加关注卖家: {seller_id}")
            self._seller_id_var.set("")
            self._seller_alias_var.set("")
            self._refresh_sellers()
        else:
            messagebox.showinfo("提示", "该卖家已在关注列表中")

    def _delete_watched_seller(self):
        sel = self._sellers_tree.selection()
        if not sel:
            return
        values = self._sellers_tree.item(sel[0], "values")
        if not values:
            return
        seller_id = values[0]
        platform_name = values[1]
        platform_id = None
        for pid, pname in PLATFORM_NAMES.items():
            if pname == platform_name:
                platform_id = pid
                break
        if platform_id and messagebox.askyesno("确认", f"删除关注卖家「{seller_id}」？"):
            self.db.remove_watched_seller(seller_id, platform_id)
            self.log_panel.append(f"已删除关注卖家: {seller_id}")
            self._refresh_sellers()

    def _refresh_sellers(self):
        if not hasattr(self, "_sellers_tree"):
            return
        for row in self._sellers_tree.get_children():
            self._sellers_tree.delete(row)
        sellers = self.db.get_watched_sellers()
        for s in sellers:
            pname = PLATFORM_NAMES.get(s["platform"], s["platform"])
            self._sellers_tree.insert("", "end", values=(
                s["seller_id"], pname, s.get("alias", "")
            ))
        self._update_watchlist_tab_labels()

    def _add_watched_item(self):
        try:
            item_id = self._item_id_var.get().strip()
            if not item_id:
                messagebox.showwarning("提示", "商品ID不能为空")
                return

            platform_name = self._item_platform_var.get()
            platform_id = None
            for pid, pname in PLATFORM_NAMES.items():
                if pname == platform_name:
                    platform_id = pid
                    break

            if not platform_id:
                messagebox.showerror("错误", "无效的平台选择")
                return

            name = self._item_name_var.get().strip() or f"商品-{item_id}"
            url = self._item_url_var.get().strip()

            ok = self.db.add_watched_item(item_id, platform_id, name, url)

            if ok:
                messagebox.showinfo("成功", f"✅ 已添加关注商品：{name}\n\n系统将自动监控该商品的留言和议价更新")
                self.log_panel.append(f"✅ 已添加关注商品: {name} [{platform_name}]")

                self._item_id_var.set("")
                self._item_name_var.set("")
                self._item_url_var.set("")
            else:
                messagebox.showinfo("提示", "⚠️ 该商品已在关注列表中")

            self._refresh_watchlist_items()

        except Exception as e:
            error_msg = str(e)

            if "no such table" in error_msg.lower():
                messagebox.showerror("数据库错误", "数据库表不存在，请重启应用或重新安装")
            elif "UNIQUE constraint" in error_msg or "already exists" in error_msg.lower():
                messagebox.showinfo("提示", "该商品已在关注列表中")
            else:
                messagebox.showerror("添加失败", f"添加商品时发生错误：\n\n{error_msg}\n\n请查看日志获取详细信息")

    def _delete_watched_item(self):
        sel = self._items_tree.selection()
        if not sel:
            return

        values = self._items_tree.item(sel[0], "values")
        if not values:
            return

        item_id = values[0]
        platform_name = values[1]
        platform_id = None
        for pid, pname in PLATFORM_NAMES.items():
            if pname == platform_name:
                platform_id = pid
                break

        name = values[2] or item_id

        if platform_id and messagebox.askyesno("确认", f"删除关注商品「{name}」？"):
            self.db.remove_watched_item(item_id, platform_id)
            self.log_panel.append(f"已删除关注商品: {name}")
            self._refresh_watchlist_items()

    def _refresh_watchlist_items(self):
        if not hasattr(self, "_items_tree"):
            return

        for row in self._items_tree.get_children():
            self._items_tree.delete(row)

        items = self.db.get_watched_items()

        for it in items:
            item_id = str(it.get("item_id", ""))
            platform_raw = str(it.get("platform", ""))
            pname = PLATFORM_NAMES.get(platform_raw, platform_raw)
            name = str(it.get("name", "")).strip() or item_id
            comments = str(it.get("last_comment_count", 0) or 0)
            created_at = str(it.get("created_at", ""))[:19]

            self._items_tree.insert("", "end", values=(
                item_id, pname, name, comments, created_at
            ))

        self._update_watchlist_tab_labels()

    def _build_stats_view(self):
        view = tk.Frame(self._content_area, bg=COLORS["bg"])
        self._views["stats"] = view

        tk.Label(view, text="运行统计", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["title"]).pack(anchor="w", padx=24, pady=(24, 0))

        sep = tk.Frame(view, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=24, pady=(16, 0))

        overview = tk.Frame(view, bg=COLORS["card"], highlightbackground=COLORS["border"],
                           highlightthickness=1)
        overview.pack(fill="x", padx=24, pady=16)
        self._stats_labels = {}
        stats_items = [
            ("total", "📦 总计发现商品", COLORS["accent"]),
            ("today", "🆕 今日新上架", COLORS["success"]),
        ]
        for i, (key, label, color) in enumerate(stats_items):
            row = tk.Frame(overview, bg=COLORS["card"])
            row.pack(fill="x", padx=16, pady=8)
            tk.Label(row, text=label, bg=COLORS["card"], fg=COLORS["text2"],
                     font=FONTS["body"]).pack(side="left")
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=COLORS["card"], fg=color,
                     font=FONTS["heading"]).pack(side="right")
            self._stats_labels[key] = var

        sep2 = tk.Frame(view, bg=COLORS["border"], height=1)
        sep2.pack(fill="x", padx=24, pady=12)

        tk.Label(view, text="各平台商品数", bg=COLORS["bg"], fg=COLORS["text2"],
                 font=FONTS["heading"]).pack(anchor="w", padx=24, pady=(8, 4))

        platform_stats = tk.Frame(view, bg=COLORS["card"], highlightbackground=COLORS["border"],
                                 highlightthickness=1)
        platform_stats.pack(fill="x", padx=24, pady=8)
        self._platform_bars = {}
        for pid, pname in PLATFORM_NAMES.items():
            color = PLATFORM_COLORS.get(pid, COLORS["accent"])
            row = tk.Frame(platform_stats, bg=COLORS["card"])
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=pname, bg=COLORS["card"], fg=COLORS["text2"],
                     font=FONTS["small"], width=16, anchor="w").pack(side="left")
            bar_frame = tk.Frame(row, bg=COLORS["bg3"], height=14)
            bar_frame.pack(side="left", fill="x", expand=True, padx=(10, 10))
            bar_frame.pack_propagate(False)
            bar_fill = tk.Frame(bar_frame, bg=color, height=14, width=0)
            bar_fill.pack(side="left", fill="y")
            var = tk.StringVar(value="0")
            tk.Label(row, textvariable=var, bg=COLORS["card"], fg=COLORS["text3"],
                     font=FONTS["small"], width=8, anchor="e").pack(side="right")
            self._platform_bars[pid] = (bar_fill, var, bar_frame)

    def _build_log_view(self):
        view = tk.Frame(self._content_area, bg=COLORS["bg"])
        self._views["log"] = view
        self.log_panel = LogPanel(view)
        self.log_panel.pack(fill="both", expand=True)

    def _build_settings_view(self):
        view = tk.Frame(self._content_area, bg=COLORS["bg"])
        self._views["settings"] = view

        canvas = tk.Canvas(view, bg=COLORS["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(view, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=COLORS["bg"])
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_wheel(e):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(e):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        pad = {"padx": 28, "pady": 6}

        tk.Label(scroll_frame, text="⚙️ 系统设置", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["title"]).pack(anchor="w", **pad)

        sep = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="🔄 轮询间隔设置", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="关键词轮询间隔（秒），留空使用默认值",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        self._interval_vars = {}
        for pid, pname in PLATFORM_NAMES.items():
            color = PLATFORM_COLORS.get(pid, COLORS["accent"])
            row = tk.Frame(scroll_frame, bg=COLORS["card"],
                           highlightbackground=COLORS["border"],
                           highlightthickness=1)
            row.pack(fill="x", padx=28, pady=4)
            inner = tk.Frame(row, bg=COLORS["card"])
            inner.pack(fill="x", padx=16, pady=10)
            tk.Label(inner, text="●", bg=COLORS["card"], fg=color,
                     font=FONTS["body_bold"]).pack(side="left")
            tk.Label(inner, text=pname, bg=COLORS["card"], fg=COLORS["text"],
                     font=FONTS["body_bold"]).pack(side="left", padx=(8, 0))
            default_interval = config.get_platform_interval(pid)
            spin_max = 3600.0 if pid == "carousell" else 60.0
            var = tk.StringVar(value=str(default_interval) if default_interval is not None else "")
            spin = ttk.Spinbox(inner, from_=0.05, to=spin_max, increment=0.05 if pid != "carousell" else 10.0,
                               textvariable=var, width=7, font=FONTS["body"])
            spin.pack(side="right")
            tk.Label(inner, text="秒", bg=COLORS["card"], fg=COLORS["text3"],
                     font=FONTS["body"]).pack(side="right", padx=(6, 0))
            if pid == "carousell":
                tk.Label(inner, text="⚠️ 已不可用", bg=COLORS["card"], fg="#e6a817",
                         font=FONTS["small"]).pack(side="right", padx=(0, 8))
            self._interval_vars[pid] = var

        sep2 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep2.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="🌏 Carousell 地区选择", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="选择要监控的 Carousell 地区市场",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        self._carousell_region_vars = {}
        from src.monitors.carousell import CAROUSELL_REGIONS
        region_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                highlightbackground=COLORS["border"],
                                highlightthickness=1)
        region_frame.pack(fill="x", padx=28, pady=10)
        region_inner = tk.Frame(region_frame, bg=COLORS["card"])
        region_inner.pack(fill="x", padx=16, pady=12)
        default_regions = config.get_carousell_regions()
        for code in CAROUSELL_REGIONS:
            var = tk.BooleanVar(value=code in default_regions)
            cb = tk.Checkbutton(
                region_inner, text=f"  {code}", variable=var,
                bg=COLORS["card"], fg=COLORS["text"], selectcolor=COLORS["accent"],
                activebackground=COLORS["card"], activeforeground=COLORS["text"],
                font=FONTS["body"],
            )
            cb.pack(side="left", padx=6)
            self._carousell_region_vars[code] = var

        sep3 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep3.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="📱 Telegram 推送配置", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="新商品/降价/拍卖结束时推送到 Telegram",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        self._tg_enabled_var = tk.BooleanVar(
            value=config.get("telegram_enabled", False)
        )
        tg_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                            highlightbackground=COLORS["border"],
                            highlightthickness=1)
        tg_frame.pack(fill="x", padx=28, pady=10)
        tg_inner = tk.Frame(tg_frame, bg=COLORS["card"])
        tg_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(tg_inner, text="启用推送", bg=COLORS["card"],
                 fg=COLORS["text"], font=FONTS["body_bold"]).pack(side="left")
        tk.Checkbutton(
            tg_inner, variable=self._tg_enabled_var,
            bg=COLORS["card"], fg=COLORS["text"], selectcolor=COLORS["accent"],
            activebackground=COLORS["card"], activeforeground=COLORS["text"],
            command=self._update_notif_settings,
        ).pack(side="right")

        token_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                               highlightbackground=COLORS["border"],
                               highlightthickness=1)
        token_frame.pack(fill="x", padx=28, pady=4)
        token_inner = tk.Frame(token_frame, bg=COLORS["card"])
        token_inner.pack(fill="x", padx=16, pady=10)
        tk.Label(token_inner, text="Bot Token", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"], width=11, anchor="w").pack(side="left")
        self._tg_token_var = tk.StringVar(
            value=config.get("telegram_token", "")
        )
        tk.Entry(token_inner, textvariable=self._tg_token_var,
                 bg=COLORS["input_bg"], fg=COLORS["text"],
                 insertbackground=COLORS["text"], font=FONTS["mono_small"],
                 relief="flat", show="•").pack(side="left", fill="x", expand=True, padx=(10, 0))

        chat_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                              highlightbackground=COLORS["border"],
                              highlightthickness=1)
        chat_frame.pack(fill="x", padx=28, pady=4)
        chat_inner = tk.Frame(chat_frame, bg=COLORS["card"])
        chat_inner.pack(fill="x", padx=16, pady=10)
        tk.Label(chat_inner, text="Chat ID", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"], width=11, anchor="w").pack(side="left")
        self._tg_chat_var = tk.StringVar(
            value=config.get("telegram_chat_id", "")
        )
        tk.Entry(chat_inner, textvariable=self._tg_chat_var,
                 bg=COLORS["input_bg"], fg=COLORS["text"],
                 insertbackground=COLORS["text"], font=FONTS["mono_small"],
                 relief="flat").pack(side="left", fill="x", expand=True, padx=(10, 0))

        btn_frame = tk.Frame(scroll_frame, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=28, pady=(10, 6))
        tk.Button(btn_frame, text="🔗 测试连接", bg=COLORS["accent"], fg="white",
                  font=FONTS["body_bold"], relief="flat", padx=18, pady=6,
                  cursor="hand2", command=self._test_telegram).pack(side="left")
        self._tg_status_label = tk.Label(btn_frame, text="", bg=COLORS["bg"],
                                         fg=COLORS["text3"], font=FONTS["body"])
        self._tg_status_label.pack(side="left", padx=14)

        help_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                              highlightbackground=COLORS["border"],
                              highlightthickness=1)
        help_frame.pack(fill="x", padx=28, pady=(6, 10))
        help_inner = tk.Frame(help_frame, bg=COLORS["card"])
        help_inner.pack(fill="x", padx=16, pady=12)
        help_text = (
            "设置步骤：\n"
            "1. 在 Telegram 搜索 @BotFather，发送 /newbot 创建机器人\n"
            "2. 获取 Bot Token（格式如 123456:ABC-DEF...）\n"
            "3. 搜索 @userinfobot，获取你的 Chat ID（纯数字）\n"
            "4. 先给机器人发一条消息，再点击「测试连接」"
        )
        tk.Label(help_inner, text=help_text, bg=COLORS["card"], fg=COLORS["text3"],
                 font=FONTS["body"], justify="left", anchor="w").pack(fill="x")

        sep3_5 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep3_5.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="🎮 Discord 推送配置", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="新商品/降价/拍卖结束时推送到 Discord 频道",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        discord_enabled_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                         highlightbackground=COLORS["border"],
                                         highlightthickness=1)
        discord_enabled_frame.pack(fill="x", padx=28, pady=10)
        discord_enabled_inner = tk.Frame(discord_enabled_frame, bg=COLORS["card"])
        discord_enabled_inner.pack(fill="x", padx=16, pady=12)

        self._discord_enabled_var = tk.BooleanVar(
            value=config.get("discord_enabled", False)
        )
        tk.Label(discord_enabled_inner, text="启用推送", bg=COLORS["card"],
                 fg=COLORS["text"], font=FONTS["body_bold"]).pack(side="left")
        tk.Checkbutton(
            discord_enabled_inner, variable=self._discord_enabled_var,
            bg=COLORS["card"], fg=COLORS["text"], selectcolor=COLORS["accent"],
            activebackground=COLORS["card"], activeforeground=COLORS["text"],
            command=self._update_notif_settings,
        ).pack(side="right")

        webhook_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                 highlightbackground=COLORS["border"],
                                 highlightthickness=1)
        webhook_frame.pack(fill="x", padx=28, pady=4)
        webhook_inner = tk.Frame(webhook_frame, bg=COLORS["card"])
        webhook_inner.pack(fill="x", padx=16, pady=10)
        tk.Label(webhook_inner, text="Webhook URL", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"], width=11, anchor="w").pack(side="left")
        self._discord_webhook_var = tk.StringVar(
            value=config.get("discord_webhook_url", "")
        )
        tk.Entry(webhook_inner, textvariable=self._discord_webhook_var,
                 bg=COLORS["input_bg"], fg=COLORS["text"],
                 insertbackground=COLORS["text"], font=FONTS["mono_small"],
                 relief="flat").pack(side="left", fill="x", expand=True, padx=(10, 0))

        discord_btn_frame = tk.Frame(scroll_frame, bg=COLORS["bg"])
        discord_btn_frame.pack(fill="x", padx=28, pady=(10, 6))
        tk.Button(discord_btn_frame, text="🔗 测试连接", bg=COLORS["accent"], fg="white",
                  font=FONTS["body_bold"], relief="flat", padx=18, pady=6,
                  cursor="hand2", command=self._test_discord).pack(side="left")
        self._discord_status_label = tk.Label(discord_btn_frame, text="", bg=COLORS["bg"],
                                              fg=COLORS["text3"], font=FONTS["body"])
        self._discord_status_label.pack(side="left", padx=14)

        discord_help_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                      highlightbackground=COLORS["border"],
                                      highlightthickness=1)
        discord_help_frame.pack(fill="x", padx=28, pady=(6, 10))
        discord_help_inner = tk.Frame(discord_help_frame, bg=COLORS["card"])
        discord_help_inner.pack(fill="x", padx=16, pady=12)
        discord_help_text = (
            "设置步骤：\n"
            "1. 打开 Discord 频道设置 → 整合 → Webhooks\n"
            "2. 点击「新建 Webhook」，自定义名称和头像\n"
            "3. 复制 Webhook URL（格式如 https://discord.com/api/webhooks/...）\n"
            "4. 粘贴到上方输入框并点击「测试连接」"
        )
        tk.Label(discord_help_inner, text=discord_help_text, bg=COLORS["card"], fg=COLORS["text3"],
                 font=FONTS["body"], justify="left", anchor="w").pack(fill="x")

        sep4 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep4.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="🌐 代理 IP 配置", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="每行一个代理地址，支持 HTTP/HTTPS/SOCKS5",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        proxy_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                               highlightbackground=COLORS["border"],
                               highlightthickness=1)
        proxy_frame.pack(fill="x", padx=28, pady=10)
        proxy_inner = tk.Frame(proxy_frame, bg=COLORS["card"])
        proxy_inner.pack(fill="x", padx=16, pady=12)

        self._proxy_text = tk.Text(
            proxy_inner, height=4, bg=COLORS["input_bg"], fg=COLORS["text"],
            insertbackground=COLORS["text"], font=FONTS["mono_small"],
            relief="flat", wrap="none",
        )
        saved_proxies = config.get("proxies", "")
        if saved_proxies:
            self._proxy_text.insert("1.0", saved_proxies)
        self._proxy_text.pack(fill="x")

        proxy_hint_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                    highlightbackground=COLORS["border"],
                                    highlightthickness=1)
        proxy_hint_frame.pack(fill="x", padx=28, pady=(4, 12))
        proxy_hint_inner = tk.Frame(proxy_hint_frame, bg=COLORS["card"])
        proxy_hint_inner.pack(fill="x", padx=16, pady=12)
        proxy_hint_text = (
            "支持的代理格式：\n"
            "  HTTP:  http://ip:port\n"
            "  HTTPS: https://ip:port\n"
            "  SOCKS5: socks5://ip:port\n"
            "  带认证: http://user:pass@ip:port\n\n"
            "留空则不使用代理，直接连接"
        )
        tk.Label(proxy_hint_inner, text=proxy_hint_text, bg=COLORS["card"],
                 fg=COLORS["text3"], font=FONTS["body"], justify="left",
                 anchor="w").pack(fill="x")

        proxy_platforms_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                         highlightbackground=COLORS["border"],
                                         highlightthickness=1)
        proxy_platforms_frame.pack(fill="x", padx=28, pady=(0, 12))
        proxy_platforms_inner = tk.Frame(proxy_platforms_frame, bg=COLORS["card"])
        proxy_platforms_inner.pack(fill="x", padx=16, pady=12)
        tk.Label(proxy_platforms_inner, text="使用代理的平台（逗号分隔，留空仅Mercari使用代理）",
                 bg=COLORS["card"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w")
        self._proxy_platforms_var = tk.StringVar(
            value=config.get("proxy_platforms", "mercari_jp"))
        tk.Entry(proxy_platforms_inner, textvariable=self._proxy_platforms_var,
                 bg=COLORS["input_bg"], fg=COLORS["text"], font=FONTS["body"],
                 relief="flat").pack(fill="x", pady=(4, 0))
        tk.Label(proxy_platforms_inner, text="可选: mercari_jp, yahoo_auctions, paypay_fleamarket, fril, bunjang, carousell",
                 bg=COLORS["card"], fg=COLORS["text3"], font=FONTS["tiny"]).pack(anchor="w", pady=(2, 0))

        sep5 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep5.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="💱 自定义汇率设置", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="设置各货币兑人民币（CNY）的汇率",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        self._exchange_rate_vars = {}
        exchange_rates = [
            ("JPY", "🇯🇵 日元 (JPY)"),
            ("KRW", "🇰🇷 韩元 (KRW)"),
            ("SGD", "🇸🇬 新加坡元 (SGD)"),
            ("HKD", "🇭🇰 港币 (HKD)"),
            ("TWD", "🇹🇼 新台币 (TWD)"),
            ("MYR", "🇲🇾 马来西亚林吉特 (MYR)"),
            ("AUD", "🇦🇺 澳元 (AUD)"),
            ("PHP", "🇵🇭 菲律宾比索 (PHP)"),
        ]
        for code, label in exchange_rates:
            rate_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                 highlightbackground=COLORS["border"],
                                 highlightthickness=1)
            rate_frame.pack(fill="x", padx=28, pady=3)
            rate_inner = tk.Frame(rate_frame, bg=COLORS["card"])
            rate_inner.pack(fill="x", padx=16, pady=8)
            tk.Label(rate_inner, text=label, bg=COLORS["card"], fg=COLORS["text"],
                     font=FONTS["body"]).pack(side="left")
            var = tk.StringVar(value=config.get_exchange_rate(code))
            entry = tk.Entry(rate_inner, textvariable=var,
                            bg=COLORS["input_bg"], fg=COLORS["text"],
                            insertbackground=COLORS["text"], font=FONTS["mono_small"],
                            relief="flat", width=12)
            entry.pack(side="right")
            tk.Label(rate_inner, text="→ CNY", bg=COLORS["card"], fg=COLORS["text3"],
                     font=FONTS["body"]).pack(side="right", padx=(4, 0))
            self._exchange_rate_vars[code] = var

        sep6 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep6.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="⛔ 卖家黑名单", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))
        tk.Label(scroll_frame, text="输入卖家ID，每行一个",
                 bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack(anchor="w", padx=28)

        blacklist_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                  highlightbackground=COLORS["border"],
                                  highlightthickness=1)
        blacklist_frame.pack(fill="x", padx=28, pady=10)
        blacklist_inner = tk.Frame(blacklist_frame, bg=COLORS["card"])
        blacklist_inner.pack(fill="x", padx=16, pady=12)

        self._blacklist_text = tk.Text(
            blacklist_inner, height=4, bg=COLORS["input_bg"], fg=COLORS["text"],
            insertbackground=COLORS["text"], font=FONTS["mono_small"],
            relief="flat",
        )
        saved_blacklist = config.get("seller_blacklist", "")
        if saved_blacklist:
            self._blacklist_text.insert("1.0", saved_blacklist)
        self._blacklist_text.pack(fill="x")

        sep7 = tk.Frame(scroll_frame, bg=COLORS["border"], height=1)
        sep7.pack(fill="x", padx=28, pady=20)

        tk.Label(scroll_frame, text="🎯 拍卖通知模式", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["heading"]).pack(anchor="w", padx=28, pady=(0, 6))

        auction_mode_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                     highlightbackground=COLORS["border"],
                                     highlightthickness=1)
        auction_mode_frame.pack(fill="x", padx=28, pady=10)
        auction_mode_inner = tk.Frame(auction_mode_frame, bg=COLORS["card"])
        auction_mode_inner.pack(fill="x", padx=16, pady=12)

        self._auction_mode_var = tk.StringVar(
            value=config.get("auction_notify_mode", "new")
        )
        modes = [
            ("new", "上新即通知"),
            ("ending", "临近结束时通知"),
        ]
        for mode_val, mode_label in modes:
            rb = tk.Radiobutton(
                auction_mode_inner, text=mode_label, variable=self._auction_mode_var,
                value=mode_val, bg=COLORS["card"], fg=COLORS["text"],
                selectcolor=COLORS["accent"], activebackground=COLORS["card"],
                activeforeground=COLORS["text"], font=FONTS["body"],
            )
            rb.pack(side="left", padx=10)

        threshold_frame = tk.Frame(scroll_frame, bg=COLORS["card"],
                                  highlightbackground=COLORS["border"],
                                  highlightthickness=1)
        threshold_frame.pack(fill="x", padx=28, pady=4)
        threshold_inner = tk.Frame(threshold_frame, bg=COLORS["card"])
        threshold_inner.pack(fill="x", padx=16, pady=8)
        tk.Label(threshold_inner, text="提前通知时间:", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["body"]).pack(side="left")
        self._auction_threshold_var = tk.StringVar(
            value=config.get("auction_ending_threshold", "3600")
        )
        tk.Entry(threshold_inner, textvariable=self._auction_threshold_var,
                 bg=COLORS["input_bg"], fg=COLORS["text"],
                 insertbackground=COLORS["text"], font=FONTS["mono_small"],
                 relief="flat", width=8).pack(side="left", padx=(8, 4))
        tk.Label(threshold_inner, text="秒 (默认3600=1小时)", bg=COLORS["card"],
                 fg=COLORS["text3"], font=FONTS["small"]).pack(side="left")

        save_btn_frame = tk.Frame(scroll_frame, bg=COLORS["bg"])
        save_btn_frame.pack(fill="x", padx=28, pady=(16, 24))
        tk.Button(save_btn_frame, text="💾 保存所有设置", bg=COLORS["success"], fg="white",
                  font=FONTS["body_bold"], relief="flat", padx=24, pady=8,
                  cursor="hand2", command=self._save_all_settings).pack()

    def _start_async_loop(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _toggle_monitoring(self):
        if not self._running:
            self._start_monitoring()
        else:
            self._stop_monitoring()

    def _start_monitoring(self):
        keywords = self.db.get_keywords()
        active_platforms = {kw["platform"] for kw in keywords}
        if not active_platforms:
            messagebox.showwarning("提示", "请先添加关键词后再启动监控。")
            return

        proxy_text = self._proxy_text.get("1.0", "end-1c").strip()
        config.set("proxies", proxy_text)

        if hasattr(self, '_proxy_platforms_var'):
            config.set("proxy_platforms", self._proxy_platforms_var.get().strip())

        if hasattr(self, '_interval_var'):
            interval_val = self._interval_var.get().strip()
            try:
                val = float(interval_val)
                if 0.1 <= val <= 60.0:
                    config.set("poll_interval", str(val))
            except (ValueError, TypeError):
                pass

        self._running = True
        self._session_new = 0
        self._error_stats: dict[str, int] = {}
        self._start_btn.configure(text="⏹ 停止监控", bg=COLORS["danger"],
                                  activebackground="#e11d48")
        self.status_bar.set_status("监控运行中…")
        self.status_bar.set_running(True)
        self.status_bar.clear_warning()
        if hasattr(self, '_monitor_status_label'):
            self._monitor_status_label.configure(text="● 运行中", fg=COLORS["success"])
        self.log_panel.append("开始监控所有平台")

        if self.notifier.telegram_enabled:
            try:
                from src.telegram_bot_service import init_bot_service, start_bot_polling
                bot_service = init_bot_service(self.notifier)
                start_bot_polling()
                self.log_panel.append("Telegram Bot命令服务已启动")
            except Exception as e:
                self.log_panel.append(f"Bot服务启动失败: {e}")

        for platform in active_platforms:
            self._start_platform(platform)
        self._update_platform_status()

    def _start_platform(self, platform: str):
        if platform in self._monitors:
            return
        monitor_cls = PLATFORM_MONITORS.get(platform)
        if not monitor_cls:
            return

        kwargs = {"db": self.db, "notifier": self.notifier,
                  "log_cb": self._thread_safe_log}
        if platform == "carousell":
            regions = [c for c, v in self._carousell_region_vars.items() if v.get()]
            config.set("carousell_regions", regions or ["SG"])
            kwargs["regions"] = regions or ["SG"]

        monitor = monitor_cls(**kwargs)

        self._monitors[platform] = monitor
        future = asyncio.run_coroutine_threadsafe(monitor.start(), self._loop)
        self._tasks[platform] = future

    def _stop_monitoring(self):
        self._running = False
        for m in self._monitors.values():
            m.stop()
        for f in self._tasks.values():
            f.cancel()
        if self._loop and self._loop.is_running():
            for m in self._monitors.values():
                asyncio.run_coroutine_threadsafe(m.cleanup(), self._loop)
        self._monitors.clear()
        self._tasks.clear()

        try:
            from src.telegram_bot_service import stop_bot_polling
            stop_bot_polling()
            self.log_panel.append("Telegram Bot命令服务已停止")
        except Exception:
            pass
        self._start_btn.configure(text="▶ 开始监控", bg=COLORS["success"],
                                  activebackground=COLORS["success_light"])
        self.status_bar.set_status("监控已停止")
        self.status_bar.set_running(False)
        if hasattr(self, '_monitor_status_label'):
            self._monitor_status_label.configure(text="● 已停止", fg=COLORS["text3"])
        self.log_panel.append("监控已停止")
        self._update_platform_status()

    def _update_platform_status(self):
        for pid, item in self._platform_status_items.items():
            item.set_active(pid in self._monitors)

    def _on_new_item(self, item: dict):
        self._session_new += 1
        self.root.after(0, lambda: self._add_item_card(item))
        self.root.after(0, self._refresh_stats)
        self.root.after(0, self._refresh_watchlist_items)
        self.root.after(0, self._update_watchlist_tab_labels)

    def _thread_safe_log(self, msg: str):
        self.root.after(0, lambda: self._process_log(msg))

    def _process_log(self, msg: str):
        self.log_panel.append(msg)
        
        if not hasattr(self, '_error_stats'):
            return
            
        is_error = any(kw in msg.lower() for kw in ["错误", "失败", "429", "403", "超时", "封禁"])
        
        if is_error:
            for platform in ["mercari_jp", "paypay_fleamarket", "fril", "yahoo_auctions", "carousell", "bunjang"]:
                if f"[{platform}]" in msg or platform.replace("_", "") in msg.lower():
                    self._error_stats[platform] = self._error_stats.get(platform, 0) + 1
                    if self._error_stats[platform] >= 5:
                        self.status_bar.set_warning(f"⚠ {platform.split('_')[0]} 频繁出错")
                    break
        
        total_errors = sum(self._error_stats.values())
        if total_errors > 20 and self._running:
            self.status_bar.set_warning(f"⚠ 多平台异常（{total_errors}次错误）")

    def _add_item_card(self, item: dict):
        if self._empty_feed and self._empty_feed.winfo_exists():
            self._empty_feed.destroy()
            self._empty_feed = None

        card = ItemCard(self._scroll_frame, item,
                        open_cb=lambda url: webbrowser.open(url))
        card.pack(fill="x", padx=6, pady=2)
        self._item_cards.append(card)

        if len(self._item_cards) > 300:
            oldest = self._item_cards.pop(0)
            oldest.destroy()

        self._feed_count_var.set(f"商品流 — {len(self._item_cards)} 条")
        self._new_count_var.set(str(self._session_new))
        self._feed_canvas.yview_moveto(0)

    def _refresh_items(self):
        for w in self._scroll_frame.winfo_children():
            w.destroy()
        self._item_cards.clear()
        self._page = 0
        self._has_more = False

        platform = self._active_platform_filter.get()
        keyword = self._search_var.get().strip() or None
        items = self.db.get_items(
            platform=None if platform == "all" else platform,
            keyword=keyword, limit=self._page_size, offset=0,
        )

        total_count = self.db.get_items_count(
            platform=None if platform == "all" else platform,
            keyword=keyword,
        )
        self._has_more = total_count > self._page_size

        if not items:
            self._empty_feed = EmptyState(
                self._scroll_frame, "📦", "暂无商品",
                "添加关键词并开始监控后，新商品将显示在这里"
            )
            self._empty_feed.pack(fill="x", pady=20)
        else:
            self._empty_feed = None
            for item in items:
                card = ItemCard(self._scroll_frame, item,
                                open_cb=lambda url: webbrowser.open(url))
                card.pack(fill="x", padx=6, pady=2)
                self._item_cards.append(card)
            self._page = 1

        self._feed_count_var.set(
            f"商品流 — {total_count} 条" + (" · 下拉加载更多" if self._has_more else "")
        )

    def _load_more_items(self):
        if not self._has_more:
            return
        platform = self._active_platform_filter.get()
        keyword = self._search_var.get().strip() or None
        offset = self._page * self._page_size
        items = self.db.get_items(
            platform=None if platform == "all" else platform,
            keyword=keyword, limit=self._page_size, offset=offset,
        )
        if not items:
            self._has_more = False
            return
        for item in items:
            card = ItemCard(self._scroll_frame, item,
                            open_cb=lambda url: webbrowser.open(url))
            card.pack(fill="x", padx=6, pady=2)
            self._item_cards.append(card)
        self._page += 1

        total_count = self.db.get_items_count(
            platform=None if platform == "all" else platform,
            keyword=keyword,
        )
        loaded = len(self._item_cards)
        self._has_more = loaded < total_count
        self._feed_count_var.set(
            f"商品流 — {loaded}/{total_count} 条" + (" · 下拉加载更多" if self._has_more else "")
        )

    def _refresh_stats(self):
        stats = self.db.get_stats()
        total = stats.get("total", 0)
        today = stats.get("today", 0)
        active_count = len(self._monitors)

        if hasattr(self, "_stat_total"):
            self._stat_total.set_value(f"{total:,}")
            self._stat_today.set_value(f"{today:,}")
            self._stat_platforms.set_value(f"{active_count}/6")
            self._stat_session.set_value(str(self._session_new))

        if hasattr(self, "_stats_labels"):
            self._stats_labels["total"].set(f"{total:,}")
            self._stats_labels["today"].set(f"{today:,}")

        if hasattr(self, "_platform_bars"):
            by_platform = stats.get("by_platform", {})
            max_val = max(by_platform.values()) if by_platform else 1
            for pid, (bar_fill, var, bar_frame) in self._platform_bars.items():
                cnt = by_platform.get(pid, 0)
                var.set(str(cnt))
                if max_val > 0 and bar_frame.winfo_width() > 0:
                    ratio = cnt / max_val
                    bar_fill.configure(width=max(int(ratio * bar_frame.winfo_width()), 0))

        self.status_bar.set_stats(total, today)

    def _filter_platform(self, platform: str):
        self._active_platform_filter.set(platform)
        for pid, btn in self._filter_btns.items():
            if pid == platform:
                color = PLATFORM_COLORS.get(pid, COLORS["accent"])
                btn.configure(bg=color, fg="white")
            else:
                btn.configure(bg=COLORS["bg3"], fg=COLORS["text2"])
        self._refresh_items()

    def _clear_feed(self):
        if messagebox.askyesno("确认", "确定清空显示中的商品流？（不删除数据库记录）"):
            for w in self._scroll_frame.winfo_children():
                w.destroy()
            self._item_cards.clear()
            self._feed_count_var.set("商品流")
            self._empty_feed = EmptyState(
                self._scroll_frame, "📦", "已清空",
                "新商品将继续显示在这里"
            )
            self._empty_feed.pack(fill="x", pady=20)

    def _quick_add_keyword(self):
        kw = self._quick_kw_var.get().strip()
        if not kw:
            return
        first_platform = list(PLATFORM_NAMES.keys())[0]
        ok = self.db.add_keyword(kw, first_platform)
        if ok:
            self._quick_kw_var.set("")
            self._refresh_keywords()
            self.log_panel.append(f"快速添加关键词「{kw}」→ {PLATFORM_NAMES[first_platform]}")
        else:
            messagebox.showinfo("提示", "该关键词已存在")

    def _show_add_keyword_dialog(self):
        dialog = AddKeywordDialog(self.root, self.db, callback=self._refresh_keywords)
        self.root.wait_window(dialog)

    def _edit_keyword(self):
        sel = self._kw_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择要编辑的关键词")
            return
        values = self._kw_tree.item(sel[0], "values")
        if not values:
            return

        kw_name = values[0]
        platform_display = values[1]

        rows = self.db.get_keywords()
        kw_data = None
        for r in rows:
            pname = PLATFORM_NAMES.get(r["platform"], r["platform"])
            if r["keyword"] == kw_name and pname == platform_display:
                kw_data = r
                break

        if not kw_data:
            return

        dialog = EditKeywordDialog(self.root, self.db, kw_data, callback=self._refresh_keywords)
        self.root.wait_window(dialog)

    def _delete_keyword(self):
        sel = self._kw_tree.selection()
        if not sel:
            return
        values = self._kw_tree.item(sel[0], "values")
        if not values:
            return
        kw_name = values[0]
        platform_display = values[1]
        if messagebox.askyesno("确认", f"删除关键词「{kw_name}」？"):
            rows = self.db.get_keywords()
            for r in rows:
                pname = PLATFORM_NAMES.get(r["platform"], r["platform"])
                if r["keyword"] == kw_name and pname == platform_display:
                    self.db.remove_keyword(r["id"])
                    break
            self._refresh_keywords()

    def _toggle_keyword(self):
        sel = self._kw_tree.selection()
        if not sel:
            return
        values = self._kw_tree.item(sel[0], "values")
        if not values:
            return
        kw_name = values[0]
        platform_display = values[1]
        rows = self.db.get_keywords()
        for r in rows:
            pname = PLATFORM_NAMES.get(r["platform"], r["platform"])
            if r["keyword"] == kw_name and pname == platform_display:
                new_enabled = not r.get("enabled", 1)
                self.db.toggle_keyword(r["id"], new_enabled)
                status = "启用" if new_enabled else "禁用"
                self.log_panel.append(f"关键词「{kw_name}」已{status}")
                break
        self._refresh_keywords()

    def _refresh_keywords(self):
        if not hasattr(self, "_kw_tree"):
            return
        for row in self._kw_tree.get_children():
            self._kw_tree.delete(row)
        for kw in self.db.get_keywords():
            pname = PLATFORM_NAMES.get(kw["platform"], kw["platform"])
            min_p = kw.get("min_price", 0) or 0
            max_p = kw.get("max_price", 0) or 0
            if min_p or max_p:
                price_range = f"¥{min_p:,} - ¥{max_p:,}" if max_p else f"¥{min_p:,}+"
            else:
                price_range = "不限"
            poll_interval = kw.get("poll_interval", 0) or 0
            poll_str = f"{poll_interval}s" if poll_interval > 0 else "默认"
            noshops = "是" if kw.get("noshops", 0) else "否"

            conditions = kw.get("allowed_conditions", "")
            if conditions:
                cond_list = conditions.split(",")
                cond_count = len(cond_list)
                cond_display = f"{cond_count}种" if cond_count > 1 else cond_list[0][:4]
            else:
                cond_display = "不限"

            status = "✅ 启用" if kw.get("enabled", 1) else "❌ 禁用"
            self._kw_tree.insert("", "end", values=(
                kw["keyword"], pname, price_range, poll_str, noshops, cond_display, status
            ))

    def _update_notif_settings(self):
        self.notifier.telegram_enabled = self._tg_enabled_var.get()
        self.notifier.telegram_token = self._tg_token_var.get().strip()
        self.notifier.telegram_chat_id = self._tg_chat_var.get().strip()
        config.set("telegram_enabled", self.notifier.telegram_enabled)
        config.set("telegram_token", self.notifier.telegram_token)
        config.set("telegram_chat_id", self.notifier.telegram_chat_id)
        self.db.set_setting("telegram_enabled", "1" if self.notifier.telegram_enabled else "0")
        self.db.set_setting("telegram_token", self.notifier.telegram_token)
        self.db.set_setting("telegram_chat_id", self.notifier.telegram_chat_id)

        if hasattr(self, '_discord_webhook_var'):
            discord_url = self._discord_webhook_var.get().strip()
            self.notifier.discord_enabled = bool(discord_url) and self._discord_enabled_var.get()
            self.notifier.discord_webhook_url = discord_url
            config.set("discord_enabled", self.notifier.discord_enabled)
            config.set("discord_webhook_url", discord_url)
            self.db.set_setting("discord_webhook_url", discord_url)

        proxy_text = self._proxy_text.get("1.0", "end-1c").strip()
        config.set("proxies", proxy_text)

        if hasattr(self, '_proxy_platforms_var'):
            config.set("proxy_platforms", self._proxy_platforms_var.get().strip())

        if hasattr(self, '_interval_var'):
            interval_val = self._interval_var.get().strip()
            try:
                val = float(interval_val)
                if 0.1 <= val <= 60.0:
                    config.set("poll_interval", str(val))
            except (ValueError, TypeError):
                pass

    def _save_all_settings(self):
        try:
            proxy_text = self._proxy_text.get("1.0", "end-1c").strip()
            config.set("proxies", proxy_text)

            if hasattr(self, '_proxy_platforms_var'):
                config.set("proxy_platforms", self._proxy_platforms_var.get().strip())

            blacklist_text = self._blacklist_text.get("1.0", "end-1c").strip()
            config.set("seller_blacklist", blacklist_text)

            for code, var in self._exchange_rate_vars.items():
                rate_str = var.get().strip()
                if rate_str:
                    try:
                        float(rate_str)
                        rates = config.get_all_exchange_rates()
                        rates[code.lower()] = rate_str
                        config.set("exchange_rates", rates)
                    except ValueError:
                        pass

            auction_mode = self._auction_mode_var.get()
            config.set("auction_notify_mode", auction_mode)

            threshold = self._auction_threshold_var.get().strip()
            try:
                float(threshold)
                config.set("auction_ending_threshold", threshold)
            except ValueError:
                pass

            self._update_notif_settings()

            for pid, var in self._interval_vars.items():
                try:
                    val_str = var.get().strip()
                    if val_str == "":
                        intervals = config.get("per_platform_interval", {})
                        intervals.pop(pid, None)
                        config.set("per_platform_interval", intervals)
                    else:
                        val = float(val_str)
                        if 0.05 <= val <= 3600.0:
                            intervals = config.get("per_platform_interval", {})
                            intervals[pid] = val_str
                            config.set("per_platform_interval", intervals)
                            if val < 0.3 and pid != "carousell":
                                pname = PLATFORM_NAMES.get(pid, pid)
                                self.log_panel.append(f"⚠️ {pname} 间隔设为 {val}s，建议不低于 0.3s")
                except (ValueError, TypeError):
                    pass

            messagebox.showinfo("成功", "所有设置已保存！")
            self.log_panel.append("设置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def _test_telegram(self):
        self._update_notif_settings()
        self._tg_status_label.config(text="⏳ 测试中...", fg=COLORS["warning"])

        def _do_test():
            ok, msg = self.notifier.test_telegram()
            color = COLORS["success"] if ok else COLORS["danger"]
            self.root.after(0, lambda: self._tg_status_label.config(text=msg, fg=color))

        threading.Thread(target=_do_test, daemon=True).start()

    def _test_discord(self):
        self._update_notif_settings()
        self._discord_status_label.config(text="⏳ 测试中...", fg=COLORS["warning"])

        def _do_test():
            ok, msg = self.notifier.test_discord()
            color = COLORS["success"] if ok else COLORS["danger"]
            self.root.after(0, lambda: self._discord_status_label.config(text=msg, fg=color))

        threading.Thread(target=_do_test, daemon=True).start()

    def _update_monitor_status(self):
        if hasattr(self, '_monitor_status_label'):
            if "mercari_jp" in self._monitors:
                self._monitor_status_label.config(
                    text="● 运行中", fg=COLORS["success"],
                )
            else:
                self._monitor_status_label.config(
                    text="● 待启动", fg=COLORS["text3"],
                )

    def _on_close(self):
        self._stop_monitoring()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self.root.destroy()

    def _start_auto_refresh(self):
        def refresh_loop():
            if self._running:
                try:
                    self._refresh_watchlist_items()
                    self._refresh_sellers()
                    self._update_watchlist_tab_labels()
                except Exception:
                    pass
                self.root.after(5000, refresh_loop)

        self.root.after(5000, refresh_loop)

    def run(self):
        self._start_auto_refresh()
        self.root.mainloop()


class AddKeywordDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, callback=None):
        super().__init__(parent)
        self.db = db
        self.callback = callback
        self.title("添加关键词")
        self.geometry("580x920")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])
        self.grab_set()
        self.transient(parent)
        self._selected_platform = list(PLATFORM_NAMES.keys())[0]
        self._build()

    def _build(self):
        tk.Label(self, text="➕ 添加监控关键词", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["title"]).pack(padx=28, pady=(24, 16), anchor="w")

        sep = tk.Frame(self, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=28, pady=(0, 16))

        kw_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                           highlightthickness=1)
        kw_frame.pack(fill="x", padx=28, pady=6)
        kw_inner = tk.Frame(kw_frame, bg=COLORS["card"])
        kw_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(kw_inner, text="🔑 关键词", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))
        self._kw = tk.StringVar()
        kw_entry = tk.Entry(kw_inner, textvariable=self._kw, bg=COLORS["input_bg"],
                            fg=COLORS["text"], font=FONTS["body"], bd=0,
                            relief="flat", insertbackground=COLORS["text"],
                            highlightbackground=COLORS["border"],
                            highlightthickness=0)
        kw_entry.pack(fill="x", ipady=7)

        platform_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                                 highlightthickness=1)
        platform_frame.pack(fill="x", padx=28, pady=6)
        platform_inner = tk.Frame(platform_frame, bg=COLORS["card"])
        platform_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(platform_inner, text="🌐 目标平台（可多选）", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))

        all_platforms_btn_frame = tk.Frame(platform_inner, bg=COLORS["card"])
        all_platforms_btn_frame.pack(fill="x", pady=(0, 6))
        self._all_platforms_var = tk.BooleanVar(value=True)
        all_platforms_cb = tk.Checkbutton(
            all_platforms_btn_frame, text="✓ 监控所有平台",
            variable=self._all_platforms_var,
            command=self._on_all_platforms_toggle,
            bg=COLORS["card"], fg=COLORS["accent"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["accent"], font=FONTS["body_bold"],
        )
        all_platforms_cb.pack(side="left")

        self._platform_vars = {}
        platforms_grid = tk.Frame(platform_inner, bg=COLORS["card"])
        platforms_grid.pack(fill="x")

        for i, (pid, pname) in enumerate(PLATFORM_NAMES.items()):
            var = tk.BooleanVar(value=True)
            self._platform_vars[pid] = var
            row_idx = i // 3
            col_idx = i % 3
            cb = tk.Checkbutton(
                platforms_grid, text=pname, variable=var,
                command=self._on_platform_changed,
                bg=COLORS["card"], fg=COLORS["text"],
                selectcolor=COLORS["accent"], activebackground=COLORS["card"],
                activeforeground=COLORS["text"], font=FONTS["small"],
            )
            cb.grid(row=row_idx, column=col_idx, sticky="w", padx=(0, 16), pady=2)

        price_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                              highlightthickness=1)
        price_frame.pack(fill="x", padx=28, pady=6)
        price_inner = tk.Frame(price_frame, bg=COLORS["card"])
        price_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(price_inner, text="💰 价格范围（留空 = 不限）", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))
        price_row = tk.Frame(price_inner, bg=COLORS["card"])
        price_row.pack(fill="x")
        self._min_price = tk.IntVar(value=0)
        self._max_price = tk.IntVar(value=0)
        min_entry = tk.Entry(price_row, textvariable=self._min_price,
                             bg=COLORS["input_bg"], fg=COLORS["text"],
                             font=FONTS["body"], bd=0, relief="flat", width=12,
                             insertbackground=COLORS["text"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=0)
        min_entry.pack(side="left", ipady=5)
        tk.Label(price_row, text=" — ", bg=COLORS["card"], fg=COLORS["text3"],
                 font=FONTS["body_bold"]).pack(side="left", padx=6)
        max_entry = tk.Entry(price_row, textvariable=self._max_price,
                             bg=COLORS["input_bg"], fg=COLORS["text"],
                             font=FONTS["body"], bd=0, relief="flat", width=12,
                             insertbackground=COLORS["text"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=0)
        max_entry.pack(side="left", ipady=5)

        poll_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                             highlightthickness=1)
        poll_frame.pack(fill="x", padx=28, pady=6)
        poll_inner = tk.Frame(poll_frame, bg=COLORS["card"])
        poll_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(poll_inner, text="⏱️ 自定义轮询间隔（秒，留空使用全局默认值）",
                 bg=COLORS["card"], fg=COLORS["text2"], font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))
        self._poll_interval = tk.DoubleVar(value=0)
        poll_entry = tk.Entry(poll_inner, textvariable=self._poll_interval,
                             bg=COLORS["input_bg"], fg=COLORS["text"],
                             font=FONTS["body"], bd=0, relief="flat", width=12,
                             insertbackground=COLORS["text"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=0)
        poll_entry.pack(anchor="w")

        options_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                               highlightthickness=1)
        options_frame.pack(fill="x", padx=28, pady=6)
        options_inner = tk.Frame(options_frame, bg=COLORS["card"])
        options_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(options_inner, text="🔧 高级选项", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 8))
        self._noshops_var = tk.BooleanVar(value=False)
        noshops_cb = tk.Checkbutton(
            options_inner, text="#noshops# 过滤商城卖家（屏蔽官方/店铺商品）",
            variable=self._noshops_var, bg=COLORS["card"], fg=COLORS["text"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["text"], font=FONTS["body"],
        )
        noshops_cb.pack(anchor="w")

        cond_label = tk.Label(options_inner, text="📊 商品成色筛选（可多选）：",
                              bg=COLORS["card"], fg=COLORS["text2"], font=FONTS["subheading"])
        cond_label.pack(anchor="w", pady=(12, 6))

        self._condition_vars = {}
        conditions = [
            ("new", "全新"),
            ("like_new", "几乎全新"),
            ("very_good", "非常好"),
            ("good", "良好"),
            ("acceptable", "可接受"),
            ("poor", "较差"),
        ]

        all_conditions_btn_frame = tk.Frame(options_inner, bg=COLORS["card"])
        all_conditions_btn_frame.pack(fill="x", pady=(6, 4))
        self._all_conditions_var = tk.BooleanVar(value=True)
        all_conditions_cb = tk.Checkbutton(
            all_conditions_btn_frame, text="✓ 全选成色",
            variable=self._all_conditions_var,
            command=self._on_all_conditions_toggle,
            bg=COLORS["card"], fg=COLORS["accent"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["accent"], font=FONTS["body_bold"],
        )
        all_conditions_cb.pack(side="left")

        cond_row1 = tk.Frame(options_inner, bg=COLORS["card"])
        cond_row1.pack(fill="x")
        cond_row2 = tk.Frame(options_inner, bg=COLORS["card"])
        cond_row2.pack(fill="x", pady=(4, 0))

        for i, (cond_val, cond_label_text) in enumerate(conditions):
            var = tk.BooleanVar(value=True)
            self._condition_vars[cond_val] = var
            cb = tk.Checkbutton(
                cond_row1 if i < 3 else cond_row2,
                text=cond_label_text, variable=var,
                command=self._on_condition_changed,
                bg=COLORS["card"], fg=COLORS["text"],
                selectcolor=COLORS["accent"], activebackground=COLORS["card"],
                activeforeground=COLORS["text"], font=FONTS["small"],
            )
            cb.pack(side="left", padx=(0, 12))

        price_drop_frame = tk.Frame(options_inner, bg=COLORS["card"])
        price_drop_frame.pack(fill="x", pady=(12, 0))
        self._price_drop_var = tk.BooleanVar(value=True)
        price_drop_cb = tk.Checkbutton(
            price_drop_frame, text="📉 启用降价提醒（价格下降时推送通知）",
            variable=self._price_drop_var,
            bg=COLORS["card"], fg=COLORS["text"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["text"], font=FONTS["body"],
        )
        price_drop_cb.pack(anchor="w")

        btn_frame = tk.Frame(self, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=28, pady=(24, 20))
        tk.Button(btn_frame, text="取消", bg=COLORS["card"], fg=COLORS["text2"],
                  font=FONTS["body_bold"], bd=0, relief="flat", highlightbackground=COLORS["border"],
                  highlightthickness=1, padx=22, pady=8,
                  cursor="hand2", command=self.destroy).pack(side="right")
        tk.Button(btn_frame, text="✅ 添加关键词", bg=COLORS["accent"], fg="white",
                  font=FONTS["body_bold"], bd=0, relief="flat", padx=26, pady=8,
                  cursor="hand2", command=self._submit).pack(side="right", padx=(0, 10))

    def _on_all_platforms_toggle(self):
        is_all = self._all_platforms_var.get()
        for var in self._platform_vars.values():
            var.set(is_all)

    def _on_platform_changed(self):
        all_selected = all(var.get() for var in self._platform_vars.values())
        self._all_platforms_var.set(all_selected)

    def _on_all_conditions_toggle(self):
        is_all = self._all_conditions_var.get()
        for var in self._condition_vars.values():
            var.set(is_all)

    def _on_condition_changed(self):
        all_selected = all(var.get() for var in self._condition_vars.values())
        self._all_conditions_var.set(all_selected)

    def _submit(self):
        kw = self._kw.get().strip()
        if not kw:
            messagebox.showwarning("提示", "关键词不能为空", parent=self)
            return
        poll_interval = self._poll_interval.get() or 0
        noshops = self._noshops_var.get()
        price_drop = self._price_drop_var.get()

        selected_platforms = [pid for pid, var in self._platform_vars.items() if var.get()]
        if not selected_platforms:
            messagebox.showwarning("提示", "请至少选择一个平台", parent=self)
            return

        selected_conditions = [
            cond for cond, var in self._condition_vars.items() if var.get()
        ]
        allowed_conditions = ",".join(selected_conditions) if selected_conditions else ""

        success_count = 0
        exists_count = 0

        for platform_id in selected_platforms:
            ok = self.db.add_keyword(
                kw, platform_id,
                self._min_price.get(), self._max_price.get(),
                poll_interval=poll_interval,
                noshops=noshops,
                allowed_conditions=allowed_conditions,
                price_drop=price_drop
            )
            if ok:
                success_count += 1
            else:
                exists_count += 1

        if success_count > 0:
            if self.callback:
                self.callback()
            platform_names = [PLATFORM_NAMES[p] for p in selected_platforms]
            msg = f"成功添加到 {success_count} 个平台：{', '.join(platform_names)}"
            if exists_count > 0:
                msg += f"\n（{exists_count} 个平台已存在该关键词）"
            messagebox.showinfo("成功", msg, parent=self)
            self.destroy()
        else:
            messagebox.showinfo("提示", "该关键词在所选平台上都已存在", parent=self)


class EditKeywordDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, kw_data: dict, callback=None):
        super().__init__(parent)
        self.db = db
        self.kw_data = kw_data
        self.callback = callback
        self.title("编辑关键词")
        self.geometry("580x920")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])
        self.grab_set()
        self.transient(parent)
        self._selected_platform = kw_data["platform"]
        self._build()

    def _build(self):
        tk.Label(self, text="✏️ 编辑监控关键词", bg=COLORS["bg"], fg=COLORS["text"],
                 font=FONTS["title"]).pack(padx=28, pady=(24, 16), anchor="w")

        sep = tk.Frame(self, bg=COLORS["border"], height=1)
        sep.pack(fill="x", padx=28, pady=(0, 16))

        kw_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                           highlightthickness=1)
        kw_frame.pack(fill="x", padx=28, pady=6)
        kw_inner = tk.Frame(kw_frame, bg=COLORS["card"])
        kw_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(kw_inner, text="🔑 关键词", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))
        self._kw = tk.StringVar(value=self.kw_data.get("keyword", ""))
        kw_entry = tk.Entry(kw_inner, textvariable=self._kw, bg=COLORS["input_bg"],
                            fg=COLORS["text"], font=FONTS["body"], bd=0,
                            relief="flat", insertbackground=COLORS["text"],
                            highlightbackground=COLORS["border"],
                            highlightthickness=0)
        kw_entry.pack(fill="x", ipady=7)

        platform_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                                 highlightthickness=1)
        platform_frame.pack(fill="x", padx=28, pady=6)
        platform_inner = tk.Frame(platform_frame, bg=COLORS["card"])
        platform_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(platform_inner, text="🌐 目标平台", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))

        platform_names_list = list(PLATFORM_NAMES.values())
        current_platform_name = PLATFORM_NAMES.get(self._selected_platform, platform_names_list[0])
        self._platform_combo_var = tk.StringVar(value=current_platform_name)
        platform_combo = ttk.Combobox(
            platform_inner, textvariable=self._platform_combo_var,
            values=platform_names_list, state="readonly",
            font=FONTS["body"], width=28,
        )
        platform_combo.pack(fill="x")
        platform_combo.bind("<<ComboboxSelected>>", self._on_platform_selected)

        price_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                              highlightthickness=1)
        price_frame.pack(fill="x", padx=28, pady=6)
        price_inner = tk.Frame(price_frame, bg=COLORS["card"])
        price_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(price_inner, text="💰 价格范围（留空 = 不限）", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))
        price_row = tk.Frame(price_inner, bg=COLORS["card"])
        price_row.pack(fill="x")
        self._min_price = tk.IntVar(value=self.kw_data.get("min_price", 0) or 0)
        self._max_price = tk.IntVar(value=self.kw_data.get("max_price", 0) or 0)
        min_entry = tk.Entry(price_row, textvariable=self._min_price,
                             bg=COLORS["input_bg"], fg=COLORS["text"],
                             font=FONTS["body"], bd=0, relief="flat", width=12,
                             insertbackground=COLORS["text"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=0)
        min_entry.pack(side="left", ipady=5)
        tk.Label(price_row, text=" — ", bg=COLORS["card"], fg=COLORS["text3"],
                 font=FONTS["body_bold"]).pack(side="left", padx=6)
        max_entry = tk.Entry(price_row, textvariable=self._max_price,
                             bg=COLORS["input_bg"], fg=COLORS["text"],
                             font=FONTS["body"], bd=0, relief="flat", width=12,
                             insertbackground=COLORS["text"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=0)
        max_entry.pack(side="left", ipady=5)

        poll_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                             highlightthickness=1)
        poll_frame.pack(fill="x", padx=28, pady=6)
        poll_inner = tk.Frame(poll_frame, bg=COLORS["card"])
        poll_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(poll_inner, text="⏱️ 自定义轮询间隔（秒，留空使用全局默认值）",
                 bg=COLORS["card"], fg=COLORS["text2"], font=FONTS["subheading"]).pack(anchor="w", pady=(0, 6))
        self._poll_interval = tk.DoubleVar(value=self.kw_data.get("poll_interval", 0) or 0)
        poll_entry = tk.Entry(poll_inner, textvariable=self._poll_interval,
                             bg=COLORS["input_bg"], fg=COLORS["text"],
                             font=FONTS["body"], bd=0, relief="flat", width=12,
                             insertbackground=COLORS["text"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=0)
        poll_entry.pack(anchor="w")

        options_frame = tk.Frame(self, bg=COLORS["card"], highlightbackground=COLORS["border"],
                               highlightthickness=1)
        options_frame.pack(fill="x", padx=28, pady=6)
        options_inner = tk.Frame(options_frame, bg=COLORS["card"])
        options_inner.pack(fill="x", padx=14, pady=10)
        tk.Label(options_inner, text="🔧 高级选项", bg=COLORS["card"], fg=COLORS["text2"],
                 font=FONTS["subheading"]).pack(anchor="w", pady=(0, 8))
        self._noshops_var = tk.BooleanVar(value=bool(self.kw_data.get("noshops", 0)))
        noshops_cb = tk.Checkbutton(
            options_inner, text="#noshops# 过滤商城卖家（屏蔽官方/店铺商品）",
            variable=self._noshops_var, bg=COLORS["card"], fg=COLORS["text"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["text"], font=FONTS["body"],
        )
        noshops_cb.pack(anchor="w")

        cond_label = tk.Label(options_inner, text="📊 商品成色筛选（可多选）：",
                              bg=COLORS["card"], fg=COLORS["text2"], font=FONTS["subheading"])
        cond_label.pack(anchor="w", pady=(12, 6))

        self._condition_vars = {}
        conditions = [
            ("new", "全新"),
            ("like_new", "几乎全新"),
            ("very_good", "非常好"),
            ("good", "良好"),
            ("acceptable", "可接受"),
            ("poor", "较差"),
        ]
        
        existing_conditions = set()
        raw_conditions = self.kw_data.get("allowed_conditions", "")
        if raw_conditions:
            existing_conditions = {c.strip() for c in raw_conditions.split(",") if c.strip()}

        all_selected_by_default = len(existing_conditions) == 0 or len(existing_conditions) == len(conditions)

        all_conditions_btn_frame = tk.Frame(options_inner, bg=COLORS["card"])
        all_conditions_btn_frame.pack(fill="x", pady=(6, 4))
        self._all_conditions_var = tk.BooleanVar(value=all_selected_by_default)
        all_conditions_cb = tk.Checkbutton(
            all_conditions_btn_frame, text="✓ 全选成色",
            variable=self._all_conditions_var,
            command=self._on_all_conditions_toggle,
            bg=COLORS["card"], fg=COLORS["accent"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["accent"], font=FONTS["body_bold"],
        )
        all_conditions_cb.pack(side="left")

        cond_row1 = tk.Frame(options_inner, bg=COLORS["card"])
        cond_row1.pack(fill="x")
        cond_row2 = tk.Frame(options_inner, bg=COLORS["card"])
        cond_row2.pack(fill="x", pady=(4, 0))

        for i, (cond_val, cond_label_text) in enumerate(conditions):
            if all_selected_by_default:
                var = tk.BooleanVar(value=True)
            else:
                var = tk.BooleanVar(value=(cond_val in existing_conditions))
            self._condition_vars[cond_val] = var
            cb = tk.Checkbutton(
                cond_row1 if i < 3 else cond_row2,
                text=cond_label_text, variable=var,
                command=self._on_condition_changed,
                bg=COLORS["card"], fg=COLORS["text"],
                selectcolor=COLORS["accent"], activebackground=COLORS["card"],
                activeforeground=COLORS["text"], font=FONTS["small"],
            )
            cb.pack(side="left", padx=(0, 12))

        price_drop_frame = tk.Frame(options_inner, bg=COLORS["card"])
        price_drop_frame.pack(fill="x", pady=(12, 0))
        current_price_drop = bool(self.kw_data.get("price_drop", 1))
        self._price_drop_var = tk.BooleanVar(value=current_price_drop)
        price_drop_cb = tk.Checkbutton(
            price_drop_frame, text="📉 启用降价提醒（价格下降时推送通知）",
            variable=self._price_drop_var,
            bg=COLORS["card"], fg=COLORS["text"],
            selectcolor=COLORS["accent"], activebackground=COLORS["card"],
            activeforeground=COLORS["text"], font=FONTS["body"],
        )
        price_drop_cb.pack(anchor="w")

        btn_frame = tk.Frame(self, bg=COLORS["bg"])
        btn_frame.pack(fill="x", padx=28, pady=(24, 20))
        tk.Button(btn_frame, text="取消", bg=COLORS["card"], fg=COLORS["text2"],
                  font=FONTS["body_bold"], bd=0, relief="flat", highlightbackground=COLORS["border"],
                  highlightthickness=1, padx=22, pady=8,
                  cursor="hand2", command=self.destroy).pack(side="right")
        tk.Button(btn_frame, text="✅ 保存修改", bg=COLORS["accent"], fg="white",
                  font=FONTS["body_bold"], bd=0, relief="flat", padx=26, pady=8,
                  cursor="hand2", command=self._submit).pack(side="right", padx=(0, 10))

    def _on_platform_selected(self, event=None):
        selected_name = self._platform_combo_var.get()
        for pid, pname in PLATFORM_NAMES.items():
            if pname == selected_name:
                self._selected_platform = pid
                break

    def _on_all_conditions_toggle(self):
        is_all = self._all_conditions_var.get()
        for var in self._condition_vars.values():
            var.set(is_all)

    def _on_condition_changed(self):
        all_selected = all(var.get() for var in self._condition_vars.values())
        self._all_conditions_var.set(all_selected)

    def _submit(self):
        kw = self._kw.get().strip()
        if not kw:
            messagebox.showwarning("提示", "关键词不能为空", parent=self)
            return

        poll_interval = self._poll_interval.get() or 0
        noshops = self._noshops_var.get()
        price_drop = self._price_drop_var.get()

        selected_conditions = [
            cond for cond, var in self._condition_vars.items() if var.get()
        ]
        allowed_conditions = ",".join(selected_conditions) if selected_conditions else ""

        ok = self.db.update_keyword(
            self.kw_data["id"],
            keyword=kw,
            platform=self._selected_platform,
            min_price=self._min_price.get(),
            max_price=self._max_price.get(),
            poll_interval=poll_interval,
            noshops=int(noshops),
            allowed_conditions=allowed_conditions,
            price_drop=int(price_drop)
        )
        if ok:
            if self.callback:
                self.callback()
            self.destroy()
        else:
            messagebox.showerror("错误", "更新失败", parent=self)


class LoginDialog(tk.Toplevel):
    def __init__(self, parent, db: Database, on_success=None):
        super().__init__(parent)
        self.db = db
        self.on_success = on_success
        self.title("管理员登录 - 二手监控助手")
        
        width = 460
        height = 560
        screen_width = parent.winfo_screenwidth()
        screen_height = parent.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        self.resizable(False, False)
        self.configure(bg=COLORS["bg"])

        self.root_window = parent
        self._login_successful = False
        
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._build()
        
        self.after(100, self._grab_focus)

    def _grab_focus(self):
        try:
            self.grab_set()
            self.focus_force()
            self.lift()
        except:
            pass

    def _on_close(self):
        self._login_successful = False
        try:
            self.grab_release()
        except:
            pass
        self.destroy()

    def _build(self):
        main_frame = tk.Frame(self, bg=COLORS["bg"])
        main_frame.pack(fill="both", expand=True, padx=50, pady=40)

        logo_frame = tk.Frame(main_frame, bg=COLORS["bg"])
        logo_frame.pack(pady=(10, 35))
        tk.Label(logo_frame, text="🔐", bg=COLORS["bg"],
                font=("Segoe UI", 56)).pack()
        tk.Label(logo_frame, text="二手监控助手", bg=COLORS["bg"],
                fg=COLORS["accent"], font=("Segoe UI", 24, "bold")).pack(pady=(16, 4))
        tk.Label(logo_frame, text="安全登录系统", bg=COLORS["bg"],
                fg=COLORS["text3"], font=FONTS["small"]).pack()

        card = tk.Frame(main_frame, bg=COLORS["card"], highlightbackground=COLORS["border"],
                       highlightthickness=1)
        card.pack(fill="x", pady=(0, 25))
        inner = tk.Frame(card, bg=COLORS["card"])
        inner.pack(fill="x", padx=24, pady=24)

        tk.Label(inner, text="👤 管理员账号", bg=COLORS["card"], fg=COLORS["text2"],
                font=FONTS["subheading"]).pack(anchor="w", pady=(0, 8))
        self._username = tk.StringVar()
        username_entry = tk.Entry(inner, textvariable=self._username,
                                bg=COLORS["input_bg"], fg=COLORS["text"],
                                font=FONTS["body"], bd=0, relief="flat",
                                insertbackground=COLORS["text"])
        username_entry.pack(fill="x", ipady=8)

        tk.Label(inner, text="🔒 登录密码", bg=COLORS["card"], fg=COLORS["text2"],
                font=FONTS["subheading"]).pack(anchor="w", pady=(18, 8))
        self._password = tk.StringVar()
        password_entry = tk.Entry(inner, textvariable=self._password,
                                bg=COLORS["input_bg"], fg=COLORS["text"],
                                font=FONTS["body"], bd=0, relief="flat",
                                show="•", insertbackground=COLORS["text"])
        password_entry.pack(fill="x", ipady=8)

        password_entry.bind("<Return>", lambda e: self._login())

        hint = tk.Label(inner, text="请输入管理员账号和密码以继续",
                       bg=COLORS["card"], fg=COLORS["text3"],
                       font=FONTS["small"])
        hint.pack(anchor="w", pady=(10, 0))
        
        default_hint = tk.Label(inner, text="默认账号: admin / admin123",
                               bg=COLORS["card"], fg=COLORS["accent"],
                               font=("Segoe UI", 9))
        default_hint.pack(anchor="w", pady=(4, 0))

        login_btn = tk.Button(main_frame, text="🔑 登录系统", bg=COLORS["accent"], fg="white",
                             font=("Segoe UI", 13, "bold"), bd=0, relief="flat",
                             padx=36, pady=12, cursor="hand2",
                             activebackground=COLORS["accent3"],
                             command=self._login)
        login_btn.pack(pady=(15, 0))

        footer = tk.Frame(main_frame, bg=COLORS["bg"])
        footer.pack(side="bottom", fill="x", pady=(25, 0))
        tk.Label(footer, text="© 2024 二手监控助手 · 安全登录系统",
               bg=COLORS["bg"], fg=COLORS["text3"], font=FONTS["small"]).pack()

    def _login(self):
        username = self._username.get().strip()
        password = self._password.get().strip()
        
        if not username or not password:
            messagebox.showwarning("提示", "请输入用户名和密码", parent=self)
            return

        try:
            user = self.db.verify_user(username, password)
            if user:
                token = self.db.create_token(user["id"])
                self._login_successful = True
                if self.on_success:
                    self.on_success(token, user)
                self.destroy()
            else:
                messagebox.showerror("登录失败", "用户名或密码错误，请重试", parent=self)
                self._password.set("")
        except Exception as e:
            messagebox.showerror("错误", f"登录过程出错: {e}", parent=self)