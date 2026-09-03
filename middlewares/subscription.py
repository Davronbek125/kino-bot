import logging
from typing import List, Dict, Any, Union
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from config import ADMIN_IDS


async def get_unsubscribed_channels(bot: Bot, user_id: int, channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Foydalanuvchi a'zo bo'lmagan kanallar ro'yxatini qaytaradi.
    Adminlar uchun har doim bo'sh ro'yxat qaytaradi (Admin Bypass).
    Agar barcha kanallarga a'zo bo'lsa, bo'sh ro'yxat qaytaradi [].
    """
    if user_id in ADMIN_IDS:
        return []

    if not channels:
        return []

    unsubscribed = []
    for ch in channels:
        raw_chat_id = str(ch["channel_id"]).strip()
        chat_id: Union[int, str] = int(raw_chat_id) if (raw_chat_id.startswith("-") and raw_chat_id[1:].isdigit()) or raw_chat_id.isdigit() else raw_chat_id

        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.RESTRICTED):
                if member.status == ChatMemberStatus.RESTRICTED and getattr(member, 'is_member', False):
                    continue
                unsubscribed.append(ch)
        except TelegramBadRequest as e:
            # Foydalanuvchi kanalda bo'lmasa Telegram xato qaytarishi mumkin (user not found)
            err_msg = str(e).lower()
            if "user not found" in err_msg or "participant_id_invalid" in err_msg:
                unsubscribed.append(ch)
            else:
                logging.warning(f"Kanal obunasini tekshirishda xatolik ({ch['channel_id']}): {e}")
        except Exception as e:
            logging.error(f"Obunani tekshirishda kutilmagan xatolik ({ch['channel_id']}): {e}")

    return unsubscribed
