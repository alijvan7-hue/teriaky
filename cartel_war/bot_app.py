"""
Sample Bot Application Runner for Cartel War using Aiogram 3.x and APScheduler.
"""
import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from cartel_war.database import init_cartel_war_db
from cartel_war.repository import WarRepository
from cartel_war.service import WarService
from cartel_war.handlers import war_router
from cartel_war.scheduler import setup_war_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("CartelWarApp")

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DB_PATH = os.getenv("DB_PATH", "cartel_war.db")


async def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.warning("⚠️ BOT_TOKEN تنظیم نشده است. لطفاً متغیر محیطی BOT_TOKEN را تنظیم کنید.")

    # ۱. آماده‌سازی دیتابیس
    await init_cartel_war_db(DB_PATH)
    logger.info("دیتابیس آماده شد ✅")

    # ۲. ساخت لایه‌های Service و Repository
    repo = WarRepository(DB_PATH)
    war_service = WarService(DB_PATH, repo)

    # ۳. راه‌اندازی بات و دیسپچر
    bot = Bot(token=BOT_TOKEN) if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE" else None
    dp = Dispatcher()

    # تزریق dependencyها به هندلرها
    dp["war_service"] = war_service
    if bot:
        dp["bot"] = bot

    dp.include_router(war_router)

    # ۴. راه‌اندازی APScheduler
    scheduler = AsyncIOScheduler()
    setup_war_scheduler(scheduler, war_service, bot)
    scheduler.start()
    logger.info("زمان‌بند APScheduler فعال شد ⏰")

    if bot:
        logger.info("ربات در حال اجرا است...")
        try:
            await dp.start_polling(bot)
        finally:
            scheduler.shutdown()
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("ربات متوقف شد.")
