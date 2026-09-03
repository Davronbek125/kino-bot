import aiosqlite
from typing import Optional, List, Dict, Any
from config import DB_PATH


async def init_db():
    """Ma'lumotlar bazasi jadvallarini yaratish"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")

        # Foydalanuvchilar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Kinolar va seriallar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                file_id TEXT,
                caption TEXT,
                is_series INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Agar is_series ustuni avvalgi bazada bo'lmasa, qo'shib qo'yamiz
        try:
            await db.execute("ALTER TABLE movies ADD COLUMN is_series INTEGER DEFAULT 0")
        except Exception:
            pass

        # Serial qismlari (episodes) jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial_code TEXT NOT NULL,
                episode_number INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(serial_code, episode_number)
            )
        """)

        # Majburiy obuna kanallari jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                invite_link TEXT NOT NULL
            )
        """)

        # Indekslar (katta hajmdagi bazada yuqori tezlikni ta'minlash)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(code COLLATE NOCASE);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_episodes_serial ON episodes(serial_code COLLATE NOCASE, episode_number);")

        await db.commit()


# ================= FOYDALANUVCHILAR =================

async def add_user(user_id: int, username: Optional[str], full_name: str):
    """Foydalanuvchini bazaga qo'shish yoki yangilash"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        """, (user_id, username, full_name))
        await db.commit()


async def get_all_users() -> List[int]:
    """Barcha foydalanuvchilar ID ro'yxatini olish (reklama tarqatish uchun)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_users_count() -> int:
    """Foydalanuvchilar sonini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


# ================= KINOLAR =================

async def add_movie(code: str, title: str, file_id: str, caption: Optional[str] = None) -> bool:
    """Yangi kino qo'shish"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO movies (code, title, file_id, caption)
                VALUES (?, ?, ?, ?)
            """, (code.strip(), title.strip(), file_id, caption))
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def get_movie_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Kodni kiritish orqali kinoni qidirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM movies WHERE LOWER(code) = LOWER(?)", (code.strip(),)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def increment_movie_views(code: str):
    """Kino ko'rishlar sonini 1 taga oshirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE movies SET views = views + 1 WHERE LOWER(code) = LOWER(?)", (code.strip(),))
        await db.commit()


def normalize_uzbek_text(text: str) -> str:
    """O'zbek tili tutuq belgilarini yagona standartga keltirish"""
    return text.replace("’", "'").replace("‘", "'").replace("ʻ", "'").replace("`", "'")


async def search_movies_by_title(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Kino nomi bo'yicha qidirish (tutuq belgilariga moslashuvchan)"""
    clean_q = query.strip()
    norm_q = normalize_uzbek_text(clean_q)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT code, title, views, is_series FROM movies 
            WHERE LOWER(title) LIKE LOWER(?) OR LOWER(title) LIKE LOWER(?)
            LIMIT ?
        """, (f"%{clean_q}%", f"%{norm_q}%", limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_random_movie() -> Optional[Dict[str, Any]]:
    """Tasodifiy bitta kinoni olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM movies ORDER BY RANDOM() LIMIT 1") as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def delete_movie(code: str) -> bool:
    """Kino yoki serialni (barcha qismlari bilan) o'chirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM movies WHERE LOWER(code) = LOWER(?)", (code.strip(),))
        await db.execute("DELETE FROM episodes WHERE LOWER(serial_code) = LOWER(?)", (code.strip(),))
        await db.commit()
        return cursor.rowcount > 0


# ================= SERIALLAR VA EPIZODLAR =================

async def add_serial(code: str, title: str, caption: Optional[str] = None) -> bool:
    """Yangi serial yaratish (bazasini ochish)"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO movies (code, title, file_id, caption, is_series)
                VALUES (?, ?, '', ?, 1)
            """, (code.strip(), title.strip(), caption))
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False


async def add_episode(serial_code: str, episode_number: int, file_id: str) -> bool:
    """Serialga qism qo'shish yoki mavjud bo'lsa yangilash"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO episodes (serial_code, episode_number, file_id)
                VALUES (?, ?, ?)
                ON CONFLICT(serial_code, episode_number) DO UPDATE SET
                    file_id = excluded.file_id
            """, (serial_code.strip(), episode_number, file_id))
            await db.commit()
            return True
    except Exception:
        return False


async def add_next_episode(serial_code: str, file_id: str) -> Optional[int]:
    """Serialga navbatdagi qismni avtomatik hisoblab qo'shish va yangi qism raqamini qaytarish"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COALESCE(MAX(episode_number), 0) + 1 FROM episodes WHERE LOWER(serial_code) = LOWER(?)",
                (serial_code.strip(),)
            ) as cursor:
                row = await cursor.fetchone()
                next_ep = row[0] if row else 1

            await db.execute("""
                INSERT INTO episodes (serial_code, episode_number, file_id)
                VALUES (?, ?, ?)
                ON CONFLICT(serial_code, episode_number) DO UPDATE SET
                    file_id = excluded.file_id
            """, (serial_code.strip(), next_ep, file_id))
            await db.commit()
            return next_ep
    except Exception:
        return None


async def get_episodes(serial_code: str) -> List[Dict[str, Any]]:
    """Serialning barcha qismlarini tartiblangan holda olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM episodes 
            WHERE LOWER(serial_code) = LOWER(?) 
            ORDER BY episode_number ASC
        """, (serial_code.strip(),)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_episode(serial_code: str, episode_number: int) -> Optional[Dict[str, Any]]:
    """Serialning muayyan bir qismini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM episodes 
            WHERE LOWER(serial_code) = LOWER(?) AND episode_number = ?
        """, (serial_code.strip(), episode_number)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def get_max_episode_number(serial_code: str) -> int:
    """Serialning eng oxirgi qismi raqamini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT MAX(episode_number) FROM episodes 
            WHERE LOWER(serial_code) = LOWER(?)
        """, (serial_code.strip(),)) as cursor:
            row = await cursor.fetchone()
            return row[0] if (row and row[0] is not None) else 0


async def get_episode_numbers(serial_code: str) -> List[int]:
    """Serialning barcha mavjud qismlari raqamlarini tartiblangan holda olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT episode_number FROM episodes 
            WHERE LOWER(serial_code) = LOWER(?) 
            ORDER BY episode_number ASC
        """, (serial_code.strip(),)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_total_episodes_count(serial_code: str) -> int:
    """Serialdagi jami qismlar sonini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT COUNT(*) FROM episodes 
            WHERE LOWER(serial_code) = LOWER(?)
        """, (serial_code.strip(),)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def delete_episode(serial_code: str, episode_number: int) -> bool:
    """Serialning bitta qismini o'chirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM episodes 
            WHERE LOWER(serial_code) = LOWER(?) AND episode_number = ?
        """, (serial_code.strip(), episode_number))
        await db.commit()
        return cursor.rowcount > 0


async def get_movies_count() -> int:
    """Jami kinolar sonini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM movies") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


# ================= KANALLAR (MAJBURIY OBUNA) =================

async def add_channel(channel_id: str, title: str, invite_link: str) -> bool:
    """Kanal qo'shish yoki mavjud bo'lsa yangilash"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO channels (channel_id, title, invite_link)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    title = excluded.title,
                    invite_link = excluded.invite_link
            """, (channel_id.strip(), title.strip(), invite_link.strip()))
            await db.commit()
            return True
    except Exception:
        return False


async def get_channels() -> List[Dict[str, Any]]:
    """Barcha majburiy obuna kanallarini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def delete_channel(channel_id: str) -> bool:
    """Kanalni o'chirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id.strip(),))
        await db.commit()
        return cursor.rowcount > 0
