import asyncio
import html
import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import BaseFilter, Command
from aiogram.exceptions import TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS, STORAGE_CHANNEL_ID
from database import db
from keyboards.reply import (
    get_admin_menu,
    get_main_menu,
    get_cancel_menu,
    get_upload_episodes_menu,
)
from keyboards.inline import (
    get_channels_management_keyboard,
    get_broadcast_confirm_keyboard,
)

admin_router = Router()


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and user.id in ADMIN_IDS)


# Admin routerni global filtrlash — admin bo'lmagan xabarlar bu routerga kirmaydi
admin_router.message.filter(AdminFilter())
admin_router.callback_query.filter(AdminFilter())

# Serial qismlarini parallel (album) yuklashda poyga holatini oldini oluvchi lock
episode_upload_lock = asyncio.Lock()


# ================= FSM HOLATLARI =================

class AddMovieState(StatesGroup):
    waiting_for_video = State()
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_caption = State()


class AddSerialState(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_caption = State()
    waiting_for_episodes = State()


class AppendEpisodeState(StatesGroup):
    waiting_for_code = State()
    waiting_for_episodes = State()


class DeleteMovieState(StatesGroup):
    waiting_for_code = State()


class AddChannelState(StatesGroup):
    waiting_for_id = State()
    waiting_for_title = State()
    waiting_for_link = State()


class BroadcastState(StatesGroup):
    waiting_for_message = State()
    confirm = State()


def is_admin(user_id: int) -> bool:
    """Foydalanuvchi admin ekanligini tekshirish"""
    return user_id in ADMIN_IDS


async def backup_video_to_channel(bot: Bot, message: Message) -> str:
    """Videoni saqlash kanaliga yuborib, doimiy file_id qaytaradi"""
    if STORAGE_CHANNEL_ID:
        try:
            if message.video:
                sent = await bot.send_video(
                    chat_id=STORAGE_CHANNEL_ID,
                    video=message.video.file_id,
                    caption="🎬 Arxiv video"
                )
                return sent.video.file_id
            elif message.document:
                sent = await bot.send_document(
                    chat_id=STORAGE_CHANNEL_ID,
                    document=message.document.file_id,
                    caption="🎬 Arxiv hujjat"
                )
                return sent.document.file_id
        except Exception as e:
            logging.error(f"Kanalga yuborishda xatolik: {e}")

    # Agar kanal ulanmagan yoki xatolik yuz bersa, oddiy file_id ni qaytaradi
    return message.video.file_id if message.video else message.document.file_id


# ================= ADMIN PANEL KIRISH VA BEKOR QILISH =================

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await message.answer(
        "👋 <b>Admin paneliga xush kelibsiz!</b>\n\n"
        "Quyidagi bo'limlardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=get_admin_menu()
    )


@admin_router.message(F.text == "⬅️ Chiqish")
async def btn_exit_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Asosiy foydalanuvchi menyusiga qaytdingiz.", reply_markup=get_main_menu())


@admin_router.message(F.text == "❌ Bekor qilish")
async def cancel_any_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == AddSerialState.waiting_for_episodes:
        data = await state.get_data()
        code = data.get("code")
        if code:
            total = await db.get_total_episodes_count(code)
            if total == 0:
                await db.delete_movie(code)
    await state.clear()
    await message.answer("Jarayon bekor qilindi.", reply_markup=get_admin_menu())


# ================= STATISTIKA =================

@admin_router.message(F.text == "📊 Statistika")
async def btn_statistics(message: Message):
    if not is_admin(message.from_user.id):
        return

    users_count = await db.get_users_count()
    movies_count = await db.get_movies_count()
    channels = await db.get_channels()

    text = (
        "📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 <b>Foydalanuvchilar:</b> {users_count} ta\n"
        f"🎬 <b>Jami kino va seriallar:</b> {movies_count} ta\n"
        f"📢 <b>Ulanmagan/faol kanallar:</b> {len(channels)} ta\n"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_menu())


# ================= YANGI KINO QO'SHISH (FSM) =================

@admin_router.message(F.text == "🎬 Yangi kino qo'shish")
async def start_add_movie(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(AddMovieState.waiting_for_video)
    await message.answer(
        "🎬 <b>Yangi kino qo'shish</b>\n\n"
        "Iltimos, kino videosini (video fayl sifatida) botga yuboring:",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@admin_router.message(AddMovieState.waiting_for_video, F.video | (F.document & F.document.mime_type.startswith("video/")))
async def process_movie_video(message: Message, state: FSMContext, bot: Bot):
    # Kanalga nusxalab, doimiy file_id olamiz
    file_id = await backup_video_to_channel(bot, message)
    await state.update_data(file_id=file_id)
    await state.set_state(AddMovieState.waiting_for_code)
    await message.answer(
        "✅ Video arxivlandi va qabul qilindi!\n\n"
        "Endi kino uchun <b>noyob kod</b> kiriting (Masalan: <code>101</code> yoki <code>avengers</code>):",
        parse_mode="HTML"
    )


@admin_router.message(AddMovieState.waiting_for_video)
async def invalid_video(message: Message):
    await message.answer("⚠️ Iltimos, video fayl yuboring:")


@admin_router.message(AddMovieState.waiting_for_code, F.text)
async def process_movie_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", code) or len(code) > 32:
        await message.answer(
            "⚠️ <b>Kino kodi noto'g'ri!</b>\n"
            "Kod faqat lotin harflari, raqamlar, pastki chiziq (_) yoki tire (-) dan iborat bo'lishi va 32 belgidan oshmasligi kerak (probellarsiz).\n"
            "<i>Masalan: 101, spider_man, avengers</i>",
            parse_mode="HTML"
        )
        return

    existing = await db.get_movie_by_code(code)
    if existing:
        await message.answer(
            f"❌ <code>{html.escape(code)}</code> kodi allaqachon mavjud! Iltimos, boshqa kod kiriting:",
            parse_mode="HTML"
        )
        return

    await state.update_data(code=code)
    await state.set_state(AddMovieState.waiting_for_title)
    await message.answer(
        "✅ Kod saqlandi!\n\nEndi kino <b>nomini</b> kiriting:\n(Masalan: <i>Qasoskorlar: Intiho</i>)",
        parse_mode="HTML"
    )


@admin_router.message(AddMovieState.waiting_for_title, F.text)
async def process_movie_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AddMovieState.waiting_for_caption)
    await message.answer(
        "✅ Nom saqlandi!\n\n"
        "Endi kino uchun qo'shimcha <b>tavsif/ma'lumot</b> yozing (Janri, tili, yili va h.k.).\n"
        "Agar tavsif kerak bo'lmasa, <code>-</code> (chiziqcha) yuboring:",
        parse_mode="HTML"
    )


@admin_router.message(AddMovieState.waiting_for_caption, F.text)
async def process_movie_caption(message: Message, state: FSMContext, bot: Bot):
    caption = message.text.strip()
    if caption == "-":
        caption = None

    data = await state.get_data()
    file_id = data["file_id"]
    code = data["code"]
    title = data["title"]

    success = await db.add_movie(code=code, title=title, file_id=file_id, caption=caption)
    await state.clear()

    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start={code}"

    if success:
        success_text = (
            "🎉 <b>Kino muvaffaqiyatli saqlandi!</b>\n\n"
            f"🎬 <b>Nomi:</b> {html.escape(title)}\n"
            f"🔢 <b>Kodi:</b> <code>{html.escape(code)}</code>\n"
            f"🔗 <b>Kanal uchun to'g'ridan-to'g'ri havola:</b>\n<code>{deep_link}</code>\n\n"
            "<i>Ushbu havolani kanalingizdagi postga qo'ysangiz, foydalanuvchi ustiga bosishi bilan shu kino ochiladi!</i>"
        )
        await message.answer(success_text, parse_mode="HTML", reply_markup=get_admin_menu())
    else:
        await message.answer("❌ Kinoni saqlashda xatolik yuz berdi!", reply_markup=get_admin_menu())


# ================= YANGI SERIAL YARATISH (FSM) =================

@admin_router.message(F.text == "📺 Yangi serial yaratish")
async def start_add_serial(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(AddSerialState.waiting_for_code)
    await message.answer(
        "📺 <b>Yangi serial yaratish</b>\n\n"
        "Serial uchun <b>noyob kod</b> kiriting (Masalan: <code>200</code> yoki <code>qora_sevgi</code>):",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@admin_router.message(AddSerialState.waiting_for_code, F.text)
async def process_serial_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if not re.match(r"^[a-zA-Z0-9_-]+$", code) or len(code) > 32:
        await message.answer(
            "⚠️ <b>Serial kodi noto'g'ri!</b>\n"
            "Kod faqat lotin harflari, raqamlar, pastki chiziq (_) yoki tire (-) dan iborat bo'lishi va 32 belgidan oshmasligi kerak (probellarsiz).\n"
            "<i>Masalan: 200, qora_sevgi, ertugrul</i>",
            parse_mode="HTML"
        )
        return

    existing = await db.get_movie_by_code(code)
    if existing:
        await message.answer(
            f"❌ <code>{html.escape(code)}</code> kodi allaqachon mavjud! Iltimos, boshqa kod kiriting:",
            parse_mode="HTML"
        )
        return

    await state.update_data(code=code)
    await state.set_state(AddSerialState.waiting_for_title)
    await message.answer(
        "✅ Kod saqlandi!\n\nEndi serial <b>nomini</b> kiriting:\n(Masalan: <i>Qashqirlar Makoni</i>)",
        parse_mode="HTML"
    )


@admin_router.message(AddSerialState.waiting_for_title, F.text)
async def process_serial_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AddSerialState.waiting_for_caption)
    await message.answer(
        "✅ Nom saqlandi!\n\n"
        "Endi serial uchun qo'shimcha <b>tavsif/ma'lumot</b> yozing (Janri, davlati, chiqarilgan yili).\n"
        "Agar tavsif kerak bo'lmasa, <code>-</code> (chiziqcha) yuboring:",
        parse_mode="HTML"
    )


@admin_router.message(AddSerialState.waiting_for_caption, F.text)
async def process_serial_caption(message: Message, state: FSMContext):
    caption = message.text.strip()
    if caption == "-":
        caption = None

    data = await state.get_data()
    code = data["code"]
    title = data["title"]

    success = await db.add_serial(code=code, title=title, caption=caption)
    if not success:
        await state.clear()
        await message.answer("❌ Serialni yaratishda xatolik yuz berdi!", reply_markup=get_admin_menu())
        return

    await state.set_state(AddSerialState.waiting_for_episodes)
    await message.answer(
        f"🎉 <b>\"{title}\"</b> seriali yaratildi!\n\n"
        "📹 <b>Endi serial qismlarini (videolarni) yuborishni boshlang:</b>\n"
        "<i>(Bir vaqtda bir nechta videoni belgilab yuborishingiz mumkin. Bot ularni 1, 2, 3... qilib avtomatik tartiblaydi)</i>\n\n"
        "Barcha qismlarni yuborib bo'lgach, pastdagi <b>✅ Yuklashni yakunlash</b> tugmasini bosing.",
        parse_mode="HTML",
        reply_markup=get_upload_episodes_menu()
    )


@admin_router.message(AddSerialState.waiting_for_episodes, F.video | (F.document & F.document.mime_type.startswith("video/")))
async def process_serial_video(message: Message, state: FSMContext, bot: Bot):
    # Kanalga nusxalab, doimiy file_id olamiz
    file_id = await backup_video_to_channel(bot, message)
    data = await state.get_data()
    code = data["code"]

    async with episode_upload_lock:
        new_ep = await db.add_next_episode(serial_code=code, file_id=file_id)

    if new_ep:
        await message.answer(f"✅ <b>{new_ep}-qism</b> qabul qilindi va kanalga saqlandi!")
    else:
        await message.answer("⚠️ Qismni saqlashda xatolik yuz berdi.")


@admin_router.message(AddSerialState.waiting_for_episodes, F.text == "✅ Yuklashni yakunlash")
async def finish_serial_upload(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    await state.clear()

    total = await db.get_total_episodes_count(code)
    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start={code}"

    text = (
        "🎉 <b>Serial to'liq saqlandi!</b>\n\n"
        f"📺 <b>Nomi:</b> {html.escape(title)}\n"
        f"🔢 <b>Kodi:</b> <code>{html.escape(code)}</code>\n"
        f"📊 <b>Jami yuklangan qismlar:</b> {total} ta\n"
        f"🔗 <b>Kanal uchun havola:</b>\n<code>{deep_link}</code>\n\n"
        "<i>Foydalanuvchi bu havolani bossa, serialning barcha qismlari chiroyli menyu bo'lib chiqadi!</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_menu())


# ================= QISM QO'SHISH (MAVJUD SERIALGA) =================

@admin_router.message(F.text == "➕ Qism qo'shish")
async def start_append_episode(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(AppendEpisodeState.waiting_for_code)
    await message.answer(
        "➕ <b>Qaysi serialga yangi qism qo'shmoqchisiz?</b>\n\n"
        "Serialning <b>kodini</b> yuboring:",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@admin_router.message(AppendEpisodeState.waiting_for_code, F.text)
async def process_append_code(message: Message, state: FSMContext):
    code = message.text.strip()
    movie = await db.get_movie_by_code(code)

    if not movie or not movie.get("is_series"):
        await message.answer(
            f"❌ <code>{code}</code> kodli serial topilmadi. Kodni tekshirib qayta kiriting:",
            parse_mode="HTML"
        )
        return

    current_max = await db.get_max_episode_number(code)
    await state.update_data(code=code, title=movie["title"])
    await state.set_state(AppendEpisodeState.waiting_for_episodes)

    await message.answer(
        f"📺 <b>\"{html.escape(movie['title'])}\"</b> seriali tanlandi.\n"
        f"📊 Hozirda <b>{current_max} ta</b> qism mavjud.\n\n"
        f"Endi <b>{current_max + 1}-qismdan</b> boshlab videolarni yuboring.\n"
        "Tugatgach <b>✅ Yuklashni yakunlash</b> tugmasini bosing.",
        parse_mode="HTML",
        reply_markup=get_upload_episodes_menu()
    )


@admin_router.message(AppendEpisodeState.waiting_for_episodes, F.video | (F.document & F.document.mime_type.startswith("video/")))
async def process_append_video(message: Message, state: FSMContext, bot: Bot):
    # Kanalga nusxalab, doimiy file_id olamiz
    file_id = await backup_video_to_channel(bot, message)
    data = await state.get_data()
    code = data["code"]

    async with episode_upload_lock:
        new_ep = await db.add_next_episode(serial_code=code, file_id=file_id)

    if new_ep:
        await message.answer(f"✅ <b>{new_ep}-qism</b> qabul qilindi va kanalga saqlandi!")
    else:
        await message.answer("⚠️ Qismni saqlashda xatolik yuz berdi.")


@admin_router.message(AppendEpisodeState.waiting_for_episodes, F.text == "✅ Yuklashni yakunlash")
async def finish_append_upload(message: Message, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    title = data["title"]
    await state.clear()

    total = await db.get_total_episodes_count(code)
    await message.answer(
        f"🎉 <b>\"{html.escape(title)}\"</b> serialiga yangi qismlar qo'shildi!\n"
        f"📊 Jami qismlar soni: <b>{total} ta</b> bo'ldi.",
        parse_mode="HTML",
        reply_markup=get_admin_menu()
    )


# ================= KINO / SERIAL O'CHIRISH (FSM) =================

@admin_router.message(F.text.in_(["🗑 Kinoni o'chirish", "🗑 Kinoni/Serialni o'chirish"]), AdminFilter())
async def start_delete_movie(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(DeleteMovieState.waiting_for_code)
    await message.answer(
        "🗑 O'chirmoqchi bo'lgan kino yoki serial <b>kodini</b> yuboring:",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@admin_router.message(DeleteMovieState.waiting_for_code, F.text)
async def process_delete_movie(message: Message, state: FSMContext):
    code = message.text.strip()

    # Agar bitta epizodni o'chirish kodi bo'lsa (Masalan: 200_5 yoki qora_sevgi_3)
    if "_" in code:
        parts = code.rsplit("_", 1)
        if parts[1].isdigit():
            serial_code = parts[0]
            ep_num = int(parts[1])
            deleted_ep = await db.delete_episode(serial_code, ep_num)
            await state.clear()
            if deleted_ep:
                await message.answer(
                    f"✅ <code>{html.escape(serial_code)}</code> serialining <b>{ep_num}-qismi</b> muvaffaqiyatli o'chirildi.",
                    parse_mode="HTML",
                    reply_markup=get_admin_menu()
                )
                return
            else:
                await message.answer(
                    f"❌ <code>{html.escape(serial_code)}</code> serialining {ep_num}-qismi topilmadi.",
                    parse_mode="HTML",
                    reply_markup=get_admin_menu()
                )
                return

    deleted = await db.delete_movie(code)
    await state.clear()

    if deleted:
        await message.answer(f"✅ <code>{html.escape(code)}</code> kodli kino/serial barcha qismlari bilan o'chirildi.", parse_mode="HTML", reply_markup=get_admin_menu())
    else:
        await message.answer(f"❌ <code>{html.escape(code)}</code> kodli kino yoki serial topilmadi.", parse_mode="HTML", reply_markup=get_admin_menu())


# ================= MAJBURIY KANALLAR BOSHQARUVI =================

@admin_router.message(F.text == "📢 Majburiy kanallar")
async def btn_manage_channels(message: Message):
    if not is_admin(message.from_user.id):
        return

    channels = await db.get_channels()
    text = (
        "📢 <b>Majburiy obuna kanallari ro'yxati:</b>\n\n"
        "<i>Eslatma: Bot ushbu kanallarda <b>Admin</b> bo'lishi shart, aks holda obunani tekshira olmaydi!</i>\n\n"
    )
    if not channels:
        text += "Hozircha hech qanday kanal ulanmagan."
    else:
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. <b>{ch['title']}</b> (ID: <code>{ch['channel_id']}</code>)\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_channels_management_keyboard(channels)
    )


@admin_router.callback_query(F.data == "add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddChannelState.waiting_for_id)
    await callback.message.answer(
        "📢 <b>Kanal qo'shish</b>\n\n"
        "Kanalning <b>@username</b>'ini yoki <b>ID</b> sini yuboring:\n"
        "<i>(Masalan: @mening_kanalim yoki -1001234567890)</i>\n"
        "Yoki kanaldagi istalgan postni bu yerga <b>Forward</b> qiling!\n\n"
        "⚠️ <i>Avval botni o'sha kanalga <b>Admin</b> qilib tayinlashingiz shart!</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@admin_router.message(AddChannelState.waiting_for_id)
async def process_channel_id(message: Message, state: FSMContext, bot: Bot):
    channel_id = None
    title = None
    invite_link = None

    # 1. Forward qilingan post bo'lsa
    if message.forward_from_chat and message.forward_from_chat.type == "channel":
        channel_id = str(message.forward_from_chat.id)
        title = message.forward_from_chat.title
        if message.forward_from_chat.username:
            invite_link = f"https://t.me/{message.forward_from_chat.username}"
    elif message.text:
        channel_id = message.text.strip()

    if not channel_id:
        await message.answer("⚠️ Iltimos, kanal @username'ini, ID sini yozing yoki kanaldan xabarni forward qiling:")
        return

    # Bot orqali kanal ma'lumotlarini tekshirib avtomatik olish
    try:
        raw_chat_id = int(channel_id) if (channel_id.startswith("-") and channel_id[1:].isdigit()) or channel_id.isdigit() else channel_id
        chat = await bot.get_chat(raw_chat_id)
        channel_id = str(chat.id)
        title = chat.title or title
        if chat.username:
            invite_link = f"https://t.me/{chat.username}"
        elif chat.invite_link:
            invite_link = chat.invite_link
    except Exception as e:
        logging.info(f"Kanal avtomatik aniqlanmadi ({channel_id}): {e}")

    await state.update_data(channel_id=channel_id)

    # Agar title va link to'liq aniqlangan bo'lsa, to'g'ridan-to'g'ri saqlaymiz!
    if title and invite_link:
        success = await db.add_channel(channel_id=channel_id, title=title, invite_link=invite_link)
        await state.clear()
        if success:
            await message.answer(
                f"🎉 <b>Kanal avtomatik aniqlandi va qo'shildi!</b>\n\n"
                f"📢 <b>Nomi:</b> {html.escape(title)}\n"
                f"🆔 <b>ID:</b> <code>{channel_id}</code>\n"
                f"🔗 <b>Havola:</b> {invite_link}",
                parse_mode="HTML",
                reply_markup=get_admin_menu()
            )
            return

    # Agar avtomatik topilmasa, nomini so'raymiz
    if title:
        await state.update_data(title=title)
        await state.set_state(AddChannelState.waiting_for_link)
        await message.answer(
            f"✅ Kanal topildi: <b>{html.escape(title)}</b>\n\n"
            "Endi uning taklif havolasini (linkini) kiriting (Masalan: https://t.me/+AbCdEf):",
            parse_mode="HTML"
        )
    else:
        await state.set_state(AddChannelState.waiting_for_title)
        await message.answer("✅ Endi kanal nomini kiriting (Tugmada ko'rinishi uchun):")


@admin_router.message(AddChannelState.waiting_for_title, F.text)
async def process_channel_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.update_data(title=title)
    await state.set_state(AddChannelState.waiting_for_link)
    await message.answer("✅ Kanal havolasini (linkini) kiriting (Masalan: https://t.me/mening_kanalim):")


@admin_router.message(AddChannelState.waiting_for_link, F.text)
async def process_channel_link(message: Message, state: FSMContext):
    link = message.text.strip()
    data = await state.get_data()
    channel_id = data["channel_id"]
    title = data["title"]

    success = await db.add_channel(channel_id=channel_id, title=title, invite_link=link)
    await state.clear()

    if success:
        await message.answer("🎉 Kanal muvaffaqiyatli qo'shildi!", reply_markup=get_admin_menu())
    else:
        await message.answer("❌ Ushbu kanal allaqachon qo'shilgan yoki xatolik yuz berdi.", reply_markup=get_admin_menu())


@admin_router.callback_query(F.data.startswith("del_channel:"))
async def cb_delete_channel(callback: CallbackQuery):
    channel_id = callback.data.split("del_channel:")[1]
    await db.delete_channel(channel_id)
    await callback.answer("Kanal o'chirildi!", show_alert=True)

    channels = await db.get_channels()
    text = (
        "📢 <b>Majburiy obuna kanallari yangilandi:</b>\n\n"
        "<i>Eslatma: Bot ushbu kanallarda <b>Admin</b> bo'lishi shart, aks holda obunani tekshira olmaydi!</i>\n\n"
    )
    if not channels:
        text += "Hozircha hech qanday kanal ulanmagan."
    else:
        for idx, ch in enumerate(channels, 1):
            text += f"{idx}. <b>{ch['title']}</b> (ID: <code>{ch['channel_id']}</code>)\n"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_channels_management_keyboard(channels)
    )


# ================= REKLAMA TARQATISH (BROADCAST FSM) =================

@admin_router.message(F.text == "✉️ Xabar tarqatish (Reklama)")
async def start_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer(
        "✉️ <b>Barcha foydalanuvchilarga yubormoqchi bo'lgan xabarni yuboring:</b>\n\n"
        "<i>(Matn, rasm, video, audio yoki forward xabar yuborishingiz mumkin)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_menu()
    )


@admin_router.message(BroadcastState.waiting_for_message)
async def preview_broadcast(message: Message, state: FSMContext):
    await state.update_data(broadcast_chat_id=message.chat.id, broadcast_message_id=message.message_id)
    await state.set_state(BroadcastState.confirm)

    users_count = await db.get_users_count()
    await message.answer(
        f"⚠️ Ushbu xabar jami <b>{users_count} ta</b> foydalanuvchiga yuboriladi.\nTasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=get_broadcast_confirm_keyboard()
    )


@admin_router.callback_query(BroadcastState.confirm, F.data == "confirm_broadcast")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer("Xabar tarqatish boshlandi...")

    data = await state.get_data()
    from_chat_id = data["broadcast_chat_id"]
    message_id = data["broadcast_message_id"]
    await state.clear()

    user_ids = await db.get_all_users()
    total_users = len(user_ids)
    await callback.message.edit_text(f"⏳ Xabar tarqatilmoqda... (0/{total_users})")

    success_count = 0
    fail_count = 0

    for idx, uid in enumerate(user_ids, 1):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
            success_count += 1
            await asyncio.sleep(0.04)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
                success_count += 1
            except Exception:
                fail_count += 1
        except Exception as e:
            fail_count += 1
            logging.warning(f"Foydalanuvchiga xabar yuborilmadi ({uid}): {e}")

        # Har 50 ta xabarda progressni yangilash
        if idx % 50 == 0 or idx == total_users:
            percent = int((idx / total_users) * 100) if total_users > 0 else 100
            try:
                await callback.message.edit_text(
                    f"⏳ <b>Xabar tarqatilmoqda...</b>\n\n"
                    f"📊 Jarayon: {idx}/{total_users} ({percent}%)\n"
                    f"🟢 Yetkazildi: {success_count} ta\n"
                    f"🔴 Yetkazilmadi: {fail_count} ta",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    report = (
        "✅ <b>Xabar tarqatish yakunlandi!</b>\n\n"
        f"🟢 Muvaffaqiyatli yetkazildi: {success_count} ta\n"
        f"🔴 Yetkazilmadi (bloklagan): {fail_count} ta\n"
        f"📊 Jami: {total_users} ta"
    )
    await callback.message.answer(report, parse_mode="HTML", reply_markup=get_admin_menu())


@admin_router.callback_query(BroadcastState.confirm, F.data == "cancel_broadcast")
async def cancel_broadcast_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Reklama bekor qilindi.")
    await callback.message.delete()
    await callback.message.answer("Xabar tarqatish bekor qilindi.", reply_markup=get_admin_menu())
