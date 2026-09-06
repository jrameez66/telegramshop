"""Entry point — bot + admin panel + reseller API + crypto checker."""
import asyncio
import logging

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
    """Har 60s pending CryptoBot invoices check karo — paid ho to balance credit."""
    crypto = context.bot_data["crypto"]
    db = context.bot_data["db"]
    for dep in db.pending_crypto():
        try:
            if await crypto.is_paid(dep["invoice_id"]):
                db.set_deposit_status(dep["id"], "paid")
                db.add_balance(dep["user_id"], dep["amount"])
                await context.bot.send_message(
                    dep["user_id"],
                    f"✅ <b>Deposit confirmed!</b>\n\n"
                    f"💰 +{dep['amount']:g} USDT aapke wallet mein add ho gaya.\n"
                    f"💳 Naya balance: <b>${db.get_user(dep['user_id'])['balance']:g}</b>",
                    parse_mode="HTML")
                await handlers_user.notify_admins(
                    context.bot,
                    f"💰 <b>Auto deposit (CryptoBot)</b>\nUser: <code>{dep['user_id']}</code>\n"
                    f"Amount: <b>{dep['amount']:g} USDT</b> — auto-credited ✔")
        except Exception as e:
            log.error("crypto checker: %s", e)


def main():
    db = DB(config.DB_PATH)
    crypto = CryptoPay(config.CRYPTOBOT_TOKEN)

    app = Application.builder().token(config.BOT_TOKEN).build()
    app.bot_data["db"] = db
    app.bot_data["crypto"] = crypto

    # ---------- user ----------
    app.add_handler(CommandHandler("start", handlers_user.start))
    app.add_handler(CallbackQueryHandler(handlers_user.user_callback,
                                         pattern=r"^(?!adm:)"))
    # ---------- admin ----------
    app.add_handler(CommandHandler("admin", handlers_admin.admin_panel))
    app.add_handler(CallbackQueryHandler(handlers_admin.admin_callback, pattern=r"^adm:"))
    # ---------- messages (admin flows pehle, phir user flows) ----------
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   handlers_admin.admin_message), group=0)
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
