import tkinter as tk
from tkinter import ttk

COLORS = {
    "bg": "#f5f7fa",
    "bg2": "#ffffff",
    "bg3": "#f8f9fc",
    "bg4": "#eef0f5",
    "bg5": "#e8ebf0",
    "accent": "#ff6b8a",
    "accent2": "#ff8fa3",
    "accent3": "#e85a77",
    "accent_light": "#ffb3c6",
    "accent_bg": "#fff0f3",
    "success": "#22c55e",
    "success_bg": "#dcfce7",
    "success_light": "#4ade80",
    "warning": "#f59e0b",
    "warning_bg": "#fef3c7",
    "warning_light": "#fbbf24",
    "danger": "#ef4444",
    "danger_bg": "#fee2e2",
    "danger_light": "#f87171",
    "info": "#3b82f6",
    "info_bg": "#dbeafe",
    "text": "#1a1d26",
    "text2": "#5a6177",
    "text3": "#8b92a5",
    "border": "#e8ecf1",
    "border2": "#dcdfe6",
    "card": "#ffffff",
    "card_hover": "#fafbfd",
    "card_border": "#e8ecf1",
    "input_bg": "#f0f2f5",
    "mercari": "#ff4f4f",
    "bunjang": "#ff6b35",
    "paypay": "#3b82f6",
    "fril": "#e91e8c",
    "yahoo_auctions": "#ff0033",
    "carousell": "#f04e23",
    "gradient_start": "#667eea",
    "gradient_mid": "#764ba2",
    "gradient_end": "#f093fb",
}

PLATFORM_COLORS = {
    "mercari_jp": COLORS["mercari"],
    "bunjang": COLORS["bunjang"],
    "paypay_fleamarket": COLORS["paypay"],
    "fril": COLORS["fril"],
    "yahoo_auctions": COLORS["yahoo_auctions"],
    "carousell": COLORS["carousell"],
}

FONTS = {
    "logo": ("Segoe UI", 15, "bold"),
    "title": ("Segoe UI", 16, "bold"),
    "heading": ("Segoe UI", 12, "bold"),
    "subheading": ("Segoe UI", 11, "bold"),
    "body": ("Segoe UI", 10),
    "body_bold": ("Segoe UI", 10, "bold"),
    "small": ("Segoe UI", 9),
    "tiny": ("Segoe UI", 8),
    "mono": ("Cascadia Code", 9),
    "mono_small": ("Cascadia Code", 8),
    "stat_value": ("Segoe UI", 22, "bold"),
    "stat_label": ("Segoe UI", 9),
    "price": ("Segoe UI", 14, "bold"),
    "item_name": ("Segoe UI", 10, "bold"),
}

CURRENCY_SYMBOLS = {
    "JPY": "¥",
    "KRW": "₩",
    "SGD": "S$",
    "HKD": "HK$",
    "TWD": "NT$",
    "MYR": "RM",
    "AUD": "A$",
    "PHP": "₱",
}


def apply_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=COLORS["bg"])

    style.configure(".", background=COLORS["bg"], foreground=COLORS["text"],
                    bordercolor=COLORS["border"], troughcolor=COLORS["bg3"],
                    selectbackground=COLORS["accent"], selectforeground="#ffffff",
                    fieldbackground=COLORS["input_bg"])

    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["card"], relief="flat")
    style.configure("Sidebar.TFrame", background=COLORS["bg2"])
    style.configure("Header.TFrame", background=COLORS["bg2"])
    style.configure("Stats.TFrame", background=COLORS["card"])

    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"],
                    font=FONTS["body"])
    style.configure("Title.TLabel", font=FONTS["title"], foreground=COLORS["accent"])
    style.configure("Heading.TLabel", font=FONTS["heading"], foreground=COLORS["text"])
    style.configure("Subheading.TLabel", font=FONTS["subheading"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", foreground=COLORS["text2"], font=FONTS["small"])

    style.map("TButton",
              background=[("active", COLORS["accent"]), ("!active", COLORS["bg2"])],
              foreground=[("active", "#ffffff"), ("!active", COLORS["text"])],
              relief=[("pressed", "flat"), ("!pressed", "flat")])

    style.configure("Accent.TButton", background=COLORS["accent"], foreground="#ffffff",
                    font=FONTS["body_bold"], padding=(16, 8))
    style.map("Accent.TButton",
              background=[("active", COLORS["accent3"]), ("disabled", COLORS["bg5"])])

    style.configure("Modern.TEntry", fieldbackground=COLORS["input_bg"],
                    foreground=COLORS["text"], insertcolor=COLORS["text"],
                    padding=(12, 8), relief="flat")
    style.configure("Modern.TCombobox", fieldbackground=COLORS["input_bg"],
                    foreground=COLORS["text"], padding=(8, 4))
    style.configure("Tiny.TLabel", foreground=COLORS["text3"], font=FONTS["tiny"])
    style.configure("Success.TLabel", foreground=COLORS["success"])
    style.configure("Danger.TLabel", foreground=COLORS["danger"])
    style.configure("Warning.TLabel", foreground=COLORS["warning"])
    style.configure("Sidebar.TLabel", background=COLORS["bg2"], foreground=COLORS["text"])
    style.configure("Header.TLabel", background=COLORS["bg2"], foreground=COLORS["text"])
    style.configure("StatValue.TLabel", font=FONTS["stat_value"], foreground=COLORS["text"])
    style.configure("StatLabel.TLabel", font=FONTS["stat_label"], foreground=COLORS["text2"])
    style.configure("Price.TLabel", font=FONTS["price"], foreground=COLORS["success"])
    style.configure("ItemName.TLabel", font=FONTS["item_name"], foreground=COLORS["text"])

    style.configure("TButton", background=COLORS["accent"], foreground="white",
                    font=FONTS["body_bold"], borderwidth=0, focusthickness=0,
                    padding=(14, 7))
    style.map("TButton",
              background=[("active", COLORS["accent3"]), ("pressed", COLORS["accent3"])],
              foreground=[("disabled", COLORS["text3"])])

    style.configure("Danger.TButton", background=COLORS["danger"])
    style.map("Danger.TButton", background=[("active", "#e11d48")])

    style.configure("Success.TButton", background=COLORS["success"])
    style.map("Success.TButton", background=[("active", "#059669")])

    style.configure("Ghost.TButton", background=COLORS["bg3"], foreground=COLORS["text2"],
                    padding=(10, 5))
    style.map("Ghost.TButton",
              background=[("active", COLORS["bg4"])],
              foreground=[("active", COLORS["text"])])

    style.configure("Outline.TButton", background=COLORS["bg"], foreground=COLORS["text2"],
                    borderwidth=1, padding=(10, 5))
    style.map("Outline.TButton",
              background=[("active", COLORS["bg3"])],
              foreground=[("active", COLORS["text"])])

    style.configure("TEntry", fieldbackground=COLORS["input_bg"], foreground=COLORS["text"],
                    insertcolor=COLORS["text"], bordercolor=COLORS["border"],
                    lightcolor=COLORS["bg3"], darkcolor=COLORS["bg3"],
                    padding=(10, 6))

    style.configure("TCombobox", fieldbackground=COLORS["input_bg"], background=COLORS["bg3"],
                    foreground=COLORS["text"], arrowcolor=COLORS["text2"])

    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=COLORS["bg2"], foreground=COLORS["text2"],
                    padding=(16, 8), font=FONTS["body"])
    style.map("TNotebook.Tab",
              background=[("selected", COLORS["bg"]), ("active", COLORS["bg3"])],
              foreground=[("selected", COLORS["accent2"])])

    style.configure("Treeview", background=COLORS["bg2"], foreground=COLORS["text"],
                    fieldbackground=COLORS["bg2"], rowheight=40, borderwidth=0)
    style.configure("Treeview.Heading", background=COLORS["bg3"], foreground=COLORS["text2"],
                    font=FONTS["small"], relief="flat", padding=(8, 4))
    style.map("Treeview",
              background=[("selected", COLORS["accent_bg"])],
              foreground=[("selected", COLORS["accent_light"])])

    style.configure("TScrollbar", background=COLORS["bg3"], troughcolor=COLORS["bg"],
                    borderwidth=0, arrowsize=13, arrowcolor=COLORS["text2"])
    style.map("TScrollbar", background=[("active", COLORS["accent"])])

    style.configure("TCheckbutton", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Sidebar.TCheckbutton", background=COLORS["bg2"], foreground=COLORS["text"])

    style.configure("TSeparator", background=COLORS["border2"])

    style.configure("TScale", background=COLORS["bg"], troughcolor=COLORS["bg3"],
                    slidercolor=COLORS["accent"])

    style.configure("TProgressbar", background=COLORS["accent"], troughcolor=COLORS["bg3"],
                    borderwidth=0, thickness=8)

    style.configure("Horizontal.TProgressbar", background=COLORS["accent"],
                    troughcolor=COLORS["bg3"], borderwidth=0, thickness=8)

    return style