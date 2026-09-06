"""SQLite database layer — v2 (quantity orders, direct-pay, currencies, API v2)."""
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  user_id INTEGER PRIMARY KEY,
  username TEXT DEFAULT '',
  first_name TEXT DEFAULT '',
  balance REAL DEFAULT 0,
  referrer_id INTEGER,
  joined_at TEXT,
  lang TEXT DEFAULT 'EN',
  region TEXT DEFAULT '',
  email TEXT DEFAULT '',
  api_key TEXT,
  banned INTEGER DEFAULT 0,
  notif INTEGER DEFAULT 1,
  ref_earnings REAL DEFAULT 0,
  shop_view TEXT DEFAULT 'list',
  grouping TEXT DEFAULT 'off'
);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  price REAL,
  sale_price REAL,
  sale_end TEXT,
  emoji TEXT DEFAULT '📦',
  active INTEGER DEFAULT 1,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS stock(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER,
  content TEXT,
  sold INTEGER DEFAULT 0,
  sold_to INTEGER,
  sold_at TEXT
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  product_id INTEGER,
  product_name TEXT,
  price_paid REAL,
  content TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS deposits(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  amount REAL,
  method TEXT,
  tx_info TEXT DEFAULT '',
  status TEXT DEFAULT 'pending',
  invoice_id TEXT DEFAULT '',
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS giftcodes(
  code TEXT PRIMARY KEY,
  amount REAL,
  max_uses INTEGER DEFAULT 1,
  used_count INTEGER DEFAULT 0,
  active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS gift_uses(code TEXT, user_id INTEGER, PRIMARY KEY(code, user_id));
CREATE TABLE IF NOT EXISTS referrals(referrer_id INTEGER, referred_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS api_requests(
  user_id INTEGER, request_id TEXT, response TEXT, created_at TEXT,
  PRIMARY KEY(user_id, request_id)
);
"""

# Fresh install ke baad bhi chalte hain — duplicate column error ignore hoti hai
MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN currency TEXT DEFAULT 'USDT'",
    "ALTER TABLE users ADD COLUMN n_stock INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN n_info INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN n_wallet INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN n_email INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN api_disabled INTEGER DEFAULT 0",
    "ALTER TABLE products ADD COLUMN description TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN note TEXT DEFAULT ''",
    "ALTER TABLE products ADD COLUMN warranty TEXT DEFAULT 'NON'",
    "ALTER TABLE products ADD COLUMN hold TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN qty INTEGER DEFAULT 1",
    "ALTER TABLE orders ADD COLUMN source TEXT DEFAULT 'bot'",
    "ALTER TABLE deposits ADD COLUMN kind TEXT DEFAULT 'topup'",
    "ALTER TABLE deposits ADD COLUMN meta TEXT DEFAULT ''",
]

DEFAULTS = {
    "shop_name": "My Shop",
    "welcome": "",
    "support": "@your_support_username",
    "channel_url": "https://t.me/your_channel",
    "ref_percent": "5",
    "min_deposit": "1",
    "pay_binance": "Pay ID: not set — Admin Panel > Settings",
    "pay_bep20": "Not set — Admin Panel > Settings se set karein",
    "pay_bybit": "Not set — Admin Panel > Settings se set karein",
    "pay_ton": "Not set — Admin Panel > Settings se set karein",
    "pay_ltc": "Not set — Admin Panel > Settings se set karein",
    "pay_others": "Contact support",
    # payment method tutorials ("Where to find Order ID?")
    "tut_binance": "", "tut_bep20": "", "tut_bybit": "", "tut_ton": "",
    "tut_ltc": "", "tut_crypto": "", "tut_others": "",
    # currency rates vs USDT (display only)
    "rate_USD": "1", "rate_PKR": "278", "rate_INR": "84", "rate_BDT": "120",
    "rate_AED": "3.67", "rate_SAR": "3.75", "rate_TRY": "41", "rate_RUB": "92",
    "rate_IDR": "16200", "rate_BRL": "5.6", "rate_EGP": "49", "rate_NGN": "1600",
    "rate_UZS": "12800", "rate_UAH": "41", "rate_VND": "25400", "rate_EUR": "0.92",
    # optional SMTP for "Stats PDF to Email"
    "smtp_host": "", "smtp_port": "465", "smtp_user": "", "smtp_pass": "",
    "smtp_from": "",
}

USER_FIELDS = {"lang", "region", "email", "banned", "notif", "shop_view", "grouping",
               "currency", "n_stock", "n_info", "n_wallet", "n_email", "api_disabled",
               "api_key"}
PRODUCT_FIELDS = {"name", "price", "emoji", "active", "sale_price", "sale_end",
                  "description", "note", "warranty", "hold"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def price_of(p):
    """(effective_price, on_sale) — flash sale active ho to sale price."""
    if p["sale_price"] is not None and p["sale_end"]:
        try:
            if datetime.fromisoformat(p["sale_end"]) > datetime.now(timezone.utc):
                return float(p["sale_price"]), True
        except Exception:
            pass
    return float(p["price"]), False


def time_ago(iso):
    """'2m ago', '5h ago', '1d ago' style relative time."""
    try:
        dt = datetime.fromisoformat(iso)
        diff = datetime.now(timezone.utc) - dt
        s = int(diff.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return ""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            for sql in MIGRATIONS:
                try:
                    self.conn.execute(sql)
                except sqlite3.OperationalError:
                    pass
            for k, v in DEFAULTS.items():
                self.conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                                  (k, v))
            self.conn.commit()

    # ---------- settings ----------
    def get_setting(self, key, default=""):
        with self.lock:
            r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return r["value"] if r else default

    def set_setting(self, key, value):
        with self.lock:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
            self.conn.commit()

    def rate(self, code):
        try:
            return float(self.get_setting(f"rate_{code}", "0") or 0)
        except ValueError:
            return 0

    # ---------- users ----------
    def ensure_user(self, tg):
        with self.lock:
            row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (tg.id,)).fetchone()
            if not row:
                self.conn.execute(
                    "INSERT INTO users(user_id, username, first_name, joined_at, api_key) "
                    "VALUES(?,?,?,?,?)",
                    (tg.id, tg.username or "", tg.first_name or "", now(),
                     "stapi_" + secrets.token_hex(16)))
                self.conn.commit()
                return self.get_user(tg.id), True
            self.conn.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                              (tg.username or "", tg.first_name or "", tg.id))
            self.conn.commit()
            u = self.get_user(tg.id)
            if not u.get("api_key"):
                self.set_user_field(tg.id, "api_key", "stapi_" + secrets.token_hex(16))
                u = self.get_user(tg.id)
            return u, False

    def get_user(self, uid):
        with self.lock:
            r = self.conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            return dict(r) if r else None

    def get_user_by_username(self, uname):
        uname = uname.lstrip("@").lower()
        with self.lock:
            r = self.conn.execute("SELECT * FROM users WHERE LOWER(username)=?",
                                  (uname,)).fetchone()
            return dict(r) if r else None

    def get_user_by_apikey(self, key):
        with self.lock:
            r = self.conn.execute("SELECT * FROM users WHERE api_key=? AND api_disabled=0",
                                  (key,)).fetchone()
            return dict(r) if r else None

    def set_user_field(self, uid, field, value):
        if field not in USER_FIELDS:
            raise ValueError("bad field")
        with self.lock:
            self.conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, uid))
            self.conn.commit()

    def regen_api_key(self, uid):
        key = "stapi_" + secrets.token_hex(16)
        self.set_user_field(uid, "api_key", key)
        return key

    def add_balance(self, uid, amount):
        with self.lock:
            self.conn.execute(
                "UPDATE users SET balance = ROUND(balance + ?, 6) WHERE user_id=?",
                (amount, uid))
            self.conn.commit()

    def add_ref_earnings(self, uid, amount):
        with self.lock:
            self.conn.execute(
                "UPDATE users SET ref_earnings = ref_earnings + ? WHERE user_id=?",
                (amount, uid))
            self.conn.commit()

    def count_users(self):
        with self.lock:
            return self.conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]

    def all_user_ids(self, include_banned=False, notif_field=None):
        q = "SELECT user_id FROM users"
        conds = []
        if not include_banned:
            conds.append("banned=0")
        if notif_field in ("n_stock", "n_info", "n_wallet", "n_email"):
            conds.append(f"{notif_field}=1")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        with self.lock:
            return [r["user_id"] for r in self.conn.execute(q).fetchall()]

    # ---------- referrals ----------
    def add_referral(self, referrer, referred):
        with self.lock:
            try:
                self.conn.execute(
                    "INSERT INTO referrals(referrer_id, referred_id) VALUES(?,?)",
                    (referrer, referred))
                self.conn.execute("UPDATE users SET referrer_id=? WHERE user_id=?",
                                  (referrer, referred))
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def referral_count(self, uid):
        with self.lock:
            return self.conn.execute(
                "SELECT COUNT(*) c FROM referrals WHERE referrer_id=?",
                (uid,)).fetchone()["c"]

    # ---------- products / stock ----------
    def add_product(self, name, price, emoji="📦"):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO products(name, price, emoji, created_at) VALUES(?,?,?,?)",
                (name, price, emoji, now()))
            self.conn.commit()
            return cur.lastrowid

    def update_product(self, pid, **kw):
        sets = {k: v for k, v in kw.items() if k in PRODUCT_FIELDS}
        if not sets:
            return
        sql = ", ".join(f"{k}=?" for k in sets)
        with self.lock:
            self.conn.execute(f"UPDATE products SET {sql} WHERE id=?", (*sets.values(), pid))
            self.conn.commit()

    def delete_product(self, pid):
        with self.lock:
            self.conn.execute("DELETE FROM stock WHERE product_id=?", (pid,))
            self.conn.execute("DELETE FROM products WHERE id=?", (pid,))
            self.conn.commit()

    def get_product(self, pid):
        with self.lock:
            r = self.conn.execute(
                "SELECT p.*, (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id "
                "AND s.sold=0) AS stock_count FROM products p WHERE p.id=?",
                (pid,)).fetchone()
            return dict(r) if r else None

    def list_products(self, offset=0, limit=10, active_only=True):
        q = ("SELECT p.*, (SELECT COUNT(*) FROM stock s WHERE s.product_id=p.id AND s.sold=0) "
             "AS stock_count FROM products p")
        if active_only:
            q += " WHERE p.active=1"
        q += " ORDER BY p.id LIMIT ? OFFSET ?"
        with self.lock:
            return [dict(r) for r in self.conn.execute(q, (limit, offset)).fetchall()]

    def count_products(self, active_only=True):
        q = "SELECT COUNT(*) c FROM products" + (" WHERE active=1" if active_only else "")
        with self.lock:
            return self.conn.execute(q).fetchone()["c"]

    def add_stock(self, pid, items):
        with self.lock:
            self.conn.executemany("INSERT INTO stock(product_id, content) VALUES(?,?)",
                                  [(pid, i) for i in items])
            self.conn.commit()
            return len(items)

    # ---------- purchase (atomic, quantity support) ----------
    def purchase_multi(self, uid, pid, qty=1, source="bot", skip_balance=False):
        """qty items ek sath khareedna. skip_balance=True → direct-pay approved order."""
        qty = max(1, int(qty))
        with self.lock:
            u = self.get_user(uid)
            p = self.get_product(pid)
            if not u:
                return {"ok": False, "err": "nouser"}
            if not p or not p["active"]:
                return {"ok": False, "err": "unavailable"}
            price, on_sale = price_of(p)
            total = round(price * qty, 6)
            if not skip_balance and float(u["balance"]) < total:
                return {"ok": False, "err": "balance", "price": price,
                        "need": round(total - float(u["balance"]), 6), "total": total}
            items = self.conn.execute(
                "SELECT * FROM stock WHERE product_id=? AND sold=0 ORDER BY id LIMIT ?",
                (pid, qty)).fetchall()
            if len(items) < qty:
                return {"ok": False, "err": "stock", "available": len(items),
                        "price": price}
            if not skip_balance:
                self.conn.execute(
                    "UPDATE users SET balance = ROUND(balance - ?, 6) WHERE user_id=?",
                    (total, uid))
            ts = now()
            for it in items:
                self.conn.execute(
                    "UPDATE stock SET sold=1, sold_to=?, sold_at=? WHERE id=?",
                    (uid, ts, it["id"]))
            content = "\n".join(it["content"] for it in items)
            cur = self.conn.execute(
                "INSERT INTO orders(user_id, product_id, product_name, price_paid, content, "
                "created_at, qty, source) VALUES(?,?,?,?,?,?,?,?)",
                (uid, pid, p["name"], total, content, ts, qty, source))
            self.conn.commit()
            left = self.get_product(pid)["stock_count"]
            return {"ok": True, "price": price, "total": total, "on_sale": on_sale,
                    "items": [it["content"] for it in items], "order_id": cur.lastrowid,
                    "product": p["name"], "stock_left": left, "qty": qty}

    def user_orders(self, uid, limit=10):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (uid, limit)).fetchall()]

    def order_stats(self, uid):
        with self.lock:
            r = self.conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(price_paid),0) s, COALESCE(SUM(qty),0) q "
                "FROM orders WHERE user_id=?", (uid,)).fetchone()
            return {"orders": r["c"], "spent": r["s"], "items": r["q"]}

    def stats_period(self, uid, seconds):
        since = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(
            timespec="seconds")
        with self.lock:
            o = self.conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(price_paid),0) s, COALESCE(SUM(qty),0) q "
                "FROM orders WHERE user_id=? AND created_at>=?", (uid, since)).fetchone()
            d = self.conn.execute(
                "SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE user_id=? "
                "AND status='paid' AND created_at>=?", (uid, since)).fetchone()
            return {"orders": o["c"], "spent": o["s"], "items": o["q"],
                    "deposits": d["s"]}

    def deposit_total(self, uid):
        with self.lock:
            return self.conn.execute(
                "SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE user_id=? "
                "AND status='paid'", (uid,)).fetchone()["s"]

    def last_order(self, uid):
        with self.lock:
            r = self.conn.execute(
                "SELECT created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (uid,)).fetchone()
            return r["created_at"] if r else None

    def api_stats(self, uid):
        with self.lock:
            r = self.conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(price_paid),0) s FROM orders "
                "WHERE user_id=? AND source='api'", (uid,)).fetchone()
            return {"orders": r["c"], "spent": r["s"]}

    # ---------- API idempotency ----------
    def get_api_request(self, uid, rid):
        with self.lock:
            r = self.conn.execute(
                "SELECT response FROM api_requests WHERE user_id=? AND request_id=?",
                (uid, rid)).fetchone()
            return r["response"] if r else None

    def save_api_request(self, uid, rid, response):
        with self.lock:
            try:
                self.conn.execute(
                    "INSERT INTO api_requests(user_id, request_id, response, created_at) "
                    "VALUES(?,?,?,?)", (uid, rid, response, now()))
                self.conn.commit()
            except sqlite3.IntegrityError:
                pass

    # ---------- deposits ----------
    def create_deposit(self, uid, amount, method, tx_info="", invoice_id="",
                       kind="topup", meta=""):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO deposits(user_id, amount, method, tx_info, invoice_id, "
                "created_at, kind, meta) VALUES(?,?,?,?,?,?,?,?)",
                (uid, amount, method, tx_info, invoice_id, now(), kind, meta))
            self.conn.commit()
            return cur.lastrowid

    def get_deposit(self, did):
        with self.lock:
            r = self.conn.execute("SELECT * FROM deposits WHERE id=?", (did,)).fetchone()
            return dict(r) if r else None

    def set_deposit_status(self, did, status):
        with self.lock:
            self.conn.execute("UPDATE deposits SET status=? WHERE id=?", (status, did))
            self.conn.commit()

    def pending_deposits(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT d.*, u.username, u.first_name FROM deposits d "
                "LEFT JOIN users u ON u.user_id=d.user_id "
                "WHERE d.status='pending' ORDER BY d.id").fetchall()]

    def pending_crypto(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM deposits WHERE status='pending' AND invoice_id != ''"
            ).fetchall()]

    def user_deposits(self, uid, limit=10):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (uid, limit)).fetchall()]

    # ---------- gift codes ----------
    def create_gift(self, amount, max_uses):
        code = "GIFT-" + secrets.token_hex(4).upper()
        with self.lock:
            self.conn.execute(
                "INSERT INTO giftcodes(code, amount, max_uses) VALUES(?,?,?)",
                (code, amount, max_uses))
            self.conn.commit()
        return code

    def redeem_gift(self, code, uid):
        code = code.strip().upper()
        with self.lock:
            g = self.conn.execute("SELECT * FROM giftcodes WHERE code=?", (code,)).fetchone()
            if not g or not g["active"]:
                return False, "❌ Invalid ya expired gift code."
            if g["used_count"] >= g["max_uses"]:
                return False, "❌ Ye gift code fully redeem ho chuka hai."
            used = self.conn.execute(
                "SELECT 1 FROM gift_uses WHERE code=? AND user_id=?", (code, uid)).fetchone()
            if used:
                return False, "❌ Aap ye code pehle hi use kar chuke hain."
            self.conn.execute("INSERT INTO gift_uses(code, user_id) VALUES(?,?)", (code, uid))
            self.conn.execute(
                "UPDATE giftcodes SET used_count = used_count + 1 WHERE code=?", (code,))
            self.conn.execute(
                "UPDATE users SET balance = ROUND(balance + ?, 6) WHERE user_id=?",
                (g["amount"], uid))
            self.conn.commit()
            return True, g["amount"]

    def list_gifts(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT * FROM giftcodes ORDER BY rowid DESC LIMIT 20").fetchall()]

    # ---------- admin stats ----------
    def stats(self):
        today = datetime.now(timezone.utc).date().isoformat()
        with self.lock:
            users = self.conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
            o = self.conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(price_paid),0) s FROM orders").fetchone()
            t = self.conn.execute(
                "SELECT COALESCE(SUM(price_paid),0) s FROM orders "
                "WHERE substr(created_at,1,10)=?", (today,)).fetchone()
            dep = self.conn.execute(
                "SELECT COUNT(*) c FROM deposits WHERE status='pending'").fetchone()["c"]
            stock = self.conn.execute(
                "SELECT COUNT(*) c FROM stock WHERE sold=0").fetchone()["c"]
            return {"users": users, "orders": o["c"], "revenue": o["s"],
                    "today": t["s"], "pending": dep, "stock": stock}

    def set_sale(self, pid, sale_price, hours):
        end = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(
            timespec="seconds")
        self.update_product(pid, sale_price=sale_price, sale_end=end)
