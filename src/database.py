import sqlite3
import threading
import time
import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path.cwd() / ".mercari_monitor" / "monitor.db"


class Database:
    _local = threading.local()

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @property
    def conn(self):
        return self._get_conn()

    def _init_db(self):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    min_price INTEGER DEFAULT 0,
                    max_price INTEGER DEFAULT 0,
                    poll_interval REAL DEFAULT 0,
                    noshops INTEGER DEFAULT 0,
                    allowed_conditions TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(keyword, platform)
                );

                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    name TEXT,
                    price INTEGER,
                    currency TEXT DEFAULT 'JPY',
                    url TEXT,
                    image_url TEXT,
                    seller TEXT,
                    status TEXT DEFAULT 'new',
                    condition TEXT DEFAULT '',
                    is_shop INTEGER DEFAULT 0,
                    is_auction INTEGER DEFAULT 0,
                    found_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(item_id, platform)
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT,
                    platform TEXT,
                    message TEXT,
                    read INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_items_platform ON items(platform);
                CREATE INDEX IF NOT EXISTS idx_items_found_at ON items(found_at);
                CREATE INDEX IF NOT EXISTS idx_items_keyword ON items(keyword);

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watched_sellers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    alias TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(seller_id, platform)
                );

                CREATE TABLE IF NOT EXISTS watched_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    name TEXT,
                    url TEXT,
                    last_comment_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(item_id, platform)
                );

                CREATE TABLE IF NOT EXISTS blocked_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    reason TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(item_id, platform)
                );

                CREATE INDEX IF NOT EXISTS idx_blocked_items_platform ON blocked_items(platform);

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    item_name TEXT,
                    item_url TEXT,
                    image_url TEXT,
                    price INTEGER DEFAULT 0,
                    currency TEXT DEFAULT 'JPY',
                    cny_price REAL DEFAULT 0,
                    service_fee REAL DEFAULT 0,
                    domestic_shipping INTEGER DEFAULT 0,
                    intl_shipping INTEGER DEFAULT 0,
                    total_cny REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    order_type TEXT DEFAULT 'buy',
                    note TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(item_id, platform)
                );

                CREATE TABLE IF NOT EXISTS platform_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    account_name TEXT DEFAULT '',
                    cookie TEXT DEFAULT '',
                    token TEXT DEFAULT '',
                    extra TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(platform, account_name)
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    expires_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
            """)
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn):
        """增量迁移：为旧表补充新字段"""
        cols_kw = {r[1] for r in conn.execute("PRAGMA table_info(keywords)").fetchall()}
        if "poll_interval" not in cols_kw:
            conn.execute("ALTER TABLE keywords ADD COLUMN poll_interval REAL DEFAULT 0")
        if "noshops" not in cols_kw:
            conn.execute("ALTER TABLE keywords ADD COLUMN noshops INTEGER DEFAULT 0")
        if "allowed_conditions" not in cols_kw:
            conn.execute("ALTER TABLE keywords ADD COLUMN allowed_conditions TEXT DEFAULT ''")
        if "price_drop" not in cols_kw:
            conn.execute("ALTER TABLE keywords ADD COLUMN price_drop INTEGER DEFAULT 1")
        if "category_id" not in cols_kw:
            conn.execute("ALTER TABLE keywords ADD COLUMN category_id TEXT DEFAULT ''")

        cols_it = {r[1] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
        if "condition" not in cols_it:
            conn.execute("ALTER TABLE items ADD COLUMN condition TEXT DEFAULT ''")
        if "is_shop" not in cols_it:
            conn.execute("ALTER TABLE items ADD COLUMN is_shop INTEGER DEFAULT 0")
        if "is_auction" not in cols_it:
            conn.execute("ALTER TABLE items ADD COLUMN is_auction INTEGER DEFAULT 0")
        if "auction_end_time" not in cols_it:
            conn.execute("ALTER TABLE items ADD COLUMN auction_end_time TEXT DEFAULT ''")

        cols_wi = {r[1] for r in conn.execute("PRAGMA table_info(watched_items)").fetchall()}
        if "last_price" not in cols_wi:
            conn.execute("ALTER TABLE watched_items ADD COLUMN last_price INTEGER DEFAULT 0")

    def add_keyword(self, keyword: str, platform: str,
                    min_price: int = 0, max_price: int = 0,
                    poll_interval: float = 0, noshops: bool = False,
                    allowed_conditions: str = "", price_drop: bool = True,
                    category_id: str = "") -> bool:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO keywords "
                "(keyword, platform, min_price, max_price, poll_interval, noshops, allowed_conditions, price_drop, category_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (keyword.strip(), platform, min_price, max_price,
                 poll_interval, 1 if noshops else 0, allowed_conditions,
                 1 if price_drop else 0, str(category_id or "").strip())
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def delete_keyword(self, keyword: str) -> bool:
        try:
            cursor = self.conn.execute("DELETE FROM keywords WHERE keyword=?", (keyword,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception:
            return False

    def update_keyword(self, keyword_id: int, **fields) -> bool:
        if not fields:
            return False
        allowed = {"min_price", "max_price", "poll_interval", "noshops", "allowed_conditions", "enabled", "price_drop"}
        sets = []
        vals = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "noshops":
                v = 1 if v else 0
            sets.append(f"{k}=?")
            vals.append(v)
        if not sets:
            return False
        vals.append(keyword_id)
        try:
            self.conn.execute(
                f"UPDATE keywords SET {', '.join(sets)} WHERE id=?", vals
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def remove_keyword(self, keyword_id: int):
        self.conn.execute("DELETE FROM keywords WHERE id=?", (keyword_id,))
        self.conn.commit()

    def toggle_keyword(self, keyword_id: int, enabled: bool):
        self.conn.execute(
            "UPDATE keywords SET enabled=? WHERE id=?", (1 if enabled else 0, keyword_id)
        )
        self.conn.commit()

    def get_keywords(self, platform: Optional[str] = None) -> list:
        if platform:
            rows = self.conn.execute(
                "SELECT * FROM keywords WHERE platform=? AND enabled=1", (platform,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM keywords ORDER BY platform, keyword").fetchall()
        return [dict(r) for r in rows]

    def is_item_new(self, item_id: str, platform: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM items WHERE item_id=? AND platform=?", (item_id, platform)
        ).fetchone()
        return row is None

    def save_item(self, item: dict) -> int:
        try:
            if self.is_item_new(item["item_id"], item["platform"]):
                self.conn.execute("""
                    INSERT INTO items
                    (item_id, platform, keyword, name, price, currency, url, image_url, seller,
                     condition, is_shop, is_auction, auction_end_time)
                    VALUES (:item_id, :platform, :keyword, :name, :price, :currency, :url, :image_url, :seller,
                     :condition, :is_shop, :is_auction, :auction_end_time)
                """, {
                    "item_id": item["item_id"],
                    "platform": item["platform"],
                    "keyword": item["keyword"],
                    "name": item.get("name", ""),
                    "price": item.get("price", 0),
                    "currency": item.get("currency", "JPY"),
                    "url": item.get("url", ""),
                    "image_url": item.get("image_url", ""),
                    "seller": item.get("seller", ""),
                    "condition": item.get("condition", ""),
                    "is_shop": 1 if item.get("is_shop", False) else 0,
                    "is_auction": 1 if item.get("is_auction", False) else 0,
                    "auction_end_time": item.get("auction_end_time", ""),
                })
                self.conn.commit()
                return 1
            else:
                existing = self.conn.execute(
                    "SELECT price FROM items WHERE item_id=? AND platform=?",
                    (item["item_id"], item["platform"])
                ).fetchone()
                new_price = item.get("price", 0)
                if existing and existing["price"] != new_price:
                    self.conn.execute(
                        "UPDATE items SET price=?, auction_end_time=? WHERE item_id=? AND platform=?",
                        (new_price, item.get("auction_end_time", ""),
                         item["item_id"], item["platform"])
                    )
                    self.conn.commit()
                    if existing["price"] > new_price and new_price > 0:
                        item["old_price"] = existing["price"]
                        return 2
                return 0
        except Exception:
            return 0

    def get_items(self, platform: Optional[str] = None,
                  keyword: Optional[str] = None, limit: int = 200,
                  offset: int = 0) -> list:
        query = "SELECT * FROM items WHERE 1=1"
        params = []
        if platform:
            query += " AND platform=?"
            params.append(platform)
        if keyword:
            query += " AND (keyword LIKE ? OR name LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        query += " ORDER BY found_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_items_count(self, platform: Optional[str] = None,
                        keyword: Optional[str] = None) -> int:
        query = "SELECT COUNT(*) FROM items WHERE 1=1"
        params = []
        if platform:
            query += " AND platform=?"
            params.append(platform)
        if keyword:
            query += " AND (keyword LIKE ? OR name LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        return self.conn.execute(query, params).fetchone()[0]

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        offset_h = int((datetime.now() - datetime.utcnow()).total_seconds() // 3600)
        offset_str = f"+{offset_h} hours" if offset_h >= 0 else f"{offset_h} hours"
        today = self.conn.execute(
            f"SELECT COUNT(*) FROM items WHERE date(found_at, '{offset_str}')=date('now', '{offset_str}')"
        ).fetchone()[0]
        by_platform = self.conn.execute(
            "SELECT platform, COUNT(*) as cnt FROM items GROUP BY platform"
        ).fetchall()
        return {
            "total": total,
            "today": today,
            "by_platform": {r["platform"]: r["cnt"] for r in by_platform}
        }

    def get_today_by_platform(self) -> dict:
        offset_h = int((datetime.now() - datetime.utcnow()).total_seconds() // 3600)
        offset_str = f"+{offset_h} hours" if offset_h >= 0 else f"{offset_h} hours"
        rows = self.conn.execute(
            f"SELECT platform, COUNT(*) as cnt FROM items WHERE date(found_at, '{offset_str}')=date('now', '{offset_str}') GROUP BY platform"
        ).fetchall()
        return {r["platform"]: r["cnt"] for r in rows}

    def save_notification(self, item_id: str, platform: str, message: str):
        self.conn.execute(
            "INSERT INTO notifications (item_id, platform, message) VALUES (?,?,?)",
            (item_id, platform, message)
        )
        self.conn.commit()

    def get_unread_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE read=0"
        ).fetchone()[0]

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, value)
        )
        self.conn.commit()

    def get_pending_auctions(self, platform: str, threshold_seconds: float) -> list:
        now = datetime.now(timezone.utc)
        rows = self.conn.execute(
            "SELECT * FROM items WHERE platform=? AND is_auction=1 AND auction_end_time!='' "
            "ORDER BY found_at DESC LIMIT 500",
            (platform,)
        ).fetchall()
        result = []
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["auction_end_time"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                remaining = (dt - now).total_seconds()
                if 0 < remaining <= threshold_seconds:
                    result.append(dict(r))
            except Exception:
                continue
        return result

    def add_watched_seller(self, seller_id: str, platform: str, alias: str = "") -> bool:
        try:
            existing = self.conn.execute(
                "SELECT 1 FROM watched_sellers WHERE seller_id=? AND platform=?",
                (seller_id, platform)
            ).fetchone()
            if existing:
                return False
            self.conn.execute(
                "INSERT INTO watched_sellers (seller_id, platform, alias) VALUES (?,?,?)",
                (seller_id, platform, alias)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def remove_watched_seller(self, seller_id: str, platform: str):
        self.conn.execute(
            "DELETE FROM watched_sellers WHERE seller_id=? AND platform=?",
            (seller_id, platform)
        )
        self.conn.commit()

    def get_watched_sellers(self, platform: Optional[str] = None) -> list:
        if platform:
            rows = self.conn.execute(
                "SELECT * FROM watched_sellers WHERE platform=?", (platform,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM watched_sellers").fetchall()
        return [dict(r) for r in rows]

    def add_watched_item(self, item_id: str, platform: str, name: str = "", url: str = "") -> bool:
        try:
            existing = self.conn.execute(
                "SELECT 1 FROM watched_items WHERE item_id=? AND platform=?",
                (item_id, platform)
            ).fetchone()
            if existing:
                return False

            self.conn.execute(
                "INSERT INTO watched_items (item_id, platform, name, url) VALUES (?,?,?,?)",
                (item_id, platform, name, url)
            )
            self.conn.commit()
            return True

        except Exception as e:
            print(f"[DB ERROR] add_watched_item failed: {e}")
            import traceback
            traceback.print_exc()

            if "no such table" in str(e).lower():
                print("[DB ERROR] watched_items table does not exist, attempting to create...")
                try:
                    self._create_tables()
                    return self.add_watched_item(item_id, platform, name, url)
                except Exception as retry_e:
                    print(f"[DB ERROR] Table creation failed: {retry_e}")

            raise e

    def remove_watched_item(self, item_id: str, platform: str):
        self.conn.execute(
            "DELETE FROM watched_items WHERE item_id=? AND platform=?",
            (item_id, platform)
        )
        self.conn.commit()

    def get_watched_items(self) -> list:
        rows = self.conn.execute("SELECT id, item_id, platform, name, url, last_comment_count, created_at FROM watched_items ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def add_blocked_item(self, item_id: str, platform: str, reason: str = "") -> bool:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO blocked_items (item_id, platform, reason) VALUES (?, ?, ?)",
                (item_id, platform, reason)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def remove_blocked_item(self, item_id: str, platform: str):
        self.conn.execute("DELETE FROM blocked_items WHERE item_id=? AND platform=?", (item_id, platform))
        self.conn.commit()

    def is_blocked(self, item_id: str, platform: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM blocked_items WHERE item_id=? AND platform=?", (item_id, platform)).fetchone()
        return row is not None

    def get_blocked_items(self) -> list:
        rows = self.conn.execute("SELECT * FROM blocked_items ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def update_watched_item_comments(self, item_id: str, platform: str, count: int):
        self.conn.execute(
            "UPDATE watched_items SET last_comment_count=? WHERE item_id=? AND platform=?",
            (count, item_id, platform)
        )
        self.conn.commit()

    def update_watched_item_price(self, item_id: str, platform: str, price: int):
        self.conn.execute(
            "UPDATE watched_items SET last_price=? WHERE item_id=? AND platform=?",
            (price, item_id, platform)
        )
        self.conn.commit()

    def create_user(self, username: str, password: str, is_admin: bool = False) -> bool:
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            self.conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)",
                (username, pw_hash, 1 if is_admin else 0)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def verify_user(self, username: str, password: str) -> Optional[dict]:
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        row = self.conn.execute(
            "SELECT * FROM users WHERE username=? AND password_hash=?",
            (username, pw_hash)
        ).fetchone()
        return dict(row) if row else None

    def create_token(self, user_id: int) -> str:
        token = secrets.token_hex(32)
        self.conn.execute(
            "INSERT OR REPLACE INTO auth_tokens (token, user_id) VALUES (?,?)",
            (token, user_id)
        )
        self.conn.commit()
        return token

    def verify_token(self, token: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT u.* FROM auth_tokens t JOIN users u ON t.user_id=u.id WHERE t.token=?",
            (token,)
        ).fetchone()
        return dict(row) if row else None

    def has_users(self) -> bool:
        row = self.conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] > 0

    def create_order(self, item_id: str, platform: str, item_name: str = "",
                     item_url: str = "", image_url: str = "", price: int = 0,
                     currency: str = "JPY", cny_price: float = 0,
                     order_type: str = "buy", note: str = "") -> int | None:
        service_fee = round(cny_price * 0.08, 2)
        domestic_shipping = 60
        intl_shipping = 0
        total_cny = round(cny_price + service_fee + domestic_shipping + intl_shipping, 2)
        try:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO orders "
                "(item_id, platform, item_name, item_url, image_url, price, currency, "
                "cny_price, service_fee, domestic_shipping, intl_shipping, total_cny, "
                "order_type, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item_id, platform, item_name, item_url, image_url, price, currency,
                 cny_price, service_fee, domestic_shipping, intl_shipping, total_cny,
                 order_type, note)
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception:
            return None

    def get_orders(self, status: str = None, limit: int = 50, offset: int = 0) -> list:
        query = "SELECT * FROM orders WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(r) for r in self.conn.execute(query, params).fetchall()]

    def get_orders_count(self, status: str = None) -> int:
        query = "SELECT COUNT(*) FROM orders WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        return self.conn.execute(query, params).fetchone()[0]

    def update_order_status(self, order_id: int, status: str, note: str = "") -> bool:
        try:
            if note:
                self.conn.execute(
                    "UPDATE orders SET status=?, note=?, updated_at=datetime('now') WHERE id=?",
                    (status, note, order_id)
                )
            else:
                self.conn.execute(
                    "UPDATE orders SET status=?, updated_at=datetime('now') WHERE id=?",
                    (status, order_id)
                )
            self.conn.commit()
            return True
        except Exception:
            return False

    def delete_order(self, order_id: int):
        self.conn.execute("DELETE FROM orders WHERE id=?", (order_id,))
        self.conn.commit()

    def get_order_by_item(self, item_id: str, platform: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM orders WHERE item_id=? AND platform=?",
            (item_id, platform)
        ).fetchone()
        return dict(row) if row else None

    def add_platform_account(self, platform: str, account_name: str,
                              cookie: str = "", token: str = "", extra: str = "") -> bool:
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO platform_accounts "
                "(platform, account_name, cookie, token, extra) VALUES (?,?,?,?,?)",
                (platform, account_name, cookie, token, extra)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def get_platform_accounts(self, platform: str = None) -> list:
        if platform:
            rows = self.conn.execute(
                "SELECT id, platform, account_name, enabled, created_at FROM platform_accounts WHERE platform=?",
                (platform,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, platform, account_name, enabled, created_at FROM platform_accounts ORDER BY platform"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_platform_account_full(self, account_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM platform_accounts WHERE id=?", (account_id,)
        ).fetchone()
        return dict(row) if row else None

    def remove_platform_account(self, account_id: int):
        self.conn.execute("DELETE FROM platform_accounts WHERE id=?", (account_id,))
        self.conn.commit()

    def get_item_detail(self, item_id: str, platform: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM items WHERE item_id=? AND platform=?",
            (item_id, platform)
        ).fetchone()
        return dict(row) if row else None