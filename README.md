# 🛍 Telegram Shop Bot — Fully Automated + Admin Panel

Screenshots wale bot jaisa complete auto-delivery shop bot: products, stock, wallet,
deposits, referrals, gift codes, flash sales, reseller API — sab kuch **ek hi bot** mein.

## ✨ Features

**User side**
- 🛍 Shop — pagination (1/4, Next/Refresh), stock counts, out-of-stock products greyed
- ⚡ **Auto-delivery** — Buy Now dabate hi item turant chat mein deliver
- 💰 Top-up Wallet — Binance Pay, USDT BEP20, Bybit Pay, USDT TON, LTC, Others (manual approval) + **🤖 Crypto Bot (automatic, instant)** optional
- 👤 Profile — ID, username, balance, email, region, language, joined date
- 💼 My Orders, 🪙 My Deposits, 📊 Stats, 💲 Price List
- ⭐ **Referral system** — apna link, har deposit par % commission (auto-credit)
- 🎁 Gift codes, 🔔 Notifications toggle, 🗂 Shop Grouping, 🛍 Shop View
- 🔑 **Reseller API key** — `/api/products`, `/api/buy` se apni site/bot connect karein

**Admin panel** (`/admin`)
- 📊 Dashboard — users, orders, revenue, today, pending deposits, stock
- 📦 Products — add (3-step wizard: naam → price → stock), rename, edit price, enable/disable, delete
- ➕ Add Stock — multi-line paste (har line = 1 account/link/code)
- 🔥 **Flash Sale** — `sale_price hours` bhejein (e.g. `0.80 24`), sab users ko sale notification chali jayegi
- 💰 Pending Deposits — ✅ Approve / ❌ Reject (user ko auto message, referral commission auto)
- 👥 Users — add/remove balance, ban/unban, find user
- 🎁 Gift Codes — `amount max_uses` (e.g. `2 10`)
- 📣 Broadcast — sab users ko message
- ⚙️ Settings — shop name, welcome msg, support @, channel URL, referral %, min deposit, tamam payment addresses
- ⚠️ Low-stock alerts (3 ya kam par), har order ki notification

## 🚀 Setup (5 minute)

1. **Bot banayen:** Telegram mein [@BotFather](https://t.me/BotFather) → `/newbot` → token copy karein
2. **Apni ID lein:** [@userinfobot](https://t.me/userinfobot) ko `/start` karein
3. **Files server par rakhein** (apne PC ya kisi VPS — Hostinger/Contabo/AWS sab chalega)
4. Install & configure:

```bash
cd telegram_shop_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env          # BOT_TOKEN aur ADMIN_IDS bharein
python3 main.py
```

Bas! Bot live hai. `/start` user ke liye, `/admin` aapke liye.

## 🤖 Auto Payments (Crypto Bot) — optional

Manual approval ke bajaye automatic deposits ke liye:
1. [@CryptoBot](https://t.me/CryptoBot) → **Crypto Pay** → **Create App** → token milega
2. `.env` mein `CRYPTOBOT_TOKEN=` daal dein, bot restart karein
3. Ab users **Crypto Bot (Auto ✔)** se pay karenge — payment detect hote hi balance auto-add (har 60s check)

## 🖥 VPS par 24/7 chalana (systemd)

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
sudo systemctl enable --now shopbot
sudo journalctl -u shopbot -f   # logs
```

## 📡 Reseller API

Har user apni key **Settings → Api Key** mein dekhta hai:

```bash
# Products + live prices
curl -H "X-API-Key: USER_KEY" http://SERVER_IP:8080/api/products

# Balance
curl -H "X-API-Key: USER_KEY" http://SERVER_IP:8080/api/me

# Buy (balance se cut hoga, item response mein)
curl -X POST -H "X-API-Key: USER_KEY" -H "Content-Type: application/json" \
     -d '{"product_id": 1}' http://SERVER_IP:8080/api/buy
```

VPS firewall mein port 8080 kholna na bhoolein (`sudo ufw allow 8080`).

## ⚙️ Pehle ye settings zaroor karein

`/admin` → ⚙️ Settings:
- `shop_name` — apni shop ka naam
- `support` — apna support @username
- `channel_url` — apne channel ka link
- `pay_binance`, `pay_bep20`, `pay_bybit`, `pay_ton`, `pay_ltc` — apne addresses/IDs
- `ref_percent` — referral commission %
- `welcome` — welcome message (optional)

`keyboards.py` mein **Kiwi Ai** button ka link bhi apne hisab se badal lein.

## 📌 Notes

- Database `shop.db` (SQLite) — backup ke liye bas ye file copy karein
- Broadcast bade userbase par thoda slow ho sakta hai (rate-limit safe delay laga hua hai)
- `.env` aur `shop.db` **kabhi share na karein** — isme token aur data hai
- Telegram ke [Terms of Service](https://telegram.org/tos) ke mutabiq istemal karein
