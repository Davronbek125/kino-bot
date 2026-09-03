from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional, Union
from urllib.parse import quote_plus


def get_subscription_keyboard(channels: List[Dict[str, Any]], movie_code: Optional[str] = None) -> InlineKeyboardMarkup:
    """Majburiy obuna kanallari va tekshirish tugmasi"""
    buttons = []
    
    # Har bir kanal uchun havola tugmasi
    for idx, ch in enumerate(channels, 1):
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {idx}-kanalga a'zo bo'lish",
                url=ch["invite_link"]
            )
        ])
    
    # Obunani tekshirish tugmasi (movie_code saqlanadi)
    code_payload = movie_code if movie_code else "none"
    buttons.append([
        InlineKeyboardButton(
            text="✅ A'zo bo'ldim / Tekshirish",
            callback_data=f"check_sub:{code_payload}"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_movie_keyboard(movie_code: str, bot_username: str) -> InlineKeyboardMarkup:
    """Kino ostidagi tugmalar (Ulashish va tasodifiy)"""
    target_link = f"https://t.me/{bot_username}?start={movie_code}"
    share_url = f"https://t.me/share/url?url={quote_plus(target_link)}&text={quote_plus('Ajoyib kino topdim! Tomosha qiling:')}"
    
    buttons = [
        [
            InlineKeyboardButton(text="↗️ Do'stlarga ulashish", url=share_url),
            InlineKeyboardButton(text="🎲 Boshqa kino", callback_data="random_movie")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_channels_management_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Admin uchun kanallarni ko'rish va o'chirish klaviaturasi"""
    buttons = []
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["invite_link"]),
            InlineKeyboardButton(text="❌ O'chirish", callback_data=f"del_channel:{ch['channel_id']}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="➕ Yangi kanal qo'shish", callback_data="add_channel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Reklamani tasdiqlash tugmalari"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data="confirm_broadcast"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_broadcast")
            ]
        ]
    )


# ================= SERIALLAR VA PAGINATSIYA =================

def get_episodes_keyboard(
    serial_code: str, 
    episodes_data: Union[int, List[int]], 
    page: int = 1, 
    page_size: int = 10
) -> InlineKeyboardMarkup:
    """Serial qismlarini tanlash (har sahifada 10 tadan qism)"""
    if isinstance(episodes_data, int):
        all_episodes = list(range(1, episodes_data + 1))
    else:
        all_episodes = episodes_data

    total_count = len(all_episodes)
    if total_count <= 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    total_pages = (total_count + page_size - 1) // page_size
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_count)
    current_page_episodes = all_episodes[start_idx:end_idx]

    # Qismlar tugmalari (har qatorda 2 tadan)
    buttons = []
    current_row = []
    for ep in current_page_episodes:
        current_row.append(
            InlineKeyboardButton(text=f"🎬 {ep}-qism", callback_data=f"ep:{serial_code}:{ep}")
        )
        if len(current_row) == 2:
            buttons.append(current_row)
            current_row = []
    if current_row:
        buttons.append(current_row)

    # Paginatsiya qatori (agar sahifalar 1 tadan ko'p bo'lsa)
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"ep_page:{serial_code}:{page - 1}")
            )
        nav_row.append(
            InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop")
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"ep_page:{serial_code}:{page + 1}")
            )
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_episode_view_keyboard(
    serial_code: str, 
    current_episode: int, 
    all_episodes: Union[int, List[int]], 
    bot_username: str
) -> InlineKeyboardMarkup:
    """Muayyan bir qism videosi ostidagi navigatsiya tugmalari"""
    buttons = []

    if isinstance(all_episodes, int):
        ep_list = list(range(1, all_episodes + 1))
    else:
        ep_list = all_episodes

    prev_ep = None
    next_ep = None
    if current_episode in ep_list:
        idx = ep_list.index(current_episode)
        if idx > 0:
            prev_ep = ep_list[idx - 1]
        if idx < len(ep_list) - 1:
            next_ep = ep_list[idx + 1]
        page = idx // 10 + 1
    else:
        if current_episode > 1:
            prev_ep = current_episode - 1
        page = (current_episode - 1) // 10 + 1

    # Oldingi va keyingi qism tugmalari
    nav_row = []
    if prev_ep is not None:
        nav_row.append(
            InlineKeyboardButton(text=f"⬅️ {prev_ep}-qism", callback_data=f"ep:{serial_code}:{prev_ep}")
        )
    if next_ep is not None:
        nav_row.append(
            InlineKeyboardButton(text=f"{next_ep}-qism ➡️", callback_data=f"ep:{serial_code}:{next_ep}")
        )
    if nav_row:
        buttons.append(nav_row)

    # Barcha qismlar menyusi va ulashish
    target_link = f"https://t.me/{bot_username}?start={serial_code}_{current_episode}"
    share_text = f"Serialning {current_episode}-qismini ko'ring!"
    share_url = f"https://t.me/share/url?url={quote_plus(target_link)}&text={quote_plus(share_text)}"
    buttons.append([
        InlineKeyboardButton(text="📋 Qismlar ro'yxati", callback_data=f"ep_page:{serial_code}:{page}"),
        InlineKeyboardButton(text="↗️ Ulashish", url=share_url)
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
