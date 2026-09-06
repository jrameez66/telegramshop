"""Entry point v2 — bot + admin panel + reseller API + crypto checker + bot commands."""
import logging

from telegram import BotCommand
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

import config
import handlers_admin
import handlers_user
from api_server import start_api_server
from cryptobot import CryptoPay
from db import DB

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def crypto_checker(context):
    """Har 60s pending CryptoBot invoices check — paid ho to credit/deliver."""
    crypto = context.bot_data["crypto"]
    db = context.bot_data["db"]
    for dep in db.pending_crypto():
        try:
            if await crypto.is_paid(dep["invoice_id"]):
                await handlers_admin._credit_deposit(context, db, dep)
                await handlers_user.notify_admins(
                    context.bot,
                    f"💰 <b>Auto deposit (CryptoBot)</b>\nUser: <code>{dep['user_id']}</code>\n"
                    f"Amount: <b>{dep['amount']:g} USDT</b> — auto-processed ✔")
        except Exception as e:
            log.error("crypto checker: %s", e)


async def post_init(app):
    """Menu button (☰) ke commands set karo."""
    await app.bot.set_my_commands([
        BotCommand("start", "Open the main menu"),
        BotCommand("products", "Browse products"),
        BotCommand("deposit", "Add funds to your wallet"),
        BotCommand("settings", "Your profile & settings"),
        BotCommand("support", "Get help"),
        BotCommand("api", "Reseller API access"),
        BotCommand("admin", "Admin panel (admins only)"),
    ])


async def cmd_settings(update, context):
    db = context.bot_data["db"]
    u, _ = db.ensure_user(update.effective_user)
    joined = (u["joined_at"] or "")[:10]
    from keyboards import settings_kb
    await update.message.reply_text(
        f"👤 <b>User Profile</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"✈️ First Name: {u['first_name']}\n"
        f"⚙️ Username: @{u['username'] or '—'}\n"
        f"✉️ Email: {u['email'] or 'not set'}\n"
        f"🪙 Balance: <b>{u['balance']:g} USDT</b>\n"
        f"💵 Currency: {u.get('currency', 'USDT')}\n"
        f"🌐 Language: {u['lang']} | 🌍 Region: {u['region'] or 'not set'}\n"
        f"🗓 Joined: {joined}",
        parse_mode="HTML", reply_markup=settings_kb(u))


async def cmd_api(update, context):
    db = context.bot_data["db"]
    u, _ = db.ensure_user(update.effective_user)
    from handlers_user import _show_api

    class FakeQ:
        message = update.message

        async def answer(self, *a, **k):
            pass

    async def fake_edit(text, kb=None):
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb,
                                        disable_web_page_preview=True)
    import handlers_user as hu
    orig = hu._edit
    hu._edit = lambda q, t, kb=None: fake_edit(t, kb)
    try:
        await _show_api(FakeQ(), db, u)
    finally:
        hu._edit = orig


def main():
    db = DB(config.DB_PATH)
    crypto = CryptoPay(config.CRYPTOBOT_TOKEN)

    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()
    app.bot_data["db"] = db
    app.bot_data["crypto"] = crypto

    # ---------- user ----------
    app.add_handler(CommandHandler("start", handlers_user.start))
    app.add_handler(CommandHandler("products", handlers_user.cmd_products))
    app.add_handler(CommandHandler("deposit", handlers_user.cmd_deposit))
    app.add_handler(CommandHandler("support", handlers_user.cmd_support))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("api", cmd_api))
    app.add_handler(CallbackQueryHandler(handlers_user.user_callback, pattern=r"^(?!adm:)"))
    # ---------- admin ----------
    app.add_handler(CommandHandler("admin", handlers_admin.admin_panel))
    app.add_handler(CallbackQueryHandler(handlers_admin.admin_callback, pattern=r"^adm:"))
    # ---------- messages ----------
    app.add_handler(MessageHandler(~filters.COMMAND, handlers_admin.admin_message), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   handlers_user.user_message), group=1)

    # ---------- background jobs ----------
    if crypto.enabled:
        app.job_queue.run_repeating(crypto_checker, interval=60, first=20)
        log.info("CryptoBot auto-verification: ON")
    else:
        log.info("CryptoBot token nahi hai — manual deposits (admin approve) mode ON")

    # ---------- reseller API ----------
    try:
        start_api_server(db, config.API_PORT)
    except OSError as e:
        log.warning("API server start nahi hua (port %s): %s", config.API_PORT, e)

    log.info("🚀 Bot started!")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
