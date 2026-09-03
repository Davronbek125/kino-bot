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

# Ma'lumotlar bazasi fayl manzili (Render Persistent Disk qo'llab-quvvatlanadi)
db_path_env = os.getenv("DB_PATH", "").strip().strip('"').strip("'")
if db_path_env:
    DB_PATH = Path(db_path_env)
else:
    DB_PATH = BASE_DIR / "database" / "bot.db"

# Baza papkasi mavjudligini ta'minlash
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
