"""Saare inline keyboards — user side aur admin panel."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


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


def products_kb(products, page, total_pages, grouped=None):
    """grouped: dict label->[products] jab Shop Grouping ON ho."""
    kb = []
    if grouped:
        for label, plist in grouped.items():
            kb.append([InlineKeyboardButton(f"— {label} —", callback_data="noop")])
            for p in plist:
                kb.append(_product_row(p))
    else:
        for p in products:
            kb.append(_product_row(p))
    nav = [InlineKeyboardButton("🔄 Refresh", callback_data=f"shop:{page}"),
           InlineKeyboardButton(f"{page + 1}/{max(total_pages, 1)}", callback_data="noop"),
           InlineKeyboardButton("➡ Next", callback_data=f"shop:{page + 1}")]
    kb.append(nav)
    kb.append([InlineKeyboardButton("◀ Back", callback_data="home")])
    return InlineKeyboardMarkup(kb)


def _product_row(p):
    from db import price_of
    price, on_sale = price_of(p)
    stock = p["stock_count"]
    if stock <= 0:
        btn = InlineKeyboardButton(
            f"{p['emoji']} {p['name']} - {price:g}USDT (Stock: 0)", callback_data="noop")
    else:
        label = f"{p['emoji']} {p['name']} - {price:g}USDT (Stock: {stock})"
        if on_sale:
            label = "🔥 " + label
        btn = InlineKeyboardButton(label, callback_data=f"buy:{p['id']}")
    return [btn]


def product_view_kb(pid, on_sale):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy Now", callback_data=f"confirmbuy:{pid}")],
        [InlineKeyboardButton("◀ Back", callback_data="shop:0")],
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
    row = [5, 10, 20]
    kb = [[InlineKeyboardButton(f"${a}", callback_data=f"cryptoamt:{a}") for a in row]]
    kb.append([InlineKeyboardButton("✏️ Custom Amount", callback_data="cryptoamt:custom")])
    kb.append([InlineKeyboardButton("◀ Back", callback_data="topup")])
    return InlineKeyboardMarkup(kb)


def settings_kb(u):
    notif = "🔔 Notifications: ON" if u["notif"] else "🔕 Notifications: OFF"
    grouping = "🗂 Shop Grouping: ON" if u["grouping"] == "on" else "🗂 Shop Grouping: OFF"
    view = "🛍 Shop View: Buttons" if u["shop_view"] == "buttons" else "🛍 Shop View: List"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("💼 My Orders", callback_data="orders")],
        [InlineKeyboardButton("🌐 Language", callback_data="lang"),
         InlineKeyboardButton(notif, callback_data="notif_toggle")],
        [InlineKeyboardButton("✉️ Email Settings", callback_data="email"),
         InlineKeyboardButton("🪙 My Deposits", callback_data="deposits")],
        [InlineKeyboardButton("🌍 Set Region", callback_data="region"),
         InlineKeyboardButton("🎁 Gift Code", callback_data="gift")],
        [InlineKeyboardButton("📖 Bot Tutorial", callback_data="tutorial"),
         InlineKeyboardButton("💲 Send Price List", callback_data="pricelist")],
        [InlineKeyboardButton("💱 Currency", callback_data="currency"),
         InlineKeyboardButton("🔑 Api Key", callback_data="apikey")],
        [InlineKeyboardButton(view, callback_data="shopview_toggle"),
         InlineKeyboardButton(grouping, callback_data="grouping_toggle")],
        [InlineKeyboardButton("◀ Back", callback_data="home")],
    ])


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
        [InlineKeyboardButton("🔥 Flash Sale", callback_data=f"adm:sale:{p['id']}"),
         InlineKeyboardButton(on, callback_data=f"adm:toggle:{p['id']}")],
        [InlineKeyboardButton("🗑 Delete Product", callback_data=f"adm:del:{p['id']}")],
        [InlineKeyboardButton("◀ Back", callback_data="adm:products:0")],
    ])


def admin_settings_kb(db):
    def row(key, label):
        val = db.get_setting(key) or "not set"
        short = (val[:18] + "…") if len(val) > 19 else val
        return [InlineKeyboardButton(f"{label}: {short}", callback_data=f"adm:set:{key}")]
    kb = [row("shop_name", "🏪 Shop Name"), row("welcome", "👋 Welcome Msg"),
          row("support", "🆘 Support @"), row("channel_url", "📢 Channel URL"),
          row("ref_percent", "⭐ Referral %"), row("min_deposit", "💵 Min Deposit"),
          row("pay_binance", "🟡 Binance Pay"), row("pay_bep20", "🪙 BEP20"),
          row("pay_bybit", "⚫ Bybit"), row("pay_ton", "💎 TON"),
          row("pay_ltc", "🩶 LTC"), row("pay_others", "🌐 Others")]
    kb.append([InlineKeyboardButton("◀ Back", callback_data="adm:home")])
    return InlineKeyboardMarkup(kb)


def admin_deposit_kb(did):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"adm:dep_ok:{did}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"adm:dep_no:{did}")],
    ])


def back_kb(target="home"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀ Back", callback_data=target)]])
