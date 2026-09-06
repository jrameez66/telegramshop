"""User-facing flows: /start, shop, purchase, topup, settings, referrals, gifts."""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import states as st
from config import ADMIN_IDS, API_PORT
from db import price_of
from keyboards import (admin_deposit_kb, back_kb, crypto_amounts_kb, main_menu,
                       product_view_kb, products_kb, settings_kb, topup_kb)

log = logging.getLogger(__name__)
PAGE_SIZE = 10

METHOD_NAMES = {
    "binance": "🟡 Binance Pay",
    "bep20": "🪙 USDT BEP20",
    "bybit": "⚫ Bybit Pay",
    "ton": "💎 USDT TON",
    "ltc": "🩶 LTC",
}


async def notify_admins(bot, text, kb=None):
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            log.warning("admin notify failed %s: %s", aid, e)


async def _edit(q, text, kb=None):
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb,
                                  disable_web_page_preview=True)
    except Exception:
        try:
            await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb,
                                       disable_web_page_preview=True)
        except Exception as e:
            log.warning("edit failed: %s", e)


def _welcome_text(db, u):
    shop = db.get_setting("shop_name")
    welcome = db.get_setting("welcome") or f"🛍 <b>Welcome to {shop}!</b>"
    return f"{welcome}\n\n🪙 Your balance: <b>${u['balance']:g}</b>"


# ---------------------------------------------------------------- /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    u, is_new = db.ensure_user(update.effective_user)
    if u.get("banned"):
        return

    # referral: /start ref_12345
    if is_new and context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                ref_id = int(arg[4:])
            except ValueError:
                ref_id = 0
            if ref_id and ref_id != u["user_id"] and db.get_user(ref_id):
                if db.add_referral(ref_id, u["user_id"]):
                    try:
                        await context.bot.send_message(
                            ref_id,
                            f"🎉 <b>Naya referral!</b>\n{u['first_name']} aapke link se join hua.",
                            parse_mode="HTML")
                    except Exception:
                        pass

    await update.message.reply_text(_welcome_text(db, u), parse_mode="HTML",
                                    reply_markup=main_menu(db))


# ---------------------------------------------------------------- views
async def _show_shop(q, db, u, page):
    total = db.count_products()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    prods = db.list_products(page * PAGE_SIZE, PAGE_SIZE)
    if not prods:
        return await _edit(q, "😔 Abhi koi product available nahi.\nBaad mein check karein!",
                           back_kb())
    grouped = None
    if u["grouping"] == "on":
        grouped = {}
        for p in prods:
            grouped.setdefault(p["name"].split()[0], []).append(p)
    await _edit(q, "<b>Available Products:</b>",
                products_kb(prods, page, pages, grouped))


async def _show_product(q, db, u, pid):
    p = db.get_product(pid)
    if not p or not p["active"]:
        await q.answer("❌ Product unavailable", show_alert=True)
        return
    price, on_sale = price_of(p)
    if p["stock_count"] <= 0:
        await q.answer("😔 Out of stock!", show_alert=True)
        return
    lines = [f"{p['emoji']} <b>{p['name']}</b>", ""]
    if on_sale:
        lines += ["🛍 <b>FLASH SALE — LIMITED TIME!</b>", "",
                  f"💵 Was: <s>{p['price']:g} USDT</s>",
                  f"⚡️ Now: <b>{price:g} USDT</b>", ""]
    else:
        lines += [f"💵 Price: <b>{price:g} USDT</b>", ""]
    lines += [f"📦 Stock: <b>{p['stock_count']}</b>",
              f"🪙 Your balance: <b>${u['balance']:g}</b>"]
    await _edit(q, "\n".join(lines), product_view_kb(pid, on_sale))


async def _do_buy(q, context, db, u, pid):
    res = db.purchase(u["user_id"], pid)
    if not res["ok"]:
        if res["err"] == "balance":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Top-up Wallet", callback_data="topup")],
                [InlineKeyboardButton("◀ Back", callback_data="shop:0")]])
            return await _edit(
                q,
                f"⚠️ <b>Insufficient balance!</b>\n\n"
                f"💵 Price: ${res['price']:g}\n"
                f"🪙 Balance: ${u['balance']:g}\n"
                f"❗️ Aur <b>${res['need']:g}</b> chahiye.", kb)
        if res["err"] == "stock":
            await q.answer("😔 Maaf kijiye, abhi-abhi stock khatam hua!", show_alert=True)
            return await _show_shop(q, db, u, 0)
        await q.answer("❌ Product unavailable", show_alert=True)
        return

    await _edit(
        q,
        f"✅ <b>Purchase Successful!</b>\n\n"
        f"📦 Product: <b>{res['product']}</b>\n"
        f"💵 Paid: <b>${res['price']:g}</b>\n"
        f"🧾 Order ID: <code>#{res['order_id']}</code>\n\n"
        f"📄 <b>Your item:</b>\n<code>{res['content']}</code>\n\n"
        f"⚠️ Isay save kar lein — ye My Orders mein bhi available rahega.",
        back_kb("shop:0"))
    await notify_admins(
        context.bot,
        f"🛒 <b>New Order</b>\n👤 {u['first_name']} (<code>{u['user_id']}</code>)\n"
        f"📦 {res['product']} — ${res['price']:g}\n📦 Stock left: {res['stock_left']}")
    if res["stock_left"] <= 3:
        await notify_admins(
            context.bot,
            f"⚠️ <b>Low stock alert:</b> {res['product']} — sirf {res['stock_left']} bache!")


async def _show_settings(q, db, u):
    joined = (u["joined_at"] or "")[:10]
    text = (f"👤 <b>User Profile</b>\n\n"
            f"🆔 ID: <code>{u['user_id']}</code>\n"
            f"✈️ First Name: {u['first_name']}\n"
            f"⚙️ Username: @{u['username'] or '—'}\n"
            f"✅ Status: started bot\n"
            f"✉️ Email: {u['email'] or '<i>not set — tap Email Settings</i>'}\n"
            f"🪙 Balance: <b>{u['balance']:g} USDT</b>\n"
            f"💵 Currency: USDT\n"
            f"🌐 Language: {u['lang']}\n"
            f"🌍 Region: {u['region'] or '<i>not set — tap Set Region</i>'}\n"
            f"🗓 Joined: {joined}")
    await _edit(q, text, settings_kb(u))


async def _crypto_invoice_reply(send, context, uid, amount):
    db = context.bot_data["db"]
    crypto = context.bot_data["crypto"]
    if amount < 1:
        return await send("❌ Minimum $1.")
    inv = await crypto.create_invoice(amount)
    if not inv:
        return await send("❌ Invoice create nahi hua. Baad mein try karein ya manual method use karein.")
    db.create_deposit(uid, amount, "cryptobot", invoice_id=str(inv["invoice_id"]))
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now", url=inv["bot_invoice_url"])],
                               [InlineKeyboardButton("◀ Back", callback_data="topup")]])
    await send(f"🤖 <b>Crypto Bot Invoice</b>\n\n"
               f"💵 Amount: <b>{amount:g} USDT</b>\n"
               f"⏳ Valid: 30 minutes\n\n"
               f"Payment ke baad balance <b>automatically</b> add ho jayega ✅", kb)


# ---------------------------------------------------------------- callbacks
async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    db = context.bot_data["db"]
    u = db.get_user(q.from_user.id)
    if not u:
        u, _ = db.ensure_user(q.from_user)
    if u.get("banned"):
        await q.answer("🚫 Aap blocked hain.", show_alert=True)
        return
    await q.answer()

    if data == "noop":
        return
    if data == "home":
        st.clear(u["user_id"])
        return await _edit(q, _welcome_text(db, u), main_menu(db))
    if data.startswith("shop:"):
        return await _show_shop(q, db, u, int(data.split(":")[1]))
    if data.startswith("buy:"):
        return await _show_product(q, db, u, int(data.split(":")[1]))
    if data.startswith("confirmbuy:"):
        return await _do_buy(q, context, db, u, int(data.split(":")[1]))

    # ---------- topup ----------
    if data == "topup":
        st.clear(u["user_id"])
        crypto = context.bot_data["crypto"]
        note = ("\n\n🤖 <b>Crypto Bot</b> = automatic, instant confirmation!"
                if crypto.enabled else
                "\n\nℹ️ Payment ke baad TX ID bhejein — admin approve karke balance add karega.")
        return await _edit(q, "💰 <b>Top Up Wallet</b>\n\nPayment method select karein:" + note,
                           topup_kb(crypto.enabled))
    if data.startswith("dep:"):
        method = data.split(":", 1)[1]
        if method == "crypto":
            return await _edit(q, "🤖 <b>Crypto Bot</b> — amount select karein (USDT):",
                               crypto_amounts_kb())
        if method == "others":
            return await _edit(q, f"🌐 <b>Other Payment Methods</b>\n\n{db.get_setting('pay_others')}",
                               back_kb("topup"))
        addr = db.get_setting(f"pay_{method}")
        min_dep = db.get_setting("min_deposit", "1")
        st.set_state(u["user_id"], st.S_DEP_AMOUNT, method=method)
        return await _edit(
            q,
            f"{METHOD_NAMES.get(method, method)}\n\n"
            f"📮 <b>Payment Address / ID:</b>\n<code>{addr}</code>\n\n"
            f"💵 Minimum deposit: <b>${min_dep}</b>\n\n"
            f"✏️ Ab amount bhejein (USD, masalan <code>10</code>):",
            back_kb("topup"))
    if data.startswith("cryptoamt:"):
        val = data.split(":")[1]
        if val == "custom":
            st.set_state(u["user_id"], st.S_CRYPTO_CUSTOM)
            return await _edit(q, "✏️ Amount bhejein (USD, minimum $1):", back_kb("topup"))
        async def send_q(text, kb=None):
            await _edit(q, text, kb)
        return await _crypto_invoice_reply(send_q, context, u["user_id"], float(val))

    # ---------- settings & profile ----------
    if data == "settings":
        st.clear(u["user_id"])
        return await _show_settings(q, db, u)
    if data == "stats":
        orders, spent = db.order_stats(u["user_id"])
        cnt = db.referral_count(u["user_id"])
        return await _edit(
            q,
            f"📊 <b>Your Stats</b>\n\n"
            f"🛒 Orders: <b>{orders}</b>\n"
            f"💸 Total spent: <b>${spent:g}</b>\n"
            f"👥 Referrals: <b>{cnt}</b>\n"
            f"⭐ Referral earnings: <b>${u['ref_earnings']:g}</b>\n"
            f"🪙 Balance: <b>${u['balance']:g}</b>",
            back_kb("settings"))
    if data == "orders":
        orders = db.user_orders(u["user_id"], 10)
        if not orders:
            return await _edit(q, "💼 <b>My Orders</b>\n\nAbhi tak koi order nahi.",
                               back_kb("settings"))
        text = "💼 <b>My Orders</b> (last 10)\n"
        for o in orders:
            text += (f"\n🧾 <code>#{o['id']}</code> — <b>{o['product_name']}</b> — ${o['price_paid']:g}\n"
                     f"📅 {o['created_at'][:16]}\n"
                     f"📄 <code>{o['content']}</code>\n")
        return await _edit(q, text[:4000], back_kb("settings"))
    if data == "deposits":
        deps = db.user_deposits(u["user_id"], 10)
        emap = {"pending": "⏳", "paid": "✅", "rejected": "❌"}
        if not deps:
            return await _edit(q, "🪙 <b>My Deposits</b>\n\nAbhi tak koi deposit nahi.",
                               back_kb("settings"))
        text = "🪙 <b>My Deposits</b> (last 10)\n"
        for d in deps:
            text += (f"\n{emap.get(d['status'], '❔')} <code>#{d['id']}</code> — "
                     f"<b>${d['amount']:g}</b> via {d['method']} — {d['created_at'][:16]}")
        return await _edit(q, text, back_kb("settings"))
    if data == "lang":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang:EN"),
             InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="lang:HI"),
             InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang:BN")],
            [InlineKeyboardButton("◀ Back", callback_data="settings")]])
        return await _edit(q, "🌐 <b>Language select karein:</b>", kb)
    if data.startswith("lang:"):
        db.set_user_field(u["user_id"], "lang", data.split(":")[1][:2].upper())
        return await _show_settings(q, db, db.get_user(u["user_id"]))
    if data == "notif_toggle":
        db.set_user_field(u["user_id"], "notif", 0 if u["notif"] else 1)
        return await _show_settings(q, db, db.get_user(u["user_id"]))
    if data == "shopview_toggle":
        db.set_user_field(u["user_id"], "shop_view",
                          "buttons" if u["shop_view"] == "list" else "list")
        return await _show_settings(q, db, db.get_user(u["user_id"]))
    if data == "grouping_toggle":
        db.set_user_field(u["user_id"], "grouping",
                          "on" if u["grouping"] == "off" else "off")
        return await _show_settings(q, db, db.get_user(u["user_id"]))
    if data == "email":
        st.set_state(u["user_id"], st.S_EMAIL)
        return await _edit(q, "✉️ Apna <b>email</b> bhejein:", back_kb("settings"))
    if data == "region":
        st.set_state(u["user_id"], st.S_REGION)
        return await _edit(q, "🌍 Apna <b>region / country</b> bhejein:", back_kb("settings"))
    if data == "gift":
        st.set_state(u["user_id"], st.S_GIFT_REDEEM)
        return await _edit(q, "🎁 Apna <b>gift code</b> bhejein:", back_kb("settings"))
    if data == "tutorial":
        return await _edit(
            q,
            "📖 <b>Bot Tutorial</b>\n\n"
            "1️⃣ 💰 Top-up Wallet se balance add karein\n"
            "2️⃣ 🛍 Shop se product select karein\n"
            "3️⃣ 🛒 Buy Now dabayen — item <b>turant</b> deliver ho jayega!\n"
            "4️⃣ 💼 My Orders mein apni purchases dekhein\n"
            "5️⃣ ⭐ Refer se dost bulayen aur har deposit par commission payen\n"
            "6️⃣ 🎁 Gift code ho to Settings &gt; Gift Code mein redeem karein\n\n"
            "Koi masla? 🆘 Support se rabta karein.",
            back_kb("settings"))
    if data == "pricelist":
        prods = db.list_products(0, 200)
        if not prods:
            return await _edit(q, "😔 Abhi koi product nahi.", back_kb("settings"))
        lines = [f"💲 <b>Price List — {db.get_setting('shop_name')}</b>\n"]
        for p in prods:
            price, on_sale = price_of(p)
            tag = " 🔥SALE" if on_sale else ""
            stxt = f"Stock: {p['stock_count']}" if p["stock_count"] > 0 else "❌ Out of stock"
            lines.append(f"{p['emoji']} <b>{p['name']}</b> — {price:g} USDT{tag} ({stxt})")
        return await _edit(q, "\n".join(lines)[:4000], back_kb("settings"))
    if data == "currency":
        return await _edit(q, "💱 <b>Currency</b>\n\nDefault: <b>USDT</b> ($)\n\n"
                              "Multi-currency support jald aa raha hai.",
                           back_kb("settings"))
    if data == "apikey":
        return await _edit(
            q,
            f"🔑 <b>Your API Key</b>\n\n<code>{u['api_key']}</code>\n\n"
            "⚠️ Isay secret rakhein!\n\n"
            "📡 <b>Reseller API</b>\n"
            f"Base URL: <code>http://YOUR_SERVER_IP:{API_PORT}</code>\n\n"
            "• <code>GET /api/me</code> — balance/info\n"
            "• <code>GET /api/products</code> — live prices &amp; stock\n"
            "• <code>POST /api/buy</code> — body: {\"product_id\": N}\n\n"
            "Header: <code>X-API-Key: &lt;your key&gt;</code>",
            back_kb("settings"))

    # ---------- misc ----------
    if data == "support":
        sup = db.get_setting("support")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Contact Support",
                                  url=f"https://t.me/{sup.lstrip('@')}")],
            [InlineKeyboardButton("◀ Back", callback_data="home")]])
        return await _edit(q, f"🆘 <b>Support</b>\n\nKisi bhi masle ke liye rabta karein:\n👉 {sup}",
                           kb)
    if data == "refer":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{u['user_id']}"
        pct = db.get_setting("ref_percent", "5")
        cnt = db.referral_count(u["user_id"])
        return await _edit(
            q,
            f"⭐ <b>Refer &amp; Earn</b>\n\n"
            f"🔗 Aapka link:\n<code>{link}</code>\n\n"
            f"👥 Referrals: <b>{cnt}</b>\n"
            f"🎁 Commission: <b>{pct}%</b> har deposit par\n"
            f"💰 Total earned: <b>${u['ref_earnings']:g}</b>",
            back_kb())


# ---------------------------------------------------------------- messages
async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    u, _ = db.ensure_user(update.effective_user)
    if u.get("banned"):
        return
    text = update.message.text.strip()
    state, data = st.get_state(u["user_id"])

    if state == st.S_GIFT_REDEEM:
        st.clear(u["user_id"])
        ok, res = db.redeem_gift(text, u["user_id"])
        if ok:
            nb = db.get_user(u["user_id"])["balance"]
            return await update.message.reply_text(
                f"🎁 <b>Gift code redeem!</b>\n\n💰 +{res:g} USDT\n💳 Balance: ${nb:g}",
                parse_mode="HTML")
        return await update.message.reply_text(res)

    if state == st.S_EMAIL:
        if "@" not in text or "." not in text or len(text) > 100:
            return await update.message.reply_text(
                "❌ Sahi email bhejein (masalan name@gmail.com):")
        db.set_user_field(u["user_id"], "email", text)
        st.clear(u["user_id"])
        return await update.message.reply_text(f"✅ Email set: <code>{text}</code>",
                                               parse_mode="HTML")

    if state == st.S_REGION:
        db.set_user_field(u["user_id"], "region", text[:50])
        st.clear(u["user_id"])
        return await update.message.reply_text(f"✅ Region set: {text[:50]}")

    if state == st.S_DEP_AMOUNT:
        try:
            amt = float(text.replace("$", ""))
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein, masalan <code>10</code>:",
                                                   parse_mode="HTML")
        min_dep = float(db.get_setting("min_deposit", "1"))
        if amt < min_dep:
            return await update.message.reply_text(
                f"❌ Minimum deposit ${min_dep:g} hai. Dobara amount bhejein:")
        st.set_state(u["user_id"], st.S_DEP_PROOF, method=data["method"], amount=amt)
        return await update.message.reply_text(
            f"💵 Amount: <b>${amt:g}</b>\n\n🧾 Ab apni <b>TX ID / Transaction details</b> bhejein:",
            parse_mode="HTML")

    if state == st.S_DEP_PROOF:
        did = db.create_deposit(u["user_id"], data["amount"], data["method"],
                                tx_info=text[:300])
        st.clear(u["user_id"])
        await update.message.reply_text(
            f"✅ <b>Deposit request submit!</b>\n\n"
            f"🧾 ID: <code>#{did}</code>\n💵 Amount: ${data['amount']:g}\n"
            f"⏳ Admin approve karte hi balance add ho jayega.",
            parse_mode="HTML")
        await notify_admins(
            context.bot,
            f"💰 <b>New Deposit Request #{did}</b>\n\n"
            f"👤 {u['first_name']} @{u['username'] or '-'} (<code>{u['user_id']}</code>)\n"
            f"💵 Amount: <b>${data['amount']:g}</b>\n"
            f"🏦 Method: {data['method']}\n"
            f"🧾 TX: <code>{text[:200]}</code>",
            admin_deposit_kb(did))
        return

    if state == st.S_CRYPTO_CUSTOM:
        st.clear(u["user_id"])
        try:
            amt = float(text.replace("$", ""))
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein:")
        async def send_m(t, kb=None):
            await update.message.reply_text(t, parse_mode="HTML", reply_markup=kb)
        return await _crypto_invoice_reply(send_m, context, u["user_id"], amt)

    # seedha gift code bhejne par bhi redeem ho jaye
    if text.upper().startswith("GIFT-"):
        ok, res = db.redeem_gift(text, u["user_id"])
        if ok:
            nb = db.get_user(u["user_id"])["balance"]
            return await update.message.reply_text(
                f"🎁 <b>Gift code redeem!</b>\n\n💰 +{res:g} USDT\n💳 Balance: ${nb:g}",
                parse_mode="HTML")
        return await update.message.reply_text(res)
