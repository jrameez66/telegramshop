import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN", "").strip()
API_PORT = int(os.getenv("API_PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN set karein (.env file mein). .env.example dekhein.")
if not ADMIN_IDS:
    raise SystemExit("❌ ADMIN_IDS set karein (.env file mein). Apni Telegram ID @userinfobot se lein.")
