"""User-facing flows v2: /start, shop (qty/direct-pay/note), topup, stats+PDF,
currency/region/lang pickers, notification categories, reseller API panel."""
import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes

import states as st
from config import ADMIN_IDS, API_PORT
from db import price_of, time_ago
from keyboards import (admin_deposit_kb, api_kb, back_kb, crypto_amounts_kb,
                       currency_kb, deposit_help_kb, direct_pay_kb, lang_kb,
                       main_menu, notif_kb, order_summary_kb, product_detail_kb,
                       products_kb, region_kb, settings_kb, shopview_kb, stats_kb,
                       topup_kb)
from pdf_report import make_stats_pdf
from data_lists import METHOD_NAMES

log = logging.getLogger(__name__)
PAGE_SIZE = 10


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


def _conv(db, u, usdt):
    """USDT ko user ki display currency mein (payments USDT mein hi hote hain)."""
    code = u.get("currency") or "USDT"
    if code in ("USDT", "USD"):
        return ""
    rate = db.rate(code)
    if not rate:
        return ""
    return f" ≈ <i>{usdt * rate:g} {code}</i>"


def _user_brief(u):
    return f"{u['first_name']} @{u['username'] or '-'} (<code>{u['user_id']}</code>)"


# ---------------------------------------------------------------- /start + commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    u, is_new = db.ensure_user(update.effective_user)
    if u.get("banned"):
        return
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


async def cmd_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    u, _ = db.ensure_user(update.effective_user)
    await _send_shop_reply(update.message, db, u, 0)


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    db.ensure_user(update.effective_user)
    crypto = context.bot_data["crypto"]
    await update.message.reply_text(
        "💰 <b>Top Up Wallet</b>\n\nPayment method select karein:",
        parse_mode="HTML", reply_markup=topup_kb(crypto.enabled))


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    sup = db.get_setting("support")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "💬 Contact Support", url=f"https://t.me/{sup.lstrip('@')}")]])
    await update.message.reply_text(
        f"🆘 <b>Support</b>\n\nKisi bhi masle ke liye rabta karein:\n👉 {sup}",
        parse_mode="HTML", reply_markup=kb)


# ---------------------------------------------------------------- views
async def _send_shop_reply(msg, db, u, page):
    total = db.count_products()
    view = u.get("shop_view", "list")
    if view == "all":
        prods = db.list_products(0, 40)
        pages = 1
    else:
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(page, pages - 1))
        prods = db.list_products(page * PAGE_SIZE, PAGE_SIZE)
    if not prods:
        return await msg.reply_text("😔 Abhi koi product available nahi.",
                                    reply_markup=back_kb())
    grouped = None
    if u.get("grouping") == "on":
        grouped = {}
        for p in prods:
            grouped.setdefault(p["name"].split()[0], []).append(p)
    await msg.reply_text("<b>Available Products:</b>", parse_mode="HTML",
                         reply_markup=products_kb(prods, page, pages, view, grouped))


async def _show_shop(q, db, u, page):
    total = db.count_products()
    view = u.get("shop_view", "list")
    if view == "all":
        prods = db.list_products(0, 40)
        pages = 1
        page = 0
    else:
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(page, pages - 1))
        prods = db.list_products(page * PAGE_SIZE, PAGE_SIZE)
    if not prods:
        return await _edit(q, "😔 Abhi koi product available nahi.\nBaad mein check karein!",
                           back_kb())
    grouped = None
    if u.get("grouping") == "on":
        grouped = {}
        for p in prods:
            grouped.setdefault(p["name"].split()[0], []).append(p)
    await _edit(q, "<b>Available Products:</b>",
                products_kb(prods, page, pages, view, grouped))


async def _show_product(q, db, u, pid, qty=1):
    p = db.get_product(pid)
    if not p or not p["active"]:
        await q.answer("❌ Product unavailable", show_alert=True)
        return
    if p["stock_count"] <= 0:
        await q.answer("😔 Out of stock!", show_alert=True)
        return
    qty = max(1, min(qty, p["stock_count"]))
    price, on_sale = price_of(p)
    total = round(price * qty, 6)
    lines = [f"{p['emoji']} <b>{p['name']}</b>"]
    if on_sale:
        lines.append(f"🤑 Price Base: <s>{p['price']:g}</s> <b>{price:g}USDT</b> 🔥")
    else:
        lines.append(f"🤑 Price Base: {price:g}USDT")
    lines += [
        f"🎁 Available Stock: {p['stock_count']}",
        f"🛡 Warranty: {p.get('warranty') or 'NON'}",
    ]
    if p.get("hold"):
        lines.append(f"⏳ HOLD: {p['hold']}")
    lines += [
        "",
        f"🔢 Selected Qty: {qty}",
        f"✏️ Total Amount: <b>{total:g}USDT</b>{_conv(db, u, total)}",
        f"🪙 Wallet: {u['balance']:g}USDT",
    ]
    await _edit(q, "\n".join(lines), product_detail_kb(pid, qty, p["stock_count"]))


async def _show_summary(q, db, u, pid, qty):
    p = db.get_product(pid)
    if not p or not p["active"] or p["stock_count"] < qty:
        await q.answer("❌ Stock kaafi nahi.", show_alert=True)
        return await _show_product(q, db, u, pid, 1)
    price, _ = price_of(p)
    total = round(price * qty, 6)
    text = (f"💼 <b>Order summary</b>\n\n"
            f"{p['emoji']} <b>{p['name']}</b>\n"
            f"🔢 Qty: {qty}\n"
            f"✏️ Total: <b>{total:g}USDT</b>{_conv(db, u, total)}\n"
            f"🪙 Wallet: {u['balance']:g}USDT\n"
            f"Choose a pay method:")
    await _edit(q, text, order_summary_kb(pid, qty, float(u["balance"]), total))


async def _deliver_order(msg_func, context, db, u, res):
    items = "\n".join(f"<code>{i}</code>" for i in res["items"])
    await msg_func(
        f"✅ <b>Purchase Successful!</b>\n\n"
        f"📦 Product: <b>{res['product']}</b> × {res['qty']}\n"
        f"💵 Paid: <b>${res['total']:g}</b>\n"
        f"🧾 Order ID: <code>#{res['order_id']}</code>\n\n"
        f"📄 <b>Your item(s):</b>\n{items}\n\n"
        f"⚠️ Save kar lein — My Orders mein bhi rahega.")
    await notify_admins(
        context.bot,
        f"🛒 <b>New Order</b>\n👤 {_user_brief(u)}\n"
        f"📦 {res['product']} × {res['qty']} — ${res['total']:g}\n"
        f"📦 Stock left: {res['stock_left']}")
    if res["stock_left"] <= 3:
        await notify_admins(
            context.bot,
            f"⚠️ <b>Low stock alert:</b> {res['product']} — sirf {res['stock_left']} bache!")


async def _do_wallet_buy(q, context, db, u, pid, qty):
    res = db.purchase_multi(u["user_id"], pid, qty)
    if not res["ok"]:
        if res["err"] == "balance":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Top-up Wallet", callback_data="topup")],
                [InlineKeyboardButton("◀ Back", callback_data=f"summary:{pid}:{qty}")]])
            return await _edit(
                q,
                f"⚠️ <b>Insufficient balance!</b>\n\n💵 Total: ${res['total']:g}\n"
                f"🪙 Balance: ${u['balance']:g}\n❗️ Aur <b>${res['need']:g}</b> chahiye.", kb)
        if res["err"] == "stock":
            await q.answer(f"😔 Sirf {res.get('available', 0)} stock bacha!", show_alert=True)
            return await _show_product(q, db, db.get_user(u["user_id"]), pid, 1)
        await q.answer("❌ Unavailable", show_alert=True)
        return

    async def send(text):
        await _edit(q, text, back_kb("shop:0"))
    await _deliver_order(send, context, db, u, res)


async def _show_stats(q, db, u, seconds=None, label="All time"):
    s = db.stats_period(u["user_id"], seconds) if seconds else db.order_stats(u["user_id"])
    last = db.last_order(u["user_id"])
    deps = (db.stats_period(u["user_id"], seconds)["deposits"] if seconds
            else db.deposit_total(u["user_id"]))
    last_txt = ""
    if last:
        dt = datetime.fromisoformat(last).strftime("%d %b %Y, %H:%M UTC")
        last_txt = f"🧾 Last Order: {time_ago(last)} ({dt})\n"
    text = (f"📊 <b>Your Stats</b> — <i>{label}</i>\n\n"
            f"🛍 Orders: {s['orders']}\n"
            f"🎁 Items Bought: {s['items']}\n"
            f"💵 Total Spent: {s['spent']:g} USDT\n"
            f"{last_txt}"
            f"⬇️ Deposits: {deps:g} USDT")
    await _edit(q, text, stats_kb())


async def _show_settings(q, db, u):
    joined = (u["joined_at"] or "")[:10]
    text = (f"👤 <b>User Profile</b>\n\n"
            f"🆔 ID: <code>{u['user_id']}</code>\n"
            f"✈️ First Name: {u['first_name']}\n"
            f"⚙️ Username: @{u['username'] or '—'}\n"
            f"✅ Status: started bot\n"
            f"✉️ Email: {u['email'] or '<i>not set — tap Email Settings</i>'}\n"
            f"🪙 Balance: <b>{u['balance']:g} USDT</b>\n"
            f"💵 Currency: {u.get('currency', 'USDT')}\n"
            f"🌐 Language: {u['lang']}\n"
            f"🌍 Region: {u['region'] or '<i>not set — tap Set Region</i>'}\n"
            f"🗓 Joined: {joined}")
    await _edit(q, text, settings_kb(u))


async def _show_api(q, db, u):
    a = db.api_stats(u["user_id"])
    key = u["api_key"] or ""
    masked = key[:13] + "••••••••" if key else "disabled"
    status = "❌ Disabled" if u.get("api_disabled") else "✅ Connected"
    text = (f"🧾 <b>Reseller Product API</b>\n\n"
            f"Connect your own bot, website, or reseller panel to this shop. "
            f"Orders are delivered from live stock and paid from your wallet balance.\n\n"
            f"{status} Status\n"
            f"🪙 API Balance: {u['balance']:g} USDT\n"
            f"🛍 Total API Orders: {a['orders']}\n"
            f"💵 Recent Spend: {a['spent']:g} USDT\n"
            f"🔑 Current Key: <code>{masked}</code>\n\n"
            f"<b>Available actions</b>\n"
            f"💼 Product list: <code>GET /api/products</code>\n"
            f"🪙 Balance check: <code>GET /api/balance</code>\n"
            f"🛒 Place order: <code>POST /api/order</code>\n\n"
            f"Endpoint URL\n<code>http://YOUR_SERVER_IP:{API_PORT}/api</code>")
    await _edit(q, text, api_kb(u))


async def _crypto_invoice_reply(send, context, uid, amount, kind="topup", meta=""):
    db = context.bot_data["db"]
    crypto = context.bot_data["crypto"]
    if amount < 1:
        return await send("❌ Minimum $1.")
    inv = await crypto.create_invoice(amount, payload=f"{kind}:{meta}:{uid}")
    if not inv:
        return await send("❌ Invoice create nahi hua. Baad mein try karein.")
    db.create_deposit(uid, amount, "cryptobot", invoice_id=str(inv["invoice_id"]),
                      kind=kind, meta=meta)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay Now", url=inv["bot_invoice_url"])],
        [InlineKeyboardButton("◀ Back", callback_data="topup")]])
    await send(f"🤖 <b>Crypto Bot Invoice</b>\n\n💵 Amount: <b>{amount:g} USDT</b>\n"
               f"⏳ Valid: 30 minutes\n\nPayment ke baad <b>automatically</b> process hoga ✅", kb)


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
    uid = u["user_id"]

    if data == "noop":
        return
    if data == "home":
        st.clear(uid)
        return await _edit(q, _welcome_text(db, u), main_menu(db))
    if data.startswith("shop:"):
        return await _show_shop(q, db, u, int(data.split(":")[1]))
    if data.startswith("buy:"):
        return await _show_product(q, db, u, int(data.split(":")[1]))
    if data.startswith("qty:"):
        _, pid, qty = data.split(":")
        return await _show_product(q, db, u, int(pid), int(qty))
    if data.startswith("qtycustom:"):
        st.set_state(uid, st.S_QTY_CUSTOM, pid=int(data.split(":")[1]))
        return await _edit(q, "🔢 <b>Custom Quantity</b>\n\nKitne items chahiye? Number bhejein:",
                           back_kb(f"buy:{data.split(':')[1]}"))
    if data.startswith("note:"):
        pid = int(data.split(":")[1])
        p = db.get_product(pid)
        if not p:
            return
        desc = p.get("description") or "—"
        note = p.get("note") or "—"
        text = (f"🗒 <b>View Note — {p['name']}</b>\n\n"
                f"🗒 <b>Description:</b>\n<blockquote>{desc}</blockquote>\n"
                f"🗒 <b>Note:</b>\n<blockquote>{note}</blockquote>")
        return await _edit(q, text[:4000], back_kb(f"buy:{pid}"))
    if data.startswith("copylink:"):
        me = await context.bot.get_me()
        return await q.answer(
            f"https://t.me/{me.username}?start=buy_{data.split(':')[1]}",
            show_alert=True)
    if data.startswith("summary:"):
        _, pid, qty = data.split(":")
        return await _show_summary(q, db, u, int(pid), int(qty))
    if data.startswith("paywallet:"):
        _, pid, qty = data.split(":")
        return await _do_wallet_buy(q, context, db, u, int(pid), int(qty))
    if data.startswith("paydirect:"):
        _, pid, qty = data.split(":")
        p = db.get_product(int(pid))
        if not p:
            return
        price, _ = price_of(p)
        total = round(price * int(qty), 6)
        crypto = context.bot_data["crypto"]
        text = (f"💳 <b>Select payment method</b>\n\n"
                f"{p['emoji']} {p['name']} × {qty}\n"
                f"💵 Total: <b>{total:g} USDT</b>\n\n"
                f"◀️ Please send the exact amount for verification.")
        return await _edit(q, text, direct_pay_kb(int(pid), int(qty), crypto.enabled))
    if data.startswith("dirpay:"):
        _, pid, qty, method = data.split(":")
        pid, qty = int(pid), int(qty)
        p = db.get_product(pid)
        if not p or p["stock_count"] < qty:
            await q.answer("❌ Stock kaafi nahi.", show_alert=True)
            return
        price, _ = price_of(p)
        total = round(price * qty, 6)
        if method == "crypto":
            async def send_q(t, kb=None):
                await _edit(q, t, kb)
            return await _crypto_invoice_reply(send_q, context, uid, total,
                                               kind="direct", meta=f"{pid}:{qty}")
        addr = db.get_setting(f"pay_{method}")
        st.set_state(uid, st.S_DIRPROOF, pid=pid, qty=qty, amount=total, method=method)
        mname = METHOD_NAMES.get(method, method)
        return await _edit(
            q,
            f"{mname} <b>Deposit</b>\n\n"
            f"📮 <b>Payment Address / ID:</b>\n<code>{addr}</code>\n\n"
            f"1️⃣ Send <b>exactly {total:g} USDT</b> to the ID above\n"
            f"2️⃣ Paste your Order ID below\n\n"
            f"❗️Only up to 3 decimal places will be credited.\n\n"
            f"⛔️ Only payments started after opening this screen and completed "
            f"within 30 minutes will be credited.\n\n"
            f"Please send your Order ID below:",
            deposit_help_kb(method, f"summary:{pid}:{qty}"))
    if data.startswith("tut:"):
        method = data.split(":", 1)[1]
        tut = db.get_setting(f"tut_{method}")
        mname = METHOD_NAMES.get(method, method)
        if not tut:
            tut = ("The admin hasn't added a tutorial for this payment method yet. "
                   "Please check back later.")
        return await _edit(q, f"🧐 <b>Where to find your reference — {mname}</b>\n\n{tut}",
                           back_kb("topup"))

    # ---------- topup ----------
    if data == "topup":
        st.clear(uid)
        crypto = context.bot_data["crypto"]
        note = ("\n\n🤖 <b>Crypto Bot</b> = automatic, instant confirmation!"
                if crypto.enabled else
                "\n\nℹ️ Payment ke baad Order ID bhejein — admin approve karega.")
        return await _edit(q, "💰 <b>Top Up Wallet</b>\n\nPayment method select karein:" + note,
                           topup_kb(crypto.enabled))
    if data.startswith("dep:"):
        method = data.split(":", 1)[1]
        if method == "crypto":
            return await _edit(q, "🤖 <b>Crypto Bot</b> — amount select karein (USDT):",
                               crypto_amounts_kb())
        if method == "others":
            return await _edit(q, f"🌐 <b>Other Payment Methods</b>\n\n"
                                  f"{db.get_setting('pay_others')}", back_kb("topup"))
        addr = db.get_setting(f"pay_{method}")
        min_dep = db.get_setting("min_deposit", "1")
        st.set_state(uid, st.S_DEP_AMOUNT, method=method)
        mname = METHOD_NAMES.get(method, method)
        return await _edit(
            q,
            f"🟡 <b>{mname} Deposit</b>\n\n"
            f"📮 <b>Payment Address / ID:</b>\n<code>{addr}</code>\n\n"
            f"1️⃣ Send any USDT amount to the ID above\n"
            f"2️⃣ Paste your Order ID below\n\n"
            f"❗️Only up to 3 decimal places will be credited to your wallet.\n\n"
            f"⛔️ Only payments started after opening this screen and completed "
            f"within 30 minutes will be credited.\n\n"
            f"💵 Min deposit: ${min_dep} — Pehle <b>amount</b> bhejein (masalan <code>10</code>):",
            deposit_help_kb(method))
    if data.startswith("cryptoamt:"):
        val = data.split(":")[1]
        if val == "custom":
            st.set_state(uid, st.S_CRYPTO_CUSTOM)
            return await _edit(q, "✏️ Amount bhejein (USD, minimum $1):", back_kb("topup"))
        async def send_q2(t, kb=None):
            await _edit(q, t, kb)
        return await _crypto_invoice_reply(send_q2, context, uid, float(val))

    # ---------- settings & profile ----------
    if data == "settings":
        st.clear(uid)
        return await _show_settings(q, db, u)
    if data == "stats":
        return await _show_stats(q, db, u)
    if data.startswith("stats_p:"):
        sec = int(data.split(":")[1])
        label = {86400: "Last 24h", 604800: "Last 7d", 2592000: "Last 30d"}.get(sec, "")
        return await _show_stats(q, db, u, sec, label)
    if data == "stats_custom":
        st.set_state(uid, st.S_STATS_CUSTOM)
        return await _edit(q, "📊 <b>Custom period</b>\n\nKitne din? Number bhejein "
                              "(masalan <code>15</code>):", back_kb("stats"))
    if data == "stats_pdf":
        if not u.get("email"):
            return await _edit(q, "❌ Pehle <b>Email Settings</b> se apna email set karein.",
                               back_kb("stats"))
        s = db.order_stats(uid)
        pdf = make_stats_pdf(db.get_setting("shop_name"), u, s, "All time",
                             db.deposit_total(uid), db.referral_count(uid))
        sent = False
        host = db.get_setting("smtp_host")
        if host:
            try:
                em = EmailMessage()
                em["Subject"] = f"{db.get_setting('shop_name')} — Your Stats"
                em["From"] = db.get_setting("smtp_from") or db.get_setting("smtp_user")
                em["To"] = u["email"]
                em.set_content("Aapki stats report attached hai.")
                em.add_attachment(pdf, maintype="application", subtype="pdf",
                                  filename="stats.pdf")
                def _send_mail():
                    with smtplib.SMTP_SSL(host, int(db.get_setting("smtp_port", "465")),
                                          timeout=20) as srv:
                        srv.login(db.get_setting("smtp_user"),
                                  db.get_setting("smtp_pass"))
                        srv.send_message(em)
                await asyncio.to_thread(_send_mail)
                sent = True
            except Exception as e:
                log.warning("smtp failed: %s", e)
        if sent:
            return await _edit(q, f"📨 Stats PDF <b>{u['email']}</b> par bhej di gayi ✅",
                               back_kb("stats"))
        await q.message.reply_document(
            InputFile(__import__("io").BytesIO(pdf), filename="stats.pdf"),
            caption="📊 Aapki Stats Report (SMTP set nahi hai, isliye yahan bheji gayi — "
                    "Admin: /admin > Settings > SMTP)")
        return await _edit(q, "📨 PDF upar document ke tor par bhej di gayi ✅",
                           back_kb("stats"))
    if data == "orders":
        orders = db.user_orders(uid, 10)
        if not orders:
            return await _edit(q, "💼 <b>My Orders</b>\n\nAbhi tak koi order nahi.",
                               back_kb("settings"))
        text = "💼 <b>My Orders</b> (last 10)\n"
        for o in orders:
            text += (f"\n🧾 <code>#{o['id']}</code> — <b>{o['product_name']}</b> × "
                     f"{o.get('qty', 1)} — ${o['price_paid']:g}\n"
                     f"📅 {o['created_at'][:16]}\n📄 <code>{o['content'][:300]}</code>\n")
        return await _edit(q, text[:4000], back_kb("settings"))
    if data == "deposits":
        deps = db.user_deposits(uid, 10)
        if not deps:
            return await _edit(q, "🪙 <b>My Deposits</b>\n\nAbhi tak koi deposit nahi.",
                               back_kb("settings"))
        smap = {"pending": "pending_review ⏳", "paid": "Credited ✅",
                "rejected": "Rejected ❌"}
        text = "🪙 <b>My Deposits</b>\n\n<b>Payment Deposits</b> 🤑\n"
        for i, d in enumerate(deps, 1):
            text += (f"\n<b>#{i}</b>\nAmount: {d['amount']:g} USDT\n"
                     f"Method: {d['method']}\nStatus: {smap.get(d['status'], d['status'])}\n"
                     f"When: {time_ago(d['created_at'])}\n")
        return await _edit(q, text[:4000], back_kb("settings"))
    if data == "lang":
        return await _edit(q, "🌐 <b>Select Language</b>", lang_kb(u))
    if data.startswith("lang:"):
        db.set_user_field(uid, "lang", data.split(":")[1][:2].upper())
        return await _show_settings(q, db, db.get_user(uid))
    if data == "notif":
        text = ("🔔 <b>Notifications</b>\n\n🔔 Tune in only the alerts you love\n\n"
                "🔔 Stock Alerts\n🔔 Info Alerts\n💵 Wallet Alerts\n📧 Email Reports")
        return await _edit(q, text, notif_kb(u))
    if data.startswith("ntog:"):
        field = data.split(":")[1]
        db.set_user_field(uid, field, 0 if u.get(field, 1) else 1)
        return await _edit(q, "🔔 <b>Notifications</b> updated — tap to toggle:",
                           notif_kb(db.get_user(uid)))
    if data == "shopview":
        kb, cur = shopview_kb(u)
        return await _edit(
            q,
            f"🛍 <b>Shop View Style</b>\n\nChoose how product buttons are shown in your "
            f"Shop.\n\n💼 10 per page = old default with Next/Prev.\n"
            f"📃 All products list = one long list with only Refresh + Back.\n\n"
            f"Current: <b>{cur}</b>", InlineKeyboardMarkup(kb))
    if data.startswith("sview:"):
        db.set_user_field(uid, "shop_view", data.split(":")[1])
        return await _show_settings(q, db, db.get_user(uid))
    if data == "grouping_toggle":
        db.set_user_field(uid, "grouping", "on" if u["grouping"] == "off" else "off")
        return await _show_settings(q, db, db.get_user(uid))
    if data == "email":
        st.set_state(uid, st.S_EMAIL)
        return await _edit(q, "✉️ Apna <b>email</b> bhejein:", back_kb("settings"))
    if data == "region":
        return await _edit(
            q,
            "🌍 <b>Set Region</b>\n\nPick your country — your local time will then be "
            "used in messages and timestamps.", region_kb(u))
    if data.startswith("regpage:"):
        return await _edit(q, "🌍 <b>Set Region</b>",
                           region_kb(u, int(data.split(":")[1])))
    if data.startswith("reg:"):
        db.set_user_field(uid, "region", data.split(":", 1)[1])
        return await _show_settings(q, db, db.get_user(uid))
    if data == "currency":
        return await _edit(
            q,
            "💱 <b>Choose Currency</b>\n\nYour product prices will show your selected "
            "currency plus USDT. Payments still use USDT.\n\n"
            f"Current: <b>{u.get('currency', 'USDT')}</b>", currency_kb(u))
    if data.startswith("curpage:"):
        return await _edit(q, "💱 <b>Choose Currency</b>",
                           currency_kb(u, int(data.split(":")[1])))
    if data.startswith("cur:"):
        db.set_user_field(uid, "currency", data.split(":")[1])
        return await _show_settings(q, db, db.get_user(uid))
    if data == "gift":
        st.set_state(uid, st.S_GIFT_REDEEM)
        return await _edit(q, "🎁 Apna <b>gift code</b> bhejein:", back_kb("settings"))
    if data == "tutorial":
        return await _edit(
            q,
            "📖 <b>Bot Tutorial</b>\n\n"
            "1️⃣ 💰 Top-up Wallet se balance add karein\n"
            "2️⃣ 🛍 Shop se product select karein\n"
            "3️⃣ Quantity chunein (− / ＋) → Buy Now\n"
            "4️⃣ 🪙 Wallet ya 💳 Pay Direct se pay karein — item <b>turant</b> deliver!\n"
            "5️⃣ 💼 My Orders mein purchases dekhein\n"
            "6️⃣ ⭐ Refer se dost bulayen, har deposit par commission payen\n"
            "7️⃣ 🎁 Gift code: Settings &gt; Gift Code\n\n"
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
    if data == "apikey":
        return await _show_api(q, db, u)
    if data == "api_regen":
        key = db.regen_api_key(uid)
        await q.answer("🔑 Nayi key ban gayi!", show_alert=True)
        await q.message.reply_text(
            f"🔑 <b>Your new API key:</b>\n<code>{key}</code>\n\n⚠️ Purani key ab kaam nahi karegi.",
            parse_mode="HTML")
        return await _show_api(q, db, db.get_user(uid))
    if data == "api_toggle":
        db.set_user_field(uid, "api_disabled", 0 if u.get("api_disabled") else 1)
        return await _show_api(q, db, db.get_user(uid))
    if data == "api_docs":
        return await _edit(
            q,
            "🧾 <b>API Documentation</b>\n\n"
            "<b>Authentication</b>\nSend your key in one of these ways:\n"
            "<code>Authorization: Bearer YOUR_KEY</code>\n"
            "<code>x-api-key: YOUR_KEY</code>\n"
            "<code>?api_key=YOUR_KEY</code>\n\n"
            f"💼 <b>Product List</b>\nGET <code>http://YOUR_SERVER_IP:{API_PORT}"
            "/api/products</code>\n\n"
            f"🪙 <b>Balance</b>\nGET <code>http://YOUR_SERVER_IP:{API_PORT}"
            "/api/balance</code>\n\n"
            f"🛒 <b>Place Order</b>\nPOST <code>http://YOUR_SERVER_IP:{API_PORT}"
            "/api/order</code>\n\nJSON body:\n"
            '<code>{ "product_id": 123, "quantity": 1, "request_id": "my-order-001" }</code>\n\n'
            "The API returns delivered items in JSON. Wallet balance is deducted only "
            "when the order is completed. Same <code>request_id</code> dobara charge "
            "nahi hota (idempotent).",
            back_kb("apikey"))

    # ---------- misc ----------
    if data == "support":
        sup = db.get_setting("support")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{sup.lstrip('@')}")],
            [InlineKeyboardButton("◀ Back", callback_data="home")]])
        return await _edit(q, f"🆘 <b>Support</b>\n\nKisi bhi masle ke liye rabta karein:\n👉 {sup}",
                           kb)
    if data == "refer":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{uid}"
        pct = db.get_setting("ref_percent", "5")
        cnt = db.referral_count(uid)
        return await _edit(
            q,
            f"⭐ <b>Refer &amp; Earn</b>\n\n🔗 Aapka link:\n<code>{link}</code>\n\n"
            f"👥 Referrals: <b>{cnt}</b>\n🎁 Commission: <b>{pct}%</b> har deposit par\n"
            f"💰 Total earned: <b>${u['ref_earnings']:g}</b>", back_kb())


# ---------------------------------------------------------------- messages
async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    u, _ = db.ensure_user(update.effective_user)
    if u.get("banned"):
        return
    uid = u["user_id"]
    text = update.message.text.strip()
    state, data = st.get_state(uid)

    if state == st.S_GIFT_REDEEM:
        st.clear(uid)
        ok, res = db.redeem_gift(text, uid)
        if ok:
            nb = db.get_user(uid)["balance"]
            return await update.message.reply_text(
                f"🎁 <b>Gift code redeem!</b>\n\n💰 +{res:g} USDT\n💳 Balance: ${nb:g}",
                parse_mode="HTML")
        return await update.message.reply_text(res)

    if state == st.S_EMAIL:
        if "@" not in text or "." not in text or len(text) > 100:
            return await update.message.reply_text("❌ Sahi email bhejein:")
        db.set_user_field(uid, "email", text)
        st.clear(uid)
        return await update.message.reply_text(f"✅ Email set: <code>{text}</code>",
                                               parse_mode="HTML")

    if state == st.S_QTY_CUSTOM:
        try:
            qty = int(text)
            if qty < 1:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein (1 ya zyada):")
        st.clear(uid)
        p = db.get_product(data["pid"])
        if not p:
            return await update.message.reply_text("❌ Product nahi mila.")
        qty = min(qty, max(p["stock_count"], 1))
        price, _ = price_of(p)
        total = round(price * qty, 6)
        await update.message.reply_text(
            f"💼 <b>Order summary</b>\n\n{p['emoji']} <b>{p['name']}</b>\n"
            f"🔢 Qty: {qty}\n✏️ Total: <b>{total:g}USDT</b>\n"
            f"🪙 Wallet: {u['balance']:g}USDT\nChoose a pay method:",
            parse_mode="HTML",
            reply_markup=order_summary_kb(p["id"], qty, float(u["balance"]), total))
        return

    if state == st.S_STATS_CUSTOM:
        try:
            days = int(text)
            if not 1 <= days <= 3650:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("❌ 1–3650 ke darmiyan number bhejein:")
        st.clear(uid)
        s = db.stats_period(uid, days * 86400)
        return await update.message.reply_text(
            f"📊 <b>Your Stats</b> — <i>Last {days}d</i>\n\n"
            f"🛍 Orders: {s['orders']}\n🎁 Items Bought: {s['items']}\n"
            f"💵 Total Spent: {s['spent']:g} USDT\n⬇️ Deposits: {s['deposits']:g} USDT",
            parse_mode="HTML", reply_markup=stats_kb())

    if state == st.S_DEP_AMOUNT:
        try:
            amt = float(text.replace("$", ""))
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein, masalan <code>10</code>:",
                                                   parse_mode="HTML")
        min_dep = float(db.get_setting("min_deposit", "1"))
        if amt < min_dep:
            return await update.message.reply_text(f"❌ Minimum deposit ${min_dep:g} hai:")
        st.set_state(uid, st.S_DEP_PROOF, method=data["method"], amount=amt)
        return await update.message.reply_text(
            f"💵 Amount: <b>{amt:g} USDT</b>\n\nPlease send your <b>Order ID</b> below:",
            parse_mode="HTML")

    if state == st.S_DEP_PROOF:
        did = db.create_deposit(uid, data["amount"], data["method"], tx_info=text[:300])
        st.clear(uid)
        await update.message.reply_text(
            f"✅ <b>Deposit request submit!</b>\n\n🧾 ID: <code>#{did}</code>\n"
            f"💵 Amount: {data['amount']:g} USDT\n"
            f"⏳ Status: pending_review — approve hote hi balance add hoga.",
            parse_mode="HTML")
        await notify_admins(
            context.bot,
            f"💰 <b>New Deposit Request #{did}</b>\n\n👤 {_user_brief(u)}\n"
            f"💵 Amount: <b>{data['amount']:g} USDT</b>\n🏦 Method: {data['method']}\n"
            f"🧾 Order ID: <code>{text[:200]}</code>",
            admin_deposit_kb(did))
        return

    if state == st.S_DIRPROOF:
        did = db.create_deposit(uid, data["amount"], data["method"], tx_info=text[:300],
                                kind="direct", meta=f"{data['pid']}:{data['qty']}")
        st.clear(uid)
        await update.message.reply_text(
            f"✅ <b>Order payment submit!</b>\n\n🧾 ID: <code>#{did}</code>\n"
            f"💵 Amount: {data['amount']:g} USDT\n"
            f"⏳ Admin verify karte hi aapka item deliver ho jayega.",
            parse_mode="HTML")
        p = db.get_product(data["pid"])
        await notify_admins(
            context.bot,
            f"🛒💳 <b>Direct Order Payment #{did}</b>\n\n👤 {_user_brief(u)}\n"
            f"📦 {p['name'] if p else data['pid']} × {data['qty']}\n"
            f"💵 Amount: <b>{data['amount']:g} USDT</b>\n🏦 Method: {data['method']}\n"
            f"🧾 Order ID: <code>{text[:200]}</code>\n\n"
            f"✅ Approve = item auto-deliver (wallet top-up nahi hoga)",
            admin_deposit_kb(did))
        return

    if state == st.S_CRYPTO_CUSTOM:
        st.clear(uid)
        try:
            amt = float(text.replace("$", ""))
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein:")
        async def send_m(t, kb=None):
            await update.message.reply_text(t, parse_mode="HTML", reply_markup=kb)
        return await _crypto_invoice_reply(send_m, context, uid, amt)

    if text.upper().startswith("GIFT-"):
        ok, res = db.redeem_gift(text, uid)
        if ok:
            nb = db.get_user(uid)["balance"]
            return await update.message.reply_text(
                f"🎁 <b>Gift code redeem!</b>\n\n💰 +{res:g} USDT\n💳 Balance: ${nb:g}",
                parse_mode="HTML")
        return await update.message.reply_text(res)
