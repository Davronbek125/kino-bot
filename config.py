import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylini yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")

# Adminlar ID ro'yxatini olish
raw_admins = os.getenv("ADMIN_IDS", "").strip().strip('"').strip("'")
ADMIN_IDS: list[int] = []
if raw_admins:
    for admin_id_str in raw_admins.split(","):
        cleaned = admin_id_str.strip()
        if cleaned.isdigit():
            ADMIN_IDS.append(int(cleaned))

# Render yoki boshqa serverlar tomonidan beriladigan port
PORT = int(os.getenv("PORT", "0"))

# Arxiv/Saqlash kanali ID si
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "-1003770492872"))

# Ma'lumotlar bazasi fayl manzili
DB_PATH = BASE_DIR / "database" / "bot.db"

# Baza papkasi mavjudligini ta'minlash
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
