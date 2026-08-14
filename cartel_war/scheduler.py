"""
APScheduler Jobs for Cartel War System.
Manages automatic state transitions, expiration, war start, war end, and daily quota reset.
"""
from datetime import datetime
import logging
from typing import Optional

from aiogram import Bot
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from cartel_war.models import WarStatus
from cartel_war.service import WarService

logger = logging.getLogger(__name__)


async def job_check_pending_wars(war_service: WarService, bot: Optional[Bot] = None):
    """منقضی کردن درخواست‌های معلق بعد از ۱ ساعت بدون پاسخ"""
    now = datetime.now()
    async with aiosqlite.connect(war_service.db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        async with db.execute(
            """
            SELECT id, attacker_leader_id, defender_leader_id 
            FROM cartel_wars 
            WHERE status = 'pending' AND expires_at <= ?
            """,
            (now.strftime("%Y-%m-%d %H:%M:%S"),)
        ) as cursor:
            expired_wars = await cursor.fetchall()

        for war_id, att_leader, def_leader in expired_wars:
            await war_service.repo.update_war_status(db, war_id, WarStatus.EXPIRED)
            await war_service.repo.clear_cartels_pending_war(db, war_id)
            await db.commit()

            if bot:
                msg = "⏳ مهلت پاسخگویی به درخواست Cartel War به پایان رسید و این درخواست منقضی شد."
                for leader_id in (att_leader, def_leader):
                    try:
                        await bot.send_message(chat_id=leader_id, text=msg)
                    except Exception as e:
                        logger.warning("نتوانستیم به لیدر پیام انقضا ارسال کنیم: %s", e)

            logger.info("War ID %d marked as EXPIRED.", war_id)


async def job_check_scheduled_wars(war_service: WarService, bot: Optional[Bot] = None):
    """شروع جنگ‌های برنامه‌ریزی شده پس از گذشت ۳۰ دقیقه"""
    now = datetime.now()
    async with aiosqlite.connect(war_service.db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        async with db.execute(
            """
            SELECT id, attacker_cartel_id, defender_cartel_id 
            FROM cartel_wars 
            WHERE status = 'scheduled' AND starts_at <= ?
            """,
            (now.strftime("%Y-%m-%d %H:%M:%S"),)
        ) as cursor:
            ready_wars = await cursor.fetchall()

        for war_id, c_a_id, c_b_id in ready_wars:
            await war_service.repo.update_war_status(db, war_id, WarStatus.ACTIVE)
            await db.commit()

            cartel_a = await war_service.repo.get_cartel_by_id(db, c_a_id)
            cartel_b = await war_service.repo.get_cartel_by_id(db, c_b_id)
            members_a = await war_service.repo.get_cartel_members(db, c_a_id)
            members_b = await war_service.repo.get_cartel_members(db, c_b_id)

            war_start_msg = (
                "🔥 **جنگ آغاز شد!**\n\n"
                f"🏴 **{cartel_a.name if cartel_a else 'A'}** VS 🏴 **{cartel_b.name if cartel_b else 'B'}**\n\n"
                "برای شرکت در نبرد وارد بخش `⚔️ وار` شوید.\n\n"
                "⏳ **مدت جنگ:** ۶ ساعت"
            )

            if bot:
                for member in members_a + members_b:
                    try:
                        await bot.send_message(chat_id=member.id, text=war_start_msg, parse_mode="Markdown")
                    except Exception:
                        pass

            logger.info("War ID %d transitioned to ACTIVE.", war_id)


async def job_check_active_wars(war_service: WarService, bot: Optional[Bot] = None):
    """پایان دادن به وارهای فعال پس از ۶ ساعت و توزیع جوایز"""
    now = datetime.now()
    async with aiosqlite.connect(war_service.db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        async with db.execute(
            """
            SELECT id, attacker_cartel_id, defender_cartel_id 
            FROM cartel_wars 
            WHERE status = 'active' AND ends_at <= ?
            """,
            (now.strftime("%Y-%m-%d %H:%M:%S"),)
        ) as cursor:
            ending_wars = await cursor.fetchall()

    for war_id, c_a_id, c_b_id in ending_wars:
        winner_id, summary = await war_service.finalize_war(war_id)
        if not summary:
            continue

        async with aiosqlite.connect(war_service.db_path) as db:
            members_a = await war_service.repo.get_cartel_members(db, c_a_id)
            members_b = await war_service.repo.get_cartel_members(db, c_b_id)

        if winner_id is not None:
            result_text = (
                "🏆 **Cartel War به پایان رسید**\n\n"
                f"🏴 **{summary['winner_name']}** پیروز شد!\n\n"
                "📊 **نتیجه نهایی**\n\n"
                f"• {summary['cartel_a_name']}: `{summary['xp_a']}` XP\n"
                f"• {summary['cartel_b_name']}: `{summary['xp_b']}` XP\n\n"
                "🎁 **پاداش اعضای تیم برنده**\n\n"
                "• +50,000 TP\n"
                "• +500 XP کارتل\n"
                "• +300 XP شخصی\n"
                "• +1 🎖 مدال افتخار جنگ\n\n"
                f"🏆 کارتل **{summary['winner_name']}** اکنون `{summary['winner_trophies']}` پیروزی جنگی ثبت کرده است."
            )
        else:
            result_text = (
                "🤝 **Cartel War به پایان رسید — نتیجه: تساوی!**\n\n"
                "📊 **نتیجه نهایی**\n\n"
                f"• {summary['cartel_a_name']}: `{summary['xp_a']}` XP\n"
                f"• {summary['cartel_b_name']}: `{summary['xp_b']}` XP\n\n"
                "به دلیل برابری امتیازات و ضربات، بازی با نتیجه مساوی به پایان رسید."
            )

        if bot:
            for member in members_a + members_b:
                try:
                    await bot.send_message(chat_id=member.id, text=result_text, parse_mode="Markdown")
                except Exception:
                    pass

        logger.info("War ID %d finalized. Winner: %s", war_id, summary.get("winner_name"))


async def job_daily_midnight_reset(war_service: WarService):
    """ریست روزانه در ساعت ۰۰:۰۰ بامداد"""
    async with aiosqlite.connect(war_service.db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("UPDATE cartels SET daily_war_count = 0")
        await db.execute(
            """
            UPDATE cartels SET pending_war_id = NULL 
            WHERE pending_war_id IS NOT NULL 
            AND pending_war_id NOT IN (
                SELECT id FROM cartel_wars WHERE status IN ('pending', 'scheduled', 'active')
            )
            """
        )
        await db.commit()
    logger.info("Daily midnight reset completed.")


def setup_war_scheduler(
    scheduler: AsyncIOScheduler,
    war_service: WarService,
    bot: Optional[Bot] = None
) -> None:
    """ثبت تمام جاب‌های زمان‌بندی Cartel War در APScheduler"""
    scheduler.add_job(
        job_check_pending_wars,
        trigger=IntervalTrigger(minutes=1),
        args=[war_service, bot],
        id="war_check_pending",
        replace_existing=True
    )
    scheduler.add_job(
        job_check_scheduled_wars,
        trigger=IntervalTrigger(minutes=1),
        args=[war_service, bot],
        id="war_check_scheduled",
        replace_existing=True
    )
    scheduler.add_job(
        job_check_active_wars,
        trigger=IntervalTrigger(minutes=1),
        args=[war_service, bot],
        id="war_check_active",
        replace_existing=True
    )
    scheduler.add_job(
        job_daily_midnight_reset,
        trigger=CronTrigger(hour=0, minute=0),
        args=[war_service],
        id="war_daily_reset",
        replace_existing=True
    )
