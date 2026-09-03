import asyncio
import logging
import sys

# Windows konsolida emojilarni xatosiz chiqarish uchun
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from config import BOT_TOKEN, PORT
from database.db import init_db
from handlers.admin import admin_router
from handlers.user import user_router


async def handle_health_check(request):
    """Render kabi platformalar uchun health-check handler"""
    return web.Response(text="Bot is running! 🎬", content_type="text/plain")


async def start_health_server(port: int):
    """Render Web Service port tekshiruvidan muvaffaqiyatli o'tishi uchun yengil veb-server"""
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Render health-check veb-server 0.0.0.0:{port} da muvaffaqiyatli ishga tushdi.")
    return runner


async def main():
    # Log sozlamalari
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "=" * 60)
        print("❌ DIQQAT: BOT_TOKEN ko'rsatilmagan!")
        print("Iltimos, .env faylini oching va Telegram @BotFather dan")
        print("olingan tokenni BOT_TOKEN qatoriga yozing.")
        print("Masalan: BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        print("=" * 60 + "\n")
        sys.exit(1)

    # Ma'lumotlar bazasini ishga tushirish
    await init_db()
    logging.info("Ma'lumotlar bazasi muvaffaqiyatli ishga tushirildi.")

    # Bot va Dispatcher yaratish
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Routerni ulash: avval admin_router, so'ng user_router
    dp.include_router(admin_router)
    dp.include_router(user_router)

    # Eski kutilayotgan xabarlarni o'chirish va polling boshlash
    await bot.delete_webhook(drop_pending_updates=True)
    bot_info = await bot.get_me()
    logging.info(f"Bot muvaffaqiyatli ishga tushdi: @{bot_info.username}")

    # Telegram menyu tugmasi buyruqlarini sozlash
    try:
        commands = [
            BotCommand(command="start", description="Botni ishga tushirish 🎬"),
            BotCommand(command="search", description="Kino qidirish 🔍"),
            BotCommand(command="random", description="Tasodifiy kino 🎲"),
            BotCommand(command="help", description="Qo'llanma va yordam ℹ️"),
        ]
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logging.info("Telegram buyruqlar menyusi o'rnatildi.")
    except Exception as e:
        logging.warning(f"Buyruqlar menyusini o'rnatishda xatolik: {e}")

    # Render uchun yengil veb-server (agar PORT berilgan bo'lsa)
    web_runner = None
    if PORT > 0:
        try:
            web_runner = await start_health_server(PORT)
        except Exception as e:
            logging.error(f"Health-check veb-serverni ishga tushirishda xatolik: {e}")

    try:
        await dp.start_polling(bot)
    finally:
        if web_runner:
            await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")
