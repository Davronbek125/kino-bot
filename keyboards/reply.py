from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    """Foydalanuvchi asosiy menyusi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Nomi bo'yicha qidirish"),
                KeyboardButton(text="🎲 Tasodifiy kino")
            ],
            [
                KeyboardButton(text="ℹ️ Bot haqida")
            ]
        ],
        resize_keyboard=True
    )


def get_admin_menu() -> ReplyKeyboardMarkup:
    """Admin paneli menyusi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎬 Yangi kino qo'shish"),
                KeyboardButton(text="📺 Yangi serial yaratish")
            ],
            [
                KeyboardButton(text="➕ Qism qo'shish"),
                KeyboardButton(text="🗑 Kinoni/Serialni o'chirish")
            ],
            [
                KeyboardButton(text="📢 Majburiy kanallar"),
                KeyboardButton(text="📊 Statistika")
            ],
            [
                KeyboardButton(text="✉️ Xabar tarqatish (Reklama)")
            ],
            [
                KeyboardButton(text="⬅️ Chiqish")
            ]
        ],
        resize_keyboard=True
    )


def get_upload_episodes_menu() -> ReplyKeyboardMarkup:
    """Serial qismlarini yuklash jarayoni tugmalari"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Yuklashni yakunlash")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )


def get_cancel_menu() -> ReplyKeyboardMarkup:
    """Jarayonni bekor qilish tugmasi"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )
