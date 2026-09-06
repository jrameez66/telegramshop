"""Admin panel v2 — /admin + management flows (desc/note/warranty/hold, rates, SMTP,
direct-order approval = auto-delivery)."""
import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

import states as st
from config import ADMIN_IDS
from db import price_of
from keyboards import (admin_kb, admin_product_manage_kb, admin_products_kb,
                       admin_rates_kb, admin_settings_kb, admin_smtp_kb, back_kb)

log = logging.getLogger(__name__)
PAGE = 10


def is_admin(uid):
    return uid in ADMIN_IDS


async def _edit(q, text, kb=None):
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        try:
            await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            log.warning("admin edit: %s", e)


def _parse_target(db, t):
    t = t.strip()
    if t.lstrip("-").isdigit():
        return db.get_user(int(t))
    return db.get_user_by_username(t)


def _parse_target_amount(db, text):
    parts = text.split()
    if len(parts) != 2:
        return None, None
    u = _parse_target(db, parts[0])
    try:
        amt = float(parts[1])
    except ValueError:
        return None, None
    if not u or amt <= 0:
        return None, None
    return u, amt


async def _show_prod(q, db, pid):
    p = db.get_product(pid)
    if not p:
        return await _edit(q, "❌ Product nahi mila.", back_kb("adm:products:0"))
    price, on_sale = price_of(p)
    sale_line = (f"\n🔥 Sale: <b>{p['sale_price']:g} USDT</b> (till {p['sale_end'][:16]} UTC)"
                 if on_sale else "")
    text = (f"📦 <b>#{p['id']} {p['name']}</b>\n\n"
            f"💵 Price: ${price:g}{sale_line}\n"
            f"📊 Stock: <b>{p['stock_count']}</b>\n"
            f"🛡 Warranty: {p.get('warranty') or 'NON'} | ⏳ Hold: {p.get('hold') or '—'}\n"
            f"📝 Desc: {'✅' if p.get('description') else '❌'} | "
            f"🗒 Note: {'✅' if p.get('note') else '❌'}\n"
            f"🔘 Status: {'🟢 Active' if p['active'] else '🔴 Disabled'}")
    await _edit(q, text, admin_product_manage_kb(p))


async def _credit_deposit(context, db, dep):
    """Deposit approve: referral commission + user ko message. Direct order ho to delivery."""
    db.set_deposit_status(dep["id"], "paid")
    uid2 = dep["user_id"]
    if dep.get("kind") == "direct":
        # direct order payment — wallet mein nahi, item deliver hoga
        try:
            pid_s, qty_s = (dep.get("meta") or "0:1").split(":")
            res = db.purchase_multi(uid2, int(pid_s), int(qty_s), source="direct",
                                    skip_balance=True)
            if res["ok"]:
                items = "\n".join(f"<code>{i}</code>" for i in res["items"])
                await context.bot.send_message(
                    uid2,
                    f"✅ <b>Payment verified — Order delivered!</b>\n\n"
                    f"📦 {res['product']} × {res['qty']}\n"
                    f"🧾 Order ID: <code>#{res['order_id']}</code>\n\n"
                    f"📄 <b>Your item(s):</b>\n{items}",
                    parse_mode="HTML")
                return True
            await context.bot.send_message(
                uid2, "⚠️ Payment received lekin stock khatam ho gaya — "
                      "amount aapke wallet mein add kar diya gaya hai.")
        except Exception as e:
            log.error("direct deliver: %s", e)
    db.add_balance(uid2, dep["amount"])
    u2 = db.get_user(uid2)
    if u2 and u2.get("referrer_id"):
        try:
            pct = float(db.get_setting("ref_percent", "5") or 0)
        except ValueError:
            pct = 0
        bonus = round(dep["amount"] * pct / 100, 6)
        if bonus > 0:
            db.add_balance(u2["referrer_id"], bonus)
            db.add_ref_earnings(u2["referrer_id"], bonus)
            try:
                await context.bot.send_message(
                    u2["referrer_id"],
                    f"⭐ <b>Referral commission!</b>\n\nAapke referral ne "
                    f"${dep['amount']:g} deposit kiya.\n🎁 Aapko <b>${bonus:g}</b> "
                    f"({pct:g}%) mile!", parse_mode="HTML")
            except Exception:
                pass
    try:
        await context.bot.send_message(
            uid2,
            f"✅ <b>Deposit approved!</b>\n\n💰 +{dep['amount']:g} USDT\n"
            f"💳 New balance: <b>${u2['balance']:g}</b>", parse_mode="HTML")
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- /admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("🛠 <b>Admin Panel</b>", parse_mode="HTML",
                                    reply_markup=admin_kb())


# ---------------------------------------------------------------- callbacks
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer()
        return
    await q.answer()
    db = context.bot_data["db"]
    uid = q.from_user.id
    parts = (q.data or "").split(":")
    a = parts[1] if len(parts) > 1 else ""

    if a == "home":
        st.clear(uid)
        return await _edit(q, "🛠 <b>Admin Panel</b>", admin_kb())
    if a == "close":
        try:
            await q.message.delete()
        except Exception:
            pass
        return

    if a == "dash":
        s = db.stats()
        return await _edit(
            q,
            f"📊 <b>Dashboard</b>\n\n"
            f"👥 Total users: <b>{s['users']}</b>\n"
            f"🛒 Total orders: <b>{s['orders']}</b>\n"
            f"💰 Total revenue: <b>${s['revenue']:g}</b>\n"
            f"📅 Today revenue: <b>${s['today']:g}</b>\n"
            f"⏳ Pending deposits: <b>{s['pending']}</b>\n"
            f"📦 Stock items: <b>{s['stock']}</b>", back_kb("adm:home"))

    # ---------- products ----------
    if a == "products":
        page = max(0, int(parts[2]))
        total = db.count_products(active_only=False)
        pages = max(1, (total + PAGE - 1) // PAGE)
        page = min(page, pages - 1)
        prods = db.list_products(page * PAGE, PAGE, active_only=False)
        return await _edit(q, "📦 <b>Products</b> — manage karne ke liye select karein:",
                           admin_products_kb(prods, page, pages))
    if a == "prod":
        return await _show_prod(q, db, int(parts[2]))
    if a == "addprod":
        st.set_state(uid, st.S_ADDPROD_NAME)
        return await _edit(q, "➕ <b>Add Product</b>\n\nStep 1/3: Product ka <b>naam</b> bhejein\n"
                              "(masalan: <code>Gemini Pro 18M Links</code>)",
                           back_kb("adm:home"))
    if a == "addstock_pick":
        page = max(0, int(parts[2]))
        total = db.count_products(active_only=False)
        pages = max(1, (total + PAGE - 1) // PAGE)
        page = min(page, pages - 1)
        prods = db.list_products(page * PAGE, PAGE, active_only=False)
        kb = [[InlineKeyboardButton(
            f"{p['emoji']} #{p['id']} {p['name']} (Stock: {p['stock_count']})",
            callback_data=f"adm:addstock:{p['id']}")] for p in prods]
        kb.append([InlineKeyboardButton("◀ Prev", callback_data=f"adm:addstock_pick:{page - 1}"),
                   InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"),
                   InlineKeyboardButton("Next ▶", callback_data=f"adm:addstock_pick:{page + 1}")])
        kb.append([InlineKeyboardButton("◀ Back", callback_data="adm:home")])
        return await _edit(q, "➕ Kis product mein stock add karna hai?", InlineKeyboardMarkup(kb))
    if a == "addstock":
        st.set_state(uid, st.S_ADDSTOCK, pid=int(parts[2]))
        return await _edit(q, "➕ <b>Add Stock</b>\n\nHar line mein 1 item bhejein:\n\n"
                              "<code>user1:pass1\nuser2:pass2</code>", back_kb("adm:home"))
    if a == "rename":
        st.set_state(uid, st.S_RENAME, pid=int(parts[2]))
        return await _edit(q, "✏️ Naya naam bhejein:", back_kb(f"adm:prod:{parts[2]}"))
    if a == "price":
        st.set_state(uid, st.S_PRICE, pid=int(parts[2]))
        return await _edit(q, "💲 Nayi price bhejein (masalan <code>4.5</code>):",
                           back_kb(f"adm:prod:{parts[2]}"))
    if a == "desc":
        st.set_state(uid, st.S_DESC, pid=int(parts[2]))
        return await _edit(q, "📝 Product ki <b>Description</b> bhejein (View Note mein dikhegi):",
                           back_kb(f"adm:prod:{parts[2]}"))
    if a == "note":
        st.set_state(uid, st.S_NOTE, pid=int(parts[2]))
        return await _edit(q, "🗒 Product ka <b>Note</b> bhejein (warranty terms waghera):",
                           back_kb(f"adm:prod:{parts[2]}"))
    if a == "warranty":
        st.set_state(uid, st.S_WARRANTY, pid=int(parts[2]))
        return await _edit(q, "🛡 Warranty bhejein (masalan <code>NON</code>, <code>2MW</code>):",
                           back_kb(f"adm:prod:{parts[2]}"))
    if a == "hold":
        st.set_state(uid, st.S_HOLD, pid=int(parts[2]))
        return await _edit(q, "⏳ Hold text bhejein (masalan <code>HOLD WARRANTY 24HOURS</code>) "
                              "— hatane ke liye <code>off</code>:",
                           back_kb(f"adm:prod:{parts[2]}"))
    if a == "sale":
        st.set_state(uid, st.S_SALE, pid=int(parts[2]))
        return await _edit(q, "🔥 <b>Flash Sale</b>\n\nFormat: <code>sale_price hours</code>\n"
                              "Masalan: <code>0.80 24</code>\n\nSale hatane ke liye: <code>off</code>",
                           back_kb(f"adm:prod:{parts[2]}"))
    if a == "toggle":
        p = db.get_product(int(parts[2]))
        if p:
            db.update_product(p["id"], active=0 if p["active"] else 1)
            return await _show_prod(q, db, p["id"])
        return await _edit(q, "❌ Product nahi mila.", back_kb("adm:products:0"))
    if a == "del":
        db.delete_product(int(parts[2]))
        return await _edit(q, "🗑 Product (aur uska stock) delete ho gaya.",
                           back_kb("adm:products:0"))

    # ---------- deposits ----------
    if a == "deposits":
        deps = db.pending_deposits()
        if not deps:
            return await _edit(q, "💰 <b>Pending Deposits</b>\n\n✅ Koi pending deposit nahi.",
                               back_kb("adm:home"))
        text = "💰 <b>Pending Deposits</b>\n\n"
        kb = []
        for d in deps[:12]:
            kind = "🛒 direct order" if d.get("kind") == "direct" else "💰 topup"
            text += (f"#{d['id']} ({kind}) — <b>${d['amount']:g}</b> via {d['method']}\n"
                     f"👤 {d['first_name'] or ''} @{d['username'] or '-'} "
                     f"(<code>{d['user_id']}</code>)\n🧾 {d['tx_info'][:60] or 'cryptobot invoice'}\n\n")
            kb.append([InlineKeyboardButton(f"✅ #{d['id']}", callback_data=f"adm:dep_ok:{d['id']}"),
                       InlineKeyboardButton(f"❌ #{d['id']}", callback_data=f"adm:dep_no:{d['id']}")])
        kb.append([InlineKeyboardButton("◀ Back", callback_data="adm:home")])
        return await _edit(q, text[:4000], InlineKeyboardMarkup(kb))
    if a == "dep_ok":
        did = int(parts[2])
        d = db.get_deposit(did)
        if not d or d["status"] != "pending":
            return await _edit(q, "⚠️ Ye deposit pehle hi process ho chuki.",
                               back_kb("adm:deposits"))
        await _credit_deposit(context, db, d)
        note = " (direct order — item delivered)" if d.get("kind") == "direct" else ""
        return await _edit(q, f"✅ Deposit #{did} approved — ${d['amount']:g}{note}.",
                           back_kb("adm:deposits"))
    if a == "dep_no":
        did = int(parts[2])
        d = db.get_deposit(did)
        if not d or d["status"] != "pending":
            return await _edit(q, "⚠️ Ye deposit pehle hi process ho chuki.",
                               back_kb("adm:deposits"))
        db.set_deposit_status(did, "rejected")
        try:
            await context.bot.send_message(
                d["user_id"], f"❌ Aapki deposit #{did} reject ho gayi. "
                              f"Masla ho to support se rabta karein.")
        except Exception:
            pass
        return await _edit(q, f"❌ Deposit #{did} rejected.", back_kb("adm:deposits"))

    # ---------- users ----------
    if a == "users":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Balance", callback_data="adm:users_add"),
             InlineKeyboardButton("➖ Remove Balance", callback_data="adm:users_sub")],
            [InlineKeyboardButton("🚫 Ban User", callback_data="adm:users_ban"),
             InlineKeyboardButton("✅ Unban User", callback_data="adm:users_unban")],
            [InlineKeyboardButton("🔍 Find User", callback_data="adm:users_find")],
            [InlineKeyboardButton("◀ Back", callback_data="adm:home")]])
        return await _edit(q, f"👥 <b>Users</b> — total: <b>{db.count_users()}</b>", kb)
    if a == "users_add":
        st.set_state(uid, st.S_ADDBAL)
        return await _edit(q, "➕ Format: <code>user_id amount</code>\n(@username bhi chalega)",
                           back_kb("adm:users"))
    if a == "users_sub":
        st.set_state(uid, st.S_SUBBAL)
        return await _edit(q, "➖ Format: <code>user_id amount</code>", back_kb("adm:users"))
    if a == "users_ban":
        st.set_state(uid, st.S_BAN)
        return await _edit(q, "🚫 User ki ID ya @username bhejein:", back_kb("adm:users"))
    if a == "users_unban":
        st.set_state(uid, st.S_UNBAN)
        return await _edit(q, "✅ User ki ID ya @username bhejein:", back_kb("adm:users"))
    if a == "users_find":
        st.set_state(uid, st.S_LOOKUP)
        return await _edit(q, "🔍 User ki ID ya @username bhejein:", back_kb("adm:users"))

    # ---------- gifts / broadcast / settings ----------
    if a == "gift":
        gifts = db.list_gifts()
        text = "🎁 <b>Gift Codes</b>\n\n"
        if gifts:
            text += "\n".join(f"<code>{g['code']}</code> — ${g['amount']:g} "
                              f"({g['used_count']}/{g['max_uses']} used)" for g in gifts)
        else:
            text += "Abhi koi code nahi."
        text += ("\n\n➕ Naya code banane ke liye abhi bhejein:\n"
                 "<code>amount max_uses</code> — masalan <code>2 10</code>")
        st.set_state(uid, st.S_GIFT)
        return await _edit(q, text, back_kb("adm:home"))
    if a == "broadcast":
        st.set_state(uid, st.S_BROADCAST)
        return await _edit(q, "📣 <b>Broadcast</b>\n\nJo message ab bhejein ge (text / photo) wo "
                              "<b>tamam users</b> ko chala jayega.\n\nCancel: ◀ Back",
                           back_kb("adm:home"))
    if a == "settings":
        return await _edit(q, "⚙️ <b>Settings</b> — change karne ke liye item select karein:",
                           admin_settings_kb(db))
    if a == "rates":
        return await _edit(q, "💱 <b>Currency Rates</b> — 1 USDT = X (tap to edit):",
                           admin_rates_kb(db, int(parts[2])))
    if a == "smtp":
        return await _edit(q, "📧 <b>SMTP Settings</b> — Stats PDF email ke liye "
                              "(Gmail: host=smtp.gmail.com, port=465, pass=App Password):",
                           admin_smtp_kb())
    if a == "set":
        key = ":".join(parts[2:])
        st.set_state(uid, st.S_SET, key=key)
        cur = db.get_setting(key)
        return await _edit(q, f"⚙️ <b>{key}</b>\n\nCurrent: <code>{cur or 'not set'}</code>\n\n"
                              f"Nayi value bhejein:", back_kb("adm:settings"))


# ---------------------------------------------------------------- messages
async def admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    state, data = st.get_state(uid)
    if not state:
        return
    db = context.bot_data["db"]
    text = (update.message.text or "").strip()
    handled = True

    if state == st.S_ADDPROD_NAME:
        st.set_state(uid, st.S_ADDPROD_PRICE, name=text)
        await update.message.reply_text("Step 2/3: <b>Price</b> bhejein (USDT, masalan "
                                        "<code>4.5</code>):", parse_mode="HTML")
    elif state == st.S_ADDPROD_PRICE:
        try:
            price = float(text)
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein, masalan 4.5")
        st.set_state(uid, st.S_ADDPROD_STOCK, name=data["name"], price=price)
        await update.message.reply_text("Step 3/3: <b>Stock items</b> bhejein — har line mein 1.\n"
                                        "Baad mein add karne ke liye <code>skip</code> likhein.",
                                        parse_mode="HTML")
    elif state == st.S_ADDPROD_STOCK:
        pid = db.add_product(data["name"], data["price"])
        n = 0
        if text.lower() != "skip":
            items = [l.strip() for l in text.splitlines() if l.strip()]
            n = db.add_stock(pid, items)
        st.clear(uid)
        await update.message.reply_text(
            f"✅ Product <b>#{pid} {data['name']}</b> add ho gaya!\n"
            f"💵 ${data['price']:g} — 📦 {n} stock items\n\n"
            f"ℹ️ Description/Note/Warranty: Products &gt; product select karein",
            parse_mode="HTML", reply_markup=back_kb(f"adm:prod:{pid}"))
    elif state == st.S_ADDSTOCK:
        items = [l.strip() for l in text.splitlines() if l.strip()]
        if not items:
            return await update.message.reply_text("❌ Kam az kam 1 item bhejein.")
        n = db.add_stock(data["pid"], items)
        st.clear(uid)
        p = db.get_product(data["pid"])
        await update.message.reply_text(
            f"✅ {n} items add hue! <b>{p['name']}</b> ka total stock: {p['stock_count']}",
            parse_mode="HTML", reply_markup=back_kb(f"adm:prod:{p['id']}"))
    elif state == st.S_PRICE:
        try:
            price = float(text)
        except ValueError:
            return await update.message.reply_text("❌ Number bhejein, masalan 4.5")
        db.update_product(data["pid"], price=price)
        st.clear(uid)
        await update.message.reply_text(f"✅ Price update: ${price:g}",
                                        reply_markup=back_kb(f"adm:prod:{data['pid']}"))
    elif state == st.S_RENAME:
        db.update_product(data["pid"], name=text)
        st.clear(uid)
        await update.message.reply_text("✅ Naam update ho gaya.",
                                        reply_markup=back_kb(f"adm:prod:{data['pid']}"))
    elif state in (st.S_DESC, st.S_NOTE, st.S_WARRANTY, st.S_HOLD):
        field = {st.S_DESC: "description", st.S_NOTE: "note",
                 st.S_WARRANTY: "warranty", st.S_HOLD: "hold"}[state]
        if text.lower() == "off" and field in ("hold", "description", "note"):
            text = ""
        db.update_product(data["pid"], **{field: text[:1000]})
        st.clear(uid)
        await update.message.reply_text(f"✅ {field} update ho gaya.",
                                        reply_markup=back_kb(f"adm:prod:{data['pid']}"))
    elif state == st.S_SALE:
        pid = data["pid"]
        if text.lower() == "off":
            db.update_product(pid, sale_price=None, sale_end=None)
            st.clear(uid)
            await update.message.reply_text("✅ Sale khatam kar di gayi.",
                                            reply_markup=back_kb(f"adm:prod:{pid}"))
            raise ApplicationHandlerStop
        sp_parts = text.split()
        try:
            sp = float(sp_parts[0])
            hours = float(sp_parts[1])
        except (ValueError, IndexError):
            return await update.message.reply_text(
                "❌ Format: <code>sale_price hours</code> — masalan <code>0.8 24</code>",
                parse_mode="HTML")
        db.set_sale(pid, sp, hours)
        p = db.get_product(pid)
        msg = (f"🛍 <b>FLASH SALE — LIMITED TIME!</b>\n\n"
               f"{p['emoji']} <b>{p['name']}</b>\n"
               f"💵 Was: <s>{p['price']:g} USDT</s>\n"
               f"⚡️ Now: <b>{sp:g} USDT</b>\n\n"
               f"🏃 Hurry — Flash Sale Ending In {hours:g} Hours !")
        sent = 0
        for u2 in db.all_user_ids(notif_field="n_stock"):
            try:
                await context.bot.send_message(u2, msg, parse_mode="HTML")
                sent += 1
            except Exception:
                pass
            await asyncio.sleep(0.05)
        st.clear(uid)
        await update.message.reply_text(f"🔥 Flash sale set! {sent} users ko notification gayi.",
                                        reply_markup=back_kb(f"adm:prod:{pid}"))
    elif state == st.S_GIFT:
        gp = text.split()
        try:
            amt = float(gp[0])
            uses = int(gp[1]) if len(gp) > 1 else 1
        except ValueError:
            return await update.message.reply_text(
                "❌ Format: <code>amount max_uses</code> — masalan <code>2 10</code>",
                parse_mode="HTML")
        code = db.create_gift(amt, uses)
        st.clear(uid)
        await update.message.reply_text(
            f"🎁 Gift code ban gaya!\n\n<code>{code}</code>\n💵 ${amt:g} — {uses} use(s)",
            parse_mode="HTML")
    elif state == st.S_BROADCAST:
        ids = db.all_user_ids()
        ok = fail = 0
        m = await update.message.reply_text(f"📣 Broadcasting to {len(ids)} users...")
        for u2 in ids:
            try:
                await context.bot.copy_message(u2, update.effective_chat.id,
                                               update.message.message_id)
                ok += 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
        st.clear(uid)
        await m.edit_text(f"📣 Broadcast complete!\n✅ {ok} delivered — ❌ {fail} failed")
    elif state == st.S_SET:
        db.set_setting(data["key"], text)
        st.clear(uid)
        await update.message.reply_text(f"✅ <b>{data['key']}</b> update ho gaya.",
                                        parse_mode="HTML", reply_markup=back_kb("adm:settings"))
    elif state in (st.S_ADDBAL, st.S_SUBBAL):
        u2, amt = _parse_target_amount(db, text)
        if not u2:
            return await update.message.reply_text(
                "❌ Format: <code>user_id amount</code> (user nahi mila?)", parse_mode="HTML")
        delta = amt if state == st.S_ADDBAL else -amt
        db.add_balance(u2["user_id"], delta)
        st.clear(uid)
        if delta > 0:
            try:
                await context.bot.send_message(
                    u2["user_id"],
                    f"💰 Admin ne aapke wallet mein <b>${amt:g}</b> add kiye!\n"
                    f"💳 Balance: ${db.get_user(u2['user_id'])['balance']:g}",
                    parse_mode="HTML")
            except Exception:
                pass
        await update.message.reply_text(
            f"✅ {u2['first_name']} (<code>{u2['user_id']}</code>) — "
            f"new balance: ${db.get_user(u2['user_id'])['balance']:g}", parse_mode="HTML")
    elif state in (st.S_BAN, st.S_UNBAN):
        target = _parse_target(db, text)
        if not target:
            return await update.message.reply_text("❌ User nahi mila. ID ya @username bhejein.")
        db.set_user_field(target["user_id"], "banned", 1 if state == st.S_BAN else 0)
        st.clear(uid)
        await update.message.reply_text(
            f"{'🚫 Ban' if state == st.S_BAN else '✅ Unban'} ho gaya: "
            f"{target['first_name']} (<code>{target['user_id']}</code>)", parse_mode="HTML")
    elif state == st.S_LOOKUP:
        target = _parse_target(db, text)
        if not target:
            return await update.message.reply_text("❌ User nahi mila.")
        o = db.order_stats(target["user_id"])
        st.clear(uid)
        await update.message.reply_text(
            f"👤 <b>User Profile</b>\n\n"
            f"🆔 <code>{target['user_id']}</code>\n"
            f"✈️ {target['first_name']} @{target['username'] or '-'}\n"
            f"💰 Balance: ${target['balance']:g}\n"
            f"🛒 Orders: {o['orders']} (items {o['items']}, ${o['spent']:g})\n"
            f"⬇️ Deposits: ${db.deposit_total(target['user_id']):g}\n"
            f"⭐ Referrals: {db.referral_count(target['user_id'])}\n"
            f"🗓 Joined: {(target['joined_at'] or '')[:10]}\n"
            f"🔘 {'🚫 Banned' if target['banned'] else '✅ Active'}", parse_mode="HTML")
    else:
        handled = False

    if handled:
        raise ApplicationHandlerStop
