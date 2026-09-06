"""Saare inline keyboards — v2 (qty selector, direct pay, settings sub-menus, admin)."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from data_lists import CURRENCIES, LANGUAGES, REGIONS
from db import price_of


def main_menu(db):
    ch = db.get_setting("channel_url")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Shop", callback_data="shop:0")],
        [InlineKeyboardButton("💰 Top-up Wallet", callback_data="topup"),
         InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("🆘 Support", callback_data="support"),
         InlineKeyboardButton("🤖 Kiwi Ai", url="https://t.me/kimi_ai_bot")],
        [InlineKeyboardButton("⭐ Refer", callback_data="refer"),
         InlineKeyboardButton("📢 Channel", url=ch)],
    ])


def products_kb(products, page, total_pages, view="list", grouped=None):
    kb = []
    if grouped:
        for label, plist in grouped.items():
            kb.append([InlineKeyboardButton(f"— {label} —", callback_data="noop")])
            for p in plist:
                kb.append(_product_row(p))
    else:
        for p in products:
            kb.append(_product_row(p))
    if view == "all":
        kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="shop:0")])
    else:
        kb.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"shop:{page}"),
                   InlineKeyboardButton(f"{page + 1}/{max(total_pages, 1)}",
                                        callback_data="noop"),
                   InlineKeyboardButton("➡ Next", callback_data=f"shop:{page + 1}")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def _product_row(p):
    price, on_sale = price_of(p)
    stock = p["stock_count"]
    if stock <= 0:
        return [InlineKeyboardButton(
            f"{p['emoji']} {p['name']} - {price:g}USDT (Stock: 0)", callback_data="noop")]
    label = f"{p['emoji']} {p['name']} - {price:g}USDT (Stock: {stock})"
    if on_sale:
        label = "🔥 " + label
    return [InlineKeyboardButton(label, callback_data=f"buy:{p['id']}")]


def product_detail_kb(pid, qty, stock):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➖", callback_data=f"qty:{pid}:{qty - 1}"),
         InlineKeyboardButton(f"🔢 {qty}", callback_data="noop"),
         InlineKeyboardButton("➕", callback_data=f"qty:{pid}:{qty + 1}")],
        [InlineKeyboardButton("🛒 Buy Now", callback_data=f"summary:{pid}:{qty}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"buy:{pid}"),
         InlineKeyboardButton("🔢 Custom Quantity", callback_data=f"qtycustom:{pid}")],
        [InlineKeyboardButton("🔗 📋 Copy Link", callback_data=f"copylink:{pid}"),
         InlineKeyboardButton("🗒 View Note", callback_data=f"note:{pid}")],
        [InlineKeyboardButton("◀ Back", callback_data="shop:0")],
    ])


def order_summary_kb(pid, qty, wallet_balance, total):
    kb = []
    if wallet_balance >= total:
        kb.append([InlineKeyboardButton("🪙 Wallet", callback_data=f"paywallet:{pid}:{qty}")])
    else:
        kb.append([InlineKeyboardButton(
            f"🪙 Wallet (❌ ${total - wallet_balance:g} kam)", callback_data="noop")])
    kb.append([InlineKeyboardButton("💳 Pay Direct", callback_data=f"paydirect:{pid}:{qty}")])
    kb.append([InlineKeyboardButton("💰 Top-up", callback_data="topup")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data=f"buy:{pid}")])
    return InlineKeyboardMarkup(kb)


def direct_pay_kb(pid, qty, crypto_enabled):
    kb = [[InlineKeyboardButton("🟡 Binance Pay", callback_data=f"dirpay:{pid}:{qty}:binance")],
          [InlineKeyboardButton("🪙 Usdt Bep20", callback_data=f"dirpay:{pid}:{qty}:bep20")],
          [InlineKeyboardButton("⚫ Bybit Pay", callback_data=f"dirpay:{pid}:{qty}:bybit")],
          [InlineKeyboardButton("💎 Usdt Ton", callback_data=f"dirpay:{pid}:{qty}:ton")],
          [InlineKeyboardButton("🩶 LTC", callback_data=f"dirpay:{pid}:{qty}:ltc")]]
    if crypto_enabled:
        kb.append([InlineKeyboardButton("🤖 Crypto Bot (Auto ✔)",
                                        callback_data=f"dirpay:{pid}:{qty}:crypto")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data=f"summary:{pid}:{qty}")])
    return InlineKeyboardMarkup(kb)


def deposit_help_kb(method, back="topup"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧐 Where to find Order ID?",
                              callback_data=f"tut:{method}")],
        [InlineKeyboardButton("◀ Cancel", callback_data=back)],
    ])


def topup_kb(crypto_enabled):
    kb = []
    if crypto_enabled:
        kb.append([InlineKeyboardButton("🤖 Crypto Bot (Auto ✔)", callback_data="dep:crypto")])
    kb += [
        [InlineKeyboardButton("🟡 Binance Pay", callback_data="dep:binance")],
        [InlineKeyboardButton("🪙 Usdt Bep20", callback_data="dep:bep20")],
        [InlineKeyboardButton("⚫ Bybit Pay", callback_data="dep:bybit")],
        [InlineKeyboardButton("💎 Usdt Ton", callback_data="dep:ton")],
        [InlineKeyboardButton("🩶 LTC", callback_data="dep:ltc")],
        [InlineKeyboardButton("🌐 Others", callback_data="dep:others")],
        [InlineKeyboardButton("◀ Back", callback_data="home")],
    ]
    return InlineKeyboardMarkup(kb)


def crypto_amounts_kb():
    kb = [[InlineKeyboardButton(f"${a}", callback_data=f"cryptoamt:{a}")
           for a in (5, 10, 20)]]
    kb.append([InlineKeyboardButton("✏️ Custom Amount", callback_data="cryptoamt:custom")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data="topup")])
    return InlineKeyboardMarkup(kb)


def settings_kb(u):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("💼 My Orders", callback_data="orders")],
        [InlineKeyboardButton("🌐 Language", callback_data="lang"),
         InlineKeyboardButton("🔔 Notifications", callback_data="notif")],
        [InlineKeyboardButton("✉️ Email Settings", callback_data="email"),
         InlineKeyboardButton("🪙 My Deposits", callback_data="deposits")],
        [InlineKeyboardButton("🌍 Set Region", callback_data="region"),
         InlineKeyboardButton("🎁 Gift Code", callback_data="gift")],
        [InlineKeyboardButton("📖 Bot Tutorial", callback_data="tutorial"),
         InlineKeyboardButton("💲 Send Price List", callback_data="pricelist")],
        [InlineKeyboardButton("💱 Currency", callback_data="currency"),
         InlineKeyboardButton("🔑 Api Key", callback_data="apikey")],
        [InlineKeyboardButton("🛍 Shop View", callback_data="shopview"),
         InlineKeyboardButton("🗂 Shop Grouping", callback_data="grouping_toggle")],
        [InlineKeyboardButton("◀ Back", callback_data="home")],
    ])


def stats_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="stats")],
        [InlineKeyboardButton("📊 24h", callback_data="stats_p:86400"),
         InlineKeyboardButton("📊 7d", callback_data="stats_p:604800")],
        [InlineKeyboardButton("📊 30d", callback_data="stats_p:2592000"),
         InlineKeyboardButton("📊 Custom", callback_data="stats_custom")],
        [InlineKeyboardButton("📨 Send Stats PDF to Email", callback_data="stats_pdf")],
        [InlineKeyboardButton("◀ Back to Settings", callback_data="settings")],
    ])


def currency_kb(u, page=0, per=8):
    total = (len(CURRENCIES) + per - 1) // per
    page = max(0, min(page, total - 1))
    kb = []
    for code, name in CURRENCIES[page * per:(page + 1) * per]:
        tick = "✅ " if u["currency"] == code else ""
        kb.append([InlineKeyboardButton(f"{tick}{code} — {name}",
                                        callback_data=f"cur:{code}")])
    kb.append([InlineKeyboardButton(f"{page + 1}/{total}", callback_data="noop"),
               InlineKeyboardButton("➡ Next", callback_data=f"curpage:{page + 1}")])
    kb.append([InlineKeyboardButton("◀ Back to Settings", callback_data="settings")])
    return InlineKeyboardMarkup(kb)


def region_kb(u, page=0, per=12):
    total = (len(REGIONS) + per - 1) // per
    page = max(0, min(page, total - 1))
    chunk = REGIONS[page * per:(page + 1) * per]
    kb = []
    for i in range(0, len(chunk), 2):
        row = [InlineKeyboardButton(
            ("✅ " if u["region"] == chunk[i] else "") + chunk[i],
            callback_data=f"reg:{chunk[i]}")]
        if i + 1 < len(chunk):
            row.append(InlineKeyboardButton(
                ("✅ " if u["region"] == chunk[i + 1] else "") + chunk[i + 1],
                callback_data=f"reg:{chunk[i + 1]}"))
        kb.append(row)
    kb.append([InlineKeyboardButton(f"{page + 1}/{total}", callback_data="noop"),
               InlineKeyboardButton("Next", callback_data=f"regpage:{page + 1}")])
    kb.append([InlineKeyboardButton("🚫 Clear", callback_data="reg:"),
               InlineKeyboardButton("◀ Back to Settings", callback_data="settings")])
    return InlineKeyboardMarkup(kb)


def lang_kb(u):
    kb = []
    for code, name in LANGUAGES:
        tick = "✅ " if u["lang"] == code else ""
        kb.append([InlineKeyboardButton(f"{tick}{name}", callback_data=f"lang:{code}")])
    kb.append([InlineKeyboardButton("◀ Back to Settings", callback_data="settings")])
    return InlineKeyboardMarkup(kb)


def notif_kb(u):
    def row(field, label):
        on = u.get(field, 1)
        return [InlineKeyboardButton(f"{'✅' if on else '❌'} {label}: "
                                     f"{'ON' if on else 'OFF'}",
                                     callback_data=f"ntog:{field}")]
    kb = [row("n_stock", "🔔 Stock Alerts"), row("n_info", "🔔 Info Alerts"),
          row("n_wallet", "🔔 Wallet Alerts"), row("n_email", "📧 Email Reports")]
    kb.append([InlineKeyboardButton("◀ Back to Settings", callback_data="settings")])
    return InlineKeyboardMarkup(kb)


def shopview_kb(u):
    cur = "All products list" if u["shop_view"] == "all" else "10 per page"
    text_kb = [
        [InlineKeyboardButton("💼 10 per page", callback_data="sview:list")],
        [InlineKeyboardButton("📃 All products list", callback_data="sview:all")],
        [InlineKeyboardButton("◀ Back to Settings", callback_data="settings")],
    ]
    return text_kb, cur


def api_kb(u):
    kb = [[InlineKeyboardButton("🔑 Regenerate Key", callback_data="api_regen")]]
    if u.get("api_disabled"):
        kb.append([InlineKeyboardButton("✅ Enable API", callback_data="api_toggle")])
    else:
        kb.append([InlineKeyboardButton("❌ Disable API", callback_data="api_toggle")])
    kb.append([InlineKeyboardButton("📄 View API Documentation", callback_data="api_docs")])
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="apikey")])
    kb.append([InlineKeyboardButton("◀ Back to Settings", callback_data="settings")])
    return InlineKeyboardMarkup(kb)


# ---------------- ADMIN ----------------

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard", callback_data="adm:dash")],
        [InlineKeyboardButton("📦 Products", callback_data="adm:products:0"),
         InlineKeyboardButton("➕ Add Product", callback_data="adm:addprod")],
        [InlineKeyboardButton("💰 Pending Deposits", callback_data="adm:deposits"),
         InlineKeyboardButton("➕ Add Stock", callback_data="adm:addstock_pick:0")],
        [InlineKeyboardButton("👥 Users", callback_data="adm:users"),
         InlineKeyboardButton("🎁 Gift Codes", callback_data="adm:gift")],
        [InlineKeyboardButton("📣 Broadcast", callback_data="adm:broadcast"),
         InlineKeyboardButton("⚙️ Settings", callback_data="adm:settings")],
        [InlineKeyboardButton("◀ Close Panel", callback_data="adm:close")],
    ])


def admin_products_kb(products, page, total):
    kb = []
    for p in products:
        st = "🟢" if p["active"] else "🔴"
        kb.append([InlineKeyboardButton(
            f"{st} #{p['id']} {p['name']} — ${p['price']:g} (Stock: {p['stock_count']})",
            callback_data=f"adm:prod:{p['id']}")])
    kb.append([InlineKeyboardButton("◀ Prev", callback_data=f"adm:products:{page - 1}"),
               InlineKeyboardButton(f"{page + 1}/{max(total, 1)}", callback_data="noop"),
               InlineKeyboardButton("Next ▶", callback_data=f"adm:products:{page + 1}")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data="adm:home")])
    return InlineKeyboardMarkup(kb)


def admin_product_manage_kb(p):
    on = "🔴 Disable" if p["active"] else "🟢 Enable"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Stock", callback_data=f"adm:addstock:{p['id']}")],
        [InlineKeyboardButton("✏️ Rename", callback_data=f"adm:rename:{p['id']}"),
         InlineKeyboardButton("💲 Edit Price", callback_data=f"adm:price:{p['id']}")],
        [InlineKeyboardButton("📝 Description", callback_data=f"adm:desc:{p['id']}"),
         InlineKeyboardButton("🗒 Note", callback_data=f"adm:note:{p['id']}")],
        [InlineKeyboardButton("🛡 Warranty", callback_data=f"adm:warranty:{p['id']}"),
         InlineKeyboardButton("⏳ Hold", callback_data=f"adm:hold:{p['id']}")],
        [InlineKeyboardButton("🔥 Flash Sale", callback_data=f"adm:sale:{p['id']}"),
         InlineKeyboardButton(on, callback_data=f"adm:toggle:{p['id']}")],
        [InlineKeyboardButton("🗑 Delete Product", callback_data=f"adm:del:{p['id']}")],
        [InlineKeyboardButton("◀ Back", callback_data="adm:products:0")],
    ])


def admin_settings_kb(db):
    kb = []

    def row(key, label):
        val = db.get_setting(key) or "not set"
        short = (val[:16] + "…") if len(val) > 17 else val
        kb.append([InlineKeyboardButton(f"{label}: {short}", callback_data=f"adm:set:{key}")])
    row("shop_name", "🏪 Shop Name")
    row("welcome", "👋 Welcome Msg")
    row("support", "🆘 Support @")
    row("channel_url", "📢 Channel URL")
    row("ref_percent", "⭐ Referral %")
    row("min_deposit", "💵 Min Deposit")
    row("pay_binance", "🟡 Binance Pay")
    row("pay_bep20", "🪙 BEP20")
    row("pay_bybit", "⚫ Bybit")
    row("pay_ton", "💎 TON")
    row("pay_ltc", "🩶 LTC")
    row("pay_others", "🌐 Others")
    row("tut_binance", "🧐 Tut: Binance")
    row("tut_bep20", "🧐 Tut: BEP20")
    row("tut_bybit", "🧐 Tut: Bybit")
    row("tut_ton", "🧐 Tut: TON")
    row("tut_ltc", "🧐 Tut: LTC")
    row("tut_crypto", "🧐 Tut: CryptoBot")
    kb.append([InlineKeyboardButton("💱 Currency Rates", callback_data="adm:rates:0")])
    kb.append([InlineKeyboardButton("📧 SMTP (Email PDF)", callback_data="adm:smtp")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data="adm:home")])
    return InlineKeyboardMarkup(kb)


def admin_rates_kb(db, page=0, per=8):
    items = [(c, n) for c, n in CURRENCIES if c != "USDT"]
    total = (len(items) + per - 1) // per
    page = max(0, min(page, total - 1))
    kb = []
    for code, name in items[page * per:(page + 1) * per]:
        kb.append([InlineKeyboardButton(
            f"{code}: {db.get_setting('rate_' + code, '0')}",
            callback_data=f"adm:set:rate_{code}")])
    kb.append([InlineKeyboardButton("◀ Prev", callback_data=f"adm:rates:{page - 1}"),
               InlineKeyboardButton(f"{page + 1}/{total}", callback_data="noop"),
               InlineKeyboardButton("Next ▶", callback_data=f"adm:rates:{page + 1}")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data="adm:settings")])
    return InlineKeyboardMarkup(kb)


def admin_smtp_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("smtp_host", callback_data="adm:set:smtp_host"),
         InlineKeyboardButton("smtp_port", callback_data="adm:set:smtp_port")],
        [InlineKeyboardButton("smtp_user", callback_data="adm:set:smtp_user"),
         InlineKeyboardButton("smtp_pass", callback_data="adm:set:smtp_pass")],
        [InlineKeyboardButton("smtp_from", callback_data="adm:set:smtp_from")],
        [InlineKeyboardButton("◀ Back", callback_data="adm:settings")],
    ])


def admin_deposit_kb(did):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"adm:dep_ok:{did}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"adm:dep_no:{did}")],
    ])


def back_kb(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀ Back", callback_data=target)]])
