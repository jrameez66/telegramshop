# 🛍 Telegram Shop Bot v2 — Fully Automated + Admin Panel

Auto-delivery shop bot with wallet, quantity orders, direct pay, referrals, gift codes,
flash sales, reseller API, multi-currency display — sab kuch ek hi bot mein.

## ✨ Features (v2)

**User side**
- 🛍 Shop — pagination (10 per page) ya **All products list** view, stock counts
- 🔢 **Quantity selector** (− / ＋ / Custom Quantity), 🗒 **View Note** (Description + Note),
  🛡 Warranty & ⏳ HOLD fields, 🔗 Copy Link (share product)
- 💼 **Order Summary → 🪙 Wallet / 💳 Pay Direct / 💰 Top-up** — direct payment approve
  hote hi item **auto-deliver**
- 💰 Top-up Wallet — Binance Pay / BEP20 / Bybit / TON / LTC / Others (Order ID + admin
  approval) + **🤖 Crypto Bot (fully automatic)** optional; har method ka
  **"🧐 Where to find Order ID?"** tutorial (admin-settable)
- 📊 **Stats** — Orders, Items Bought, Total Spent, Last Order, Deposits +
  **24h / 7d / 30d / Custom** filters + **📨 Stats PDF to Email** (SMTP set ho to)
- 💱 **Currency picker** (17 currencies — display conversion, payments USDT mein),
  🌍 **Region picker** (country grid + Clear), 🌐 **8 languages**
- 🔔 **Notification categories** — Stock / Info / Wallet / Email alerts alag toggles
- 🔑 **Reseller API panel** — `stapi_...` key (masked), Regenerate, Disable/Enable,
  Docs — `GET /api/products`, `GET /api/balance`, `POST /api/order`
  (`{"product_id":123,"quantity":1,"request_id":"..."}` — idempotent, dobara charge nahi)
- ☰ **Menu commands** — /products, /deposit, /settings, /support, /api
- ⭐ Referrals (auto % commission), 🎁 Gift codes, 💼 My Orders, 🪙 My Deposits
  (pending_review/Credited statuses)

**Admin panel** (`/admin`)
- 📊 Dashboard — users, orders, revenue, today, pending, stock
- 📦 Products — add wizard, rename, price, **Description / Note / Warranty / Hold**,
  enable/disable, delete
- ➕ Add Stock (multi-line), 🔥 Flash Sale (auto broadcast sirf Stock-Alerts-ON users ko)
- 💰 Pending Deposits — ✅ Approve (topup = wallet credit + referral commission;
  **direct order = item auto-deliver**), ❌ Reject
- 👥 Users — add/remove balance, ban/unban, find user (orders + deposits ke sath)
- 🎁 Gift codes, 📣 Broadcast (text/photo), ⚙️ Settings (shop name, support, channel,
  referral %, min deposit, 6 payment addresses, **6 payment tutorials**,
  **💱 Currency Rates**, **📧 SMTP**)

## 🚀 Setup (5 minute)

1. **Bot banayen:** [@BotFather](https://t.me/BotFather) → `/newbot` → token copy
2. **Apni ID:** [@userinfobot](https://t.me/userinfobot) → `/start`
3. Install & run:

```bash
cd telegram_shop_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env          # BOT_TOKEN aur ADMIN_IDS bharein
python3 main.py
```

## 🤖 Auto Payments (Crypto Bot) — optional

1. [@CryptoBot](https://t.me/CryptoBot) → **Crypto Pay** → **Create App** → token
2. `.env` mein `CRYPTOBOT_TOKEN=` daal dein, restart
3. Users ka payment auto-detect → balance/order auto-process (60s checker)

## 🖥 VPS 24/7 (systemd)

```ini
# /etc/systemd/system/shopbot.service
[Unit]
Description=Telegram Shop Bot
After=network.target
[Service]
WorkingDirectory=/opt/telegram_shop_bot
ExecStart=/opt/telegram_shop_bot/venv/bin/python main.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now shopbot && sudo journalctl -u shopbot -f
```

## 📡 Reseller API

```bash
# Products (Bearer / x-api-key / ?api_key= teeno chalte hain)
curl -H "Authorization: Bearer stapi_xxx" http://SERVER_IP:8080/api/products
# Balance
curl -H "x-api-key: stapi_xxx" http://SERVER_IP:8080/api/balance
# Order (idempotent request_id)
curl -X POST -H "x-api-key: stapi_xxx" -H "Content-Type: application/json" \
     -d '{"product_id":1,"quantity":2,"request_id":"order-001"}' \
     http://SERVER_IP:8080/api/order
```

VPS firewall: `sudo ufw allow 8080` (Railway/Render par deploy karein to public URL
milega — `API_PORT` environment se set hota hai).

## ⚙️ Zaroori settings (`/admin` → ⚙️ Settings)

- `shop_name`, `support`, `channel_url`, `welcome`
- `pay_binance` (Pay ID + name), `pay_bep20`, `pay_bybit`, `pay_ton`, `pay_ltc`
- `tut_binance` … `tut_crypto` — "Where to find Order ID?" tutorials
- `ref_percent`, `min_deposit`
- 💱 **Currency Rates** — 1 USDT = X (masalan rate_PKR=278)
- 📧 **SMTP** — Stats PDF email ke liye (Gmail: smtp.gmail.com / 465 / App Password)

## 📌 Notes

- Database `shop.db` (SQLite) — backup = ye file copy
- v1 DB par migrate automatic hai (columns auto-add hote hain)
- `.env` / `shop.db` kabhi share na karein
- Telegram ToS ke mutabiq istemal karein
