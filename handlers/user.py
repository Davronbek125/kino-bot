import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards.reply import get_main_menu, get_cancel_menu
from keyboards.inline import (
    get_subscription_keyboard,
    get_movie_keyboard,
    get_episodes_keyboard,
    get_episode_view_keyboard,
)
from middlewares.subscription import get_unsubscribed_channels

user_router = Router()


class SearchState(StatesGroup):
    waiting_for_query = State()


# ================= YORDAMCHI FUNKSIYALAR =================

async def send_movie_to_user(bot: Bot, chat_id: int, movie: dict):
    """Oddiy kinoni foydalanuvchiga yuborish"""
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"

    title = html.escape(movie["title"])
    code = html.escape(movie["code"])
    views = movie.get("views", 0) + 1

    formatted_caption = (
        f"🎬 <b>{title}</b>\n"
        f"🔢 <b>Kodi:</b> <code>{code}</code>\n"
        f"👁 <b>Ko'rishlar soni:</b> {views}\n\n"
    )
    raw_caption = movie.get("caption")
    if raw_caption:
        safe_caption = html.escape(raw_caption)
        if len(safe_caption) > 800:
            safe_caption = safe_caption[:797] + "..."
        formatted_caption += f"{safe_caption}\n\n"

    formatted_caption += f"🤖 @{bot_username}"

    await db.increment_movie_views(movie["code"])

    await bot.send_video(
        chat_id=chat_id,
        video=movie["file_id"],
        caption=formatted_caption,
        parse_mode="HTML",
        reply_markup=get_movie_keyboard(movie["code"], bot_username)
    )


async def send_serial_overview_to_user(bot: Bot, chat_id: int, movie: dict, total_episodes: int = 0, page: int = 1, message_to_edit: Message = None):
    """Serial haqida ma'lumot va qismlar menyusini ko'rsatish"""
    title = html.escape(movie["title"])
    code = html.escape(movie["code"])
    views = movie.get("views", 0) + 1

    ep_numbers = await db.get_episode_numbers(movie["code"])
    total_episodes = len(ep_numbers)

    text = (
        f"📺 <b>{title}</b> (Serial)\n"
        f"🔢 <b>Serial kodi:</b> <code>{code}</code>\n"
        f"📊 <b>Mavjud qismlar:</b> {total_episodes} ta\n"
        f"👁 <b>Ko'rishlar:</b> {views}\n\n"
    )
    raw_caption = movie.get("caption")
    if raw_caption:
        safe_caption = html.escape(raw_caption)
        if len(safe_caption) > 800:
            safe_caption = safe_caption[:797] + "..."
        text += f"{safe_caption}\n\n"

    if total_episodes == 0:
        text += "⚠️ <i>Ushbu serialga hali qismlar yuklanmagan.</i>"
    else:
        text += "👇 <b>Tomosha qilish uchun kerakli qismni tanlang:</b>"

    reply_markup = get_episodes_keyboard(movie["code"], ep_numbers, page=page)

    if message_to_edit:
        try:
            await message_to_edit.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
            return
        except TelegramBadRequest:
            return
        except Exception:
            pass

    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup)


async def send_episode_to_user(bot: Bot, chat_id: int, movie: dict, ep_num: int, total_episodes: int = 0):
    """Serialning bitta qismini foydalanuvchiga yuborish"""
    episode = await db.get_episode(movie["code"], ep_num)
    if not episode:
        await bot.send_message(chat_id, f"❌ {ep_num}-qism topilmadi.")
        return

    ep_numbers = await db.get_episode_numbers(movie["code"])
    total_episodes = len(ep_numbers)

    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"

    title = html.escape(movie["title"])
    code = html.escape(movie["code"])

    caption = (
        f"📺 <b>{title}</b>\n"
        f"🎬 <b>{ep_num}-qism</b> (Jami: {total_episodes} ta)\n"
        f"🔢 <b>Kodi:</b> <code>{code}_{ep_num}</code>\n\n"
        f"🤖 @{bot_username}"
    )

    await bot.send_video(
        chat_id=chat_id,
        video=episode["file_id"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=get_episode_view_keyboard(movie["code"], ep_num, ep_numbers, bot_username)
    )


async def handle_movie_or_series_delivery(bot: Bot, chat_id: int, code_str: str) -> bool:
    """Kino, serial yoki serial qismini yetkazib beruvchi yagona funksiya"""
    clean_code = code_str.strip()

    # 1. Avval to'g'ridan-to'g'ri kod bo'yicha qidirish
    movie = await db.get_movie_by_code(clean_code)
    if movie:
        if movie.get("is_series"):
            await db.increment_movie_views(movie["code"])
            await send_serial_overview_to_user(bot, chat_id, movie, page=1)
            return True
        else:
            await send_movie_to_user(bot, chat_id, movie)
            return True

    # 2. Agar to'g'ridan-to'g'ri topilmasa va format serial_qism bo'lsa (Masalan: 200_5 yoki qora_sevgi_12)
    if "_" in clean_code:
        parts = clean_code.rsplit("_", 1)
        serial_code = parts[0]
        if parts[1].isdigit():
            ep_num = int(parts[1])
            movie = await db.get_movie_by_code(serial_code)
            if movie and movie.get("is_series"):
                await send_episode_to_user(bot, chat_id, movie, ep_num)
                return True

    return False


# ================= /start BUYRUG'I VA DEEP LINKING =================

@user_router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()

    # Foydalanuvchini bazaga qo'shish
    user = message.from_user
    await db.add_user(user.id, user.username, user.full_name)

    # Majburiy kanallarni tekshirish
    channels = await db.get_channels()
    unsubscribed = await get_unsubscribed_channels(bot, user.id, channels)

    payload = command.args.strip() if command.args else None

    # Agar a'zo bo'lmagan kanallar bo'lsa
    if unsubscribed:
        text = (
            f"Assalomu alaykum, <b>{html.escape(user.full_name)}</b>!\n\n"
            "⚠️ Botdan to'liq foydalanish va kinoni yuklab olish uchun "
            "quyidagi hamkor kanallarimizga obuna bo'ling:"
        )
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard(unsubscribed, movie_code=payload)
        )
        return

    # Deep link orqali kino yoki serial so'ralgan bo'lsa
    if payload:
        delivered = await handle_movie_or_series_delivery(bot, message.chat.id, payload)
        if delivered:
            return
        else:
            await message.answer(
                f"❌ Kechirasiz, <code>{html.escape(payload)}</code> kodli kino yoki serial topilmadi!",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            return

    # Oddiy start xabari
    welcome_text = (
        f"Assalomu alaykum, <b>{html.escape(user.full_name)}</b>! 🎬\n\n"
        "Men <b>Kodli Kinolar va Seriallar</b> botiman.\n\n"
        "📥 Kino yoki serialni olish uchun uning <b>kodini</b> yuboring (Masalan: <code>101</code>).\n"
        "Yoki pastdagi menyu orqali qidirishingiz mumkin:"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu())


# ================= OBUNANI TEKSHIRISH CALLBACK =================

@user_router.callback_query(F.data.startswith("check_sub:"))
async def callback_check_subscription(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    channels = await db.get_channels()
    unsubscribed = await get_unsubscribed_channels(bot, user_id, channels)

    payload = callback.data.split("check_sub:")[1]
    code = payload if payload != "none" else None

    if unsubscribed:
        await callback.answer("❌ Siz hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
        try:
            await callback.message.edit_reply_markup(
                reply_markup=get_subscription_keyboard(unsubscribed, movie_code=code)
            )
        except TelegramBadRequest:
            pass
        return

    await callback.answer("✅ Rahmat! Barcha kanallarga a'zo bo'ldingiz.")
    try:
        await callback.message.delete()
    except Exception:
        pass

    if code:
        delivered = await handle_movie_or_series_delivery(bot, callback.message.chat.id, code)
        if not delivered:
            await callback.message.answer(
                f"❌ Afsuski, <code>{html.escape(code)}</code> kodli kino yoki serial topilmadi.",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
        return

    await callback.message.answer(
        "✅ Rahmat! Endi kino yoki serial kodini yuborishingiz mumkin:",
        reply_markup=get_main_menu()
    )


# ================= SERIAL EPIZODLARI CALLBACK =================

@user_router.callback_query(F.data.startswith("ep:"))
async def callback_open_episode(callback: CallbackQuery, bot: Bot):
    # Format: ep:{serial_code}:{ep_num}
    parts = callback.data.split(":")
    serial_code = parts[1]
    ep_num = int(parts[2])

    movie = await db.get_movie_by_code(serial_code)
    if not movie:
        await callback.answer("Serial topilmadi.", show_alert=True)
        return

    await callback.answer(f"{ep_num}-qism ochilmoqda...")
    await send_episode_to_user(bot, callback.message.chat.id, movie, ep_num)


@user_router.callback_query(F.data.startswith("ep_page:"))
async def callback_episodes_page(callback: CallbackQuery, bot: Bot):
    # Format: ep_page:{serial_code}:{page}
    parts = callback.data.split(":")
    serial_code = parts[1]
    page = int(parts[2])

    movie = await db.get_movie_by_code(serial_code)
    if not movie:
        await callback.answer("Serial topilmadi.", show_alert=True)
        return

    await callback.answer()
    await send_serial_overview_to_user(bot, callback.message.chat.id, movie, page=page, message_to_edit=callback.message)


@user_router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


# ================= TASODIFIY KINO =================

@user_router.message(Command("random"))
@user_router.message(F.text == "🎲 Tasodifiy kino")
async def btn_random_movie(message: Message, bot: Bot):
    # Foydalanuvchini bazaga yozish
    user = message.from_user
    await db.add_user(user.id, user.username, user.full_name)

    channels = await db.get_channels()
    unsubscribed = await get_unsubscribed_channels(bot, message.from_user.id, channels)
    if unsubscribed:
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_subscription_keyboard(unsubscribed)
        )
        return

    movie = await db.get_random_movie()
    if not movie:
        await message.answer("😔 Hozircha bazada kinolar mavjud emas.")
        return

    if movie.get("is_series"):
        await send_serial_overview_to_user(bot, message.chat.id, movie, page=1)
    else:
        await send_movie_to_user(bot, message.chat.id, movie)


@user_router.callback_query(F.data == "random_movie")
async def cb_random_movie(callback: CallbackQuery, bot: Bot):
    # Obunani tekshirish
    channels = await db.get_channels()
    unsubscribed = await get_unsubscribed_channels(bot, callback.from_user.id, channels)
    if unsubscribed:
        await callback.answer("⚠️ Botdan foydalanish uchun homiy kanallarga a'zo bo'ling!", show_alert=True)
        await callback.message.answer(
            "⚠️ Botdan to'liq foydalanish uchun quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_subscription_keyboard(unsubscribed)
        )
        return

    movie = await db.get_random_movie()
    if not movie:
        await callback.answer("😔 Boshqa kinolar topilmadi.", show_alert=True)
        return

    await callback.answer()
    if movie.get("is_series"):
        await send_serial_overview_to_user(bot, callback.message.chat.id, movie, page=1)
    else:
        await send_movie_to_user(bot, callback.message.chat.id, movie)


# ================= NOMI BO'YICHA QIDIRISH =================

@user_router.message(Command("search"))
@user_router.message(F.text == "🔍 Nomi bo'yicha qidirish")
async def btn_search_movie(message: Message, state: FSMContext):
    # Foydalanuvchini bazaga yozish
    user = message.from_user
    await db.add_user(user.id, user.username, user.full_name)

    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🔎 Qidirmoqchi bo'lgan kino yoki serial nomini yozing:\n"
        "<i>(Masalan: O'rgimchak odam, Qashqirlar makoni yoki Avatar)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@user_router.message(SearchState.waiting_for_query, F.text == "❌ Bekor qilish")
async def cancel_search(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Qidiruv bekor qilindi.", reply_markup=get_main_menu())


@user_router.message(SearchState.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    query = message.text.strip()
    movies = await db.search_movies_by_title(query)
    await state.clear()

    if not movies:
        await message.answer(
            f"❌ <b>\"{html.escape(query)}\"</b> bo'yicha hech qanday kino yoki serial topilmadi.\n"
            "Nomini to'g'ri yozganingizga ishonch hosil qiling.",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return

    response = "<b>🔍 Qidiruv natijalari:</b>\n\n"
    for idx, m in enumerate(movies, 1):
        type_icon = "📺 [Serial]" if m.get("is_series") else "🎬 [Film]"
        response += f"{idx}. {type_icon} <b>{html.escape(m['title'])}</b>\n   🔢 Kodi: <code>{html.escape(m['code'])}</code>\n\n"

    response += "💡 <i>Tomosha qilish uchun uning kodini botga yuboring!</i>"
    await message.answer(response, parse_mode="HTML", reply_markup=get_main_menu())


# ================= BOT HAQIDA VA YORDAM =================

@user_router.message(Command("help"))
@user_router.message(F.text == "ℹ️ Bot haqida")
async def btn_about(message: Message):
    text = (
        "ℹ️ <b>Kodli Kinolar va Seriallar Boti</b>\n\n"
        "Bu bot orqali siz o'zingizga kerakli film va seriallarni qulay va tez yuklab olishingiz mumkin.\n\n"
        "📌 <b>Qanday ishlaydi?</b>\n"
        "1. Kanalimizda ko'rgan kino yoki serialingiz kodini oling.\n"
        "2. Botga o'sha kodni yuboring (Masalan: <code>101</code> yoki <code>200</code>).\n"
        "3. Seriallar bo'lsa, qismlar menyusi orqali istalgan qismni (1-100+) tanlab tomosha qiling!\n\n"
        "Hammasi juda oson va qulay! 🍿"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())


# ================= KOD ORQALI KINO/SERIAL OLISH (UMUMIY MATN) =================

@user_router.message(F.text)
async def process_movie_code(message: Message, bot: Bot):
    code = message.text.strip()

    # Foydalanuvchini bazaga yozish
    user = message.from_user
    await db.add_user(user.id, user.username, user.full_name)

    # Majburiy obunani tekshirish
    channels = await db.get_channels()
    unsubscribed = await get_unsubscribed_channels(bot, message.from_user.id, channels)
    if unsubscribed:
        await message.answer(
            "⚠️ Botdan foydalanish uchun avval quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_subscription_keyboard(unsubscribed, movie_code=code)
        )
        return

    delivered = await handle_movie_or_series_delivery(bot, message.chat.id, code)
    if not delivered:
        await message.answer(
            f"❌ Kechirasiz, <code>{html.escape(code)}</code> kodli kino yoki serial topilmadi!\n\n"
            "Iltimos, kodni to'g'ri kiritganingizni tekshiring yoki <b>🔍 Nomi bo'yicha qidirish</b> tugmasidan foydalaning.",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
