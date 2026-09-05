import os
import asyncpg
from typing import Optional, List, Dict, Any

# Connection stringni Render Environment Variables (DATABASE_URL) dan oladi
DATABASE_URL = os.getenv("DATABASE_URL")

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """PostgreSQL ulanishlar pulini (Pool) yaratish va boshqarish"""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL muhit o'zgaruvchisi topilmadi!")
        _pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def init_db():
    """Ma'lumotlar bazasi jadvallarini PostgreSQL da yaratish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Foydalanuvchilar jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Kinolar va seriallar jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                file_id TEXT,
                caption TEXT,
                is_series INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Serial qismlari (episodes) jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id SERIAL PRIMARY KEY,
                serial_code TEXT NOT NULL,
                episode_number INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(serial_code, episode_number)
            );
        """)

        # Majburiy obuna kanallari jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                invite_link TEXT NOT NULL
            );
        """)

        # Indekslar (katta hajmda tezlikni ta'minlash)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(LOWER(code));")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_serial ON episodes(LOWER(serial_code), episode_number);")


# ================= FOYDALANUVCHILAR =================

async def add_user(user_id: int, username: Optional[str], full_name: str):
    """Foydalanuvchini bazaga qo'shish yoki yangilash"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT(user_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name
        """, user_id, username, full_name)


async def get_all_users() -> List[int]:
    """Barcha foydalanuvchilar ID ro'yxatini olish (reklama tarqatish uchun)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [row["user_id"] for row in rows]


async def get_users_count() -> int:
    """Foydalanuvchilar sonini olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT COUNT(*) FROM users")
        return val or 0


# ================= KINOLAR =================

async def add_movie(code: str, title: str, file_id: str, caption: Optional[str] = None) -> bool:
    """Yangi kino qo'shish"""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO movies (code, title, file_id, caption)
                VALUES ($1, $2, $3, $4)
            """, code.strip(), title.strip(), file_id, caption)
            return True
    except asyncpg.UniqueViolationError:
        return False
    except Exception:
        return False


async def get_movie_by_code(code: str) -> Optional[Dict[str, Any]]:
    """Kodni kiritish orqali kinoni qidirish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM movies WHERE LOWER(code) = LOWER($1)", code.strip())
        return dict(row) if row else None


async def increment_movie_views(code: str):
    """Kino ko'rishlar sonini 1 taga oshirish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE movies SET views = views + 1 WHERE LOWER(code) = LOWER($1)", code.strip())


def normalize_uzbek_text(text: str) -> str:
    """O'zbek tili tutuq belgilarini yagona standartga keltirish"""
    return text.replace("’", "'").replace("‘", "'").replace("ʻ", "'").replace("`", "'")


async def search_movies_by_title(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Kino nomi bo'yicha qidirish (ILIKE orqali katta-kichik harflarga sezgir bo'lmagan qidiruv)"""
    clean_q = query.strip()
    norm_q = normalize_uzbek_text(clean_q)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT code, title, views, is_series FROM movies 
            WHERE title ILIKE $1 OR title ILIKE $2
            LIMIT $3
        """, f"%{clean_q}%", f"%{norm_q}%", limit)
        return [dict(row) for row in rows]


async def get_random_movie() -> Optional[Dict[str, Any]]:
    """Tasodifiy bitta kinoni olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM movies ORDER BY RANDOM() LIMIT 1")
        return dict(row) if row else None


async def delete_movie(code: str) -> bool:
    """Kino yoki serialni (barcha qismlari bilan) o'chirish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("DELETE FROM movies WHERE LOWER(code) = LOWER($1)", code.strip())
        await conn.execute("DELETE FROM episodes WHERE LOWER(serial_code) = LOWER($1)", code.strip())
        # res odatda 'DELETE X' shaklida qaytadi
        count = int(res.split()[-1]) if res else 0
        return count > 0


# ================= SERIALLAR VA EPIZODLAR =================

async def add_serial(code: str, title: str, caption: Optional[str] = None) -> bool:
    """Yangi serial yaratish (bazasini ochish)"""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO movies (code, title, file_id, caption, is_series)
                VALUES ($1, $2, '', $3, 1)
            """, code.strip(), title.strip(), caption)
            return True
    except asyncpg.UniqueViolationError:
        return False
    except Exception:
        return False


async def add_episode(serial_code: str, episode_number: int, file_id: str) -> bool:
    """Serialga qism qo'shish yoki mavjud bo'lsa yangilash"""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO episodes (serial_code, episode_number, file_id)
                VALUES ($1, $2, $3)
                ON CONFLICT(serial_code, episode_number) DO UPDATE SET
                    file_id = EXCLUDED.file_id
            """, serial_code.strip(), episode_number, file_id)
            return True
    except Exception:
        return False


async def add_next_episode(serial_code: str, file_id: str) -> Optional[int]:
    """Serialga navbatdagi qismni avtomatik hisoblab qo'shish va yangi qism raqamini qaytarish"""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            next_ep = await conn.fetchval("""
                SELECT COALESCE(MAX(episode_number), 0) + 1 
                FROM episodes 
                WHERE LOWER(serial_code) = LOWER($1)
            """, serial_code.strip())
            next_ep = next_ep or 1

            await conn.execute("""
                INSERT INTO episodes (serial_code, episode_number, file_id)
                VALUES ($1, $2, $3)
                ON CONFLICT(serial_code, episode_number) DO UPDATE SET
                    file_id = EXCLUDED.file_id
            """, serial_code.strip(), next_ep, file_id)
            return next_ep
    except Exception:
        return None


async def get_episodes(serial_code: str) -> List[Dict[str, Any]]:
    """Serialning barcha qismlarini tartiblangan holda olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM episodes 
            WHERE LOWER(serial_code) = LOWER($1) 
            ORDER BY episode_number ASC
        """, serial_code.strip())
        return [dict(row) for row in rows]


async def get_episode(serial_code: str, episode_number: int) -> Optional[Dict[str, Any]]:
    """Serialning muayyan bir qismini olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM episodes 
            WHERE LOWER(serial_code) = LOWER($1) AND episode_number = $2
        """, serial_code.strip(), episode_number)
        return dict(row) if row else None


async def get_max_episode_number(serial_code: str) -> int:
    """Serialning eng oxirgi qismi raqamini olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("""
            SELECT MAX(episode_number) FROM episodes 
            WHERE LOWER(serial_code) = LOWER($1)
        """, serial_code.strip())
        return val if val is not None else 0


async def get_episode_numbers(serial_code: str) -> List[int]:
    """Serialning barcha mavjud qismlari raqamlarini tartiblangan holda olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT episode_number FROM episodes 
            WHERE LOWER(serial_code) = LOWER($1) 
            ORDER BY episode_number ASC
        """, serial_code.strip())
        return [row["episode_number"] for row in rows]


async def get_total_episodes_count(serial_code: str) -> int:
    """Serialdagi jami qismlar sonini olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("""
            SELECT COUNT(*) FROM episodes 
            WHERE LOWER(serial_code) = LOWER($1)
        """, serial_code.strip())
        return val or 0


async def delete_episode(serial_code: str, episode_number: int) -> bool:
    """Serialning bitta qismini o'chirish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("""
            DELETE FROM episodes 
            WHERE LOWER(serial_code) = LOWER($1) AND episode_number = $2
        """, serial_code.strip(), episode_number)
        count = int(res.split()[-1]) if res else 0
        return count > 0


async def get_movies_count() -> int:
    """Jami kinolar sonini olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT COUNT(*) FROM movies")
        return val or 0


# ================= KANALLAR (MAJBURIY OBUNA) =================

async def add_channel(channel_id: str, title: str, invite_link: str) -> bool:
    """Kanal qo'shish yoki mavjud bo'lsa yangilash"""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO channels (channel_id, title, invite_link)
                VALUES ($1, $2, $3)
                ON CONFLICT(channel_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    invite_link = EXCLUDED.invite_link
            """, channel_id.strip(), title.strip(), invite_link.strip())
            return True
    except Exception:
        return False


async def get_channels() -> List[Dict[str, Any]]:
    """Barcha majburiy obuna kanallarini olish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM channels")
        return [dict(row) for row in rows]


async def delete_channel(channel_id: str) -> bool:
    """Kanalni o'chirish"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("DELETE FROM channels WHERE channel_id = $1", channel_id.strip())
        count = int(res.split()[-1]) if res else 0
        return count > 0
