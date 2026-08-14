"""
Comprehensive Automated Test Suite for Cartel War System.
Tests all business logic, combat rules, cooldowns, balance multipliers, concurrency locks, tie-breaking, and rewards.
"""
import asyncio
from datetime import datetime, timedelta
import os
import unittest
import aiosqlite

from cartel_war.database import init_cartel_war_db
from cartel_war.models import Cartel, WarStatus, UserProfile
from cartel_war.repository import WarRepository
from cartel_war.service import WarService
from cartel_war.scheduler import (
    job_check_pending_wars,
    job_check_scheduled_wars,
    job_check_active_wars,
    job_daily_midnight_reset
)


class TestCartelWarSystem(unittest.IsolatedAsyncioTestCase):
    DB_PATH = "test_war_system.db"

    async def asyncSetUp(self):
        if os.path.exists(self.DB_PATH):
            os.remove(self.DB_PATH)

        await init_cartel_war_db(self.DB_PATH)
        self.repo = WarRepository(self.DB_PATH)
        self.service = WarService(self.DB_PATH, self.repo)

        # ساخت داده‌های اولیه برای تست
        async with aiosqlite.connect(self.DB_PATH) as db:
            # ۲ کارتل
            await db.execute("INSERT INTO cartels (id, name, leader_id) VALUES (1, 'گرگ‌های شب', 101)")
            await db.execute("INSERT INTO cartels (id, name, leader_id) VALUES (2, 'شاهین‌های سرخ', 201)")

            # اعضای کارتل ۱ (۳ نفر: لیدر ۱۰۱، عضو ۱۰۲ با عضویت قدیمی، عضو ۱۰۳ تازه وارد)
            old_time = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
            recent_time = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

            await db.execute(
                "INSERT INTO users (id, full_name, cartel_id, cartel_joined_at, attack_power, defense_power, level) "
                "VALUES (101, 'رهبر گرگ‌ها', 1, ?, 300, 250, 10)", (old_time,)
            )
            await db.execute(
                "INSERT INTO users (id, full_name, cartel_id, cartel_joined_at, attack_power, defense_power, level) "
                "VALUES (102, 'جنگجوی گرگ', 1, ?, 200, 180, 8)", (old_time,)
            )
            await db.execute(
                "INSERT INTO users (id, full_name, cartel_id, cartel_joined_at, attack_power, defense_power, level) "
                "VALUES (103, 'عضو تازه گرگ', 1, ?, 150, 150, 5)", (recent_time,)
            )

            # اعضای کارتل ۲ (۱۰ نفر: اختلاف ۷ نفر با کارتل ۱ -> ضریب 1.15x)
            await db.execute(
                "INSERT INTO users (id, full_name, cartel_id, cartel_joined_at, attack_power, defense_power, level) "
                "VALUES (201, 'رهبر شاهین‌ها', 2, ?, 280, 260, 10)", (old_time,)
            )
            for i in range(2, 11):
                uid = 200 + i
                await db.execute(
                    "INSERT INTO users (id, full_name, cartel_id, cartel_joined_at, attack_power, defense_power, level) "
                    "VALUES (?, ?, 2, ?, 180, 160, 7)", (uid, f"جنگجوی شاهین {i}", old_time)
                )

            await db.commit()

    async def asyncTearDown(self):
        if os.path.exists(self.DB_PATH):
            try:
                os.remove(self.DB_PATH)
            except Exception:
                pass

    async def test_balance_multiplier(self):
        """تست ضرایب بالانس برای تیم‌های کوچک‌تر"""
        self.assertEqual(WarService.get_balance_multiplier(10, 12, True), 1.0)    # اختلاف ۲ -> 1.0x
        self.assertEqual(WarService.get_balance_multiplier(5, 12, True), 1.15)    # اختلاف ۷ -> 1.15x
        self.assertEqual(WarService.get_balance_multiplier(3, 15, True), 1.30)    # اختلاف ۱۲ -> 1.30x
        self.assertEqual(WarService.get_balance_multiplier(2, 20, True), 1.50)    # اختلاف ۱۸ -> 1.50x
        self.assertEqual(WarService.get_balance_multiplier(5, 12, False), 1.0)   # برای تیم بزرگتر ضریب 1.0 است

    async def test_initiate_war_rules(self):
        """تست قوانین ارسال درخواست وار"""
        # ۱. عضو معمولی اجازه درخواست ندارد
        ok, msg, _, _ = await self.service.initiate_war_request(102, "شاهین‌های سرخ")
        self.assertFalse(ok)
        self.assertIn("رهبر", msg)

        # ۲. درخواست به کارتل ناموجود
        ok, msg, _, _ = await self.service.initiate_war_request(101, "کارتل خیالی")
        self.assertFalse(ok)
        self.assertIn("پیدا نشد", msg)

        # ۳. درخواست به کارتل خودی
        ok, msg, _, _ = await self.service.initiate_war_request(101, "گرگ‌های شب")
        self.assertFalse(ok)
        self.assertIn("خودی", msg)

        # ۴. درخواست معتبر
        ok, msg, war_id, def_leader = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        self.assertTrue(ok)
        self.assertIsNotNone(war_id)
        self.assertEqual(def_leader, 201)

        # ۵. ارسال درخواست مجدد در حالی که درخواست فعال دارد
        ok2, msg2, _, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        self.assertFalse(ok2)
        self.assertIn("فعال", msg2)

    async def test_rejection_flow(self):
        """تست رد درخواست وار و بازگشت سهمیه روزانه"""
        ok, _, war_id, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        self.assertTrue(ok)

        # رهبر مدافع درخواست را رد می‌کند
        ok_rej, msg_rej, _ = await self.service.handle_war_response(201, war_id, accept=False)
        self.assertTrue(ok_rej)

        async with aiosqlite.connect(self.DB_PATH) as db:
            c1 = await self.repo.get_cartel_by_id(db, 1)
            c2 = await self.repo.get_cartel_by_id(db, 2)
            # pending_war_id باید خالی شده باشد
            self.assertIsNone(c1.pending_war_id)
            self.assertIsNone(c2.pending_war_id)
            # سهمیه روزانه مصرف نشده باشد
            self.assertEqual(c1.daily_war_count, 0)
            self.assertEqual(c2.daily_war_count, 0)

        # لیدر مهاجم بلافاصله می‌تواند مجدداً درخواست دهد
        ok_new, _, new_war_id, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        self.assertTrue(ok_new)

    async def test_acceptance_and_scheduling(self):
        """تست قبول درخواست و ورود به فاز SCHEDULED"""
        _, _, war_id, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        ok_acc, msg_acc, war = await self.service.handle_war_response(201, war_id, accept=True)
        self.assertTrue(ok_acc)
        self.assertEqual(war.status, WarStatus.SCHEDULED)

        async with aiosqlite.connect(self.DB_PATH) as db:
            c1 = await self.repo.get_cartel_by_id(db, 1)
            c2 = await self.repo.get_cartel_by_id(db, 2)
            # با قبول شدن وار سهمیه روزانه ۱ مصرف می‌شود
            self.assertEqual(c1.daily_war_count, 1)
            self.assertEqual(c2.daily_war_count, 1)

    async def test_attack_mechanics_and_cooldown(self):
        """تست مکانیک حمله، قانون ۲۴ ساعت عضویت، کول‌دان ۵ دقیقه و قفل همزمانی"""
        _, _, war_id, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        await self.service.handle_war_response(201, war_id, accept=True)

        # فعال کردن دستی وار
        async with aiosqlite.connect(self.DB_PATH) as db:
            await self.repo.update_war_status(db, war_id, WarStatus.ACTIVE)
            await db.commit()

        # ۱. عضوی که کمتر از ۲۴ ساعت عضو شده اجازه حمله ندارد (کاربر ۱۰۳)
        ok, msg, _ = await self.service.execute_attack(103, war_id)
        self.assertFalse(ok)
        self.assertIn("۲۴ ساعت", msg)

        # ۲. حمله موفق جنگجوی مجاز (کاربر ۱۰۲)
        ok, msg, result = await self.service.execute_attack(102, war_id)
        self.assertTrue(ok)
        self.assertIsNotNone(result)
        self.assertEqual(result.balance_multiplier, 1.15)  # ضریب تیم کوچکتر
        self.assertGreater(result.xp_gained, 0)
        self.assertGreater(result.medals_gained, 0)

        # ۳. تست کول‌دان: تلاش برای حمله بلافاصله باید رد شود
        ok_cd, msg_cd, _ = await self.service.execute_attack(102, war_id)
        self.assertFalse(ok_cd)
        self.assertIn("کول‌دان", msg_cd)

        # ۴. تست قفل همزمانی با اجرای همزمان چند حمله برای یک کاربر
        async def try_attack():
            return await self.service.execute_attack(101, war_id)

        results = await asyncio.gather(try_attack(), try_attack(), try_attack())
        success_count = sum(1 for r in results if r[0] is True)
        self.assertEqual(success_count, 1, "فقط دقیقاً ۱ حمله همزمان باید موفق شود و بقیه باید توسط قفل و کول‌دان بلاک شوند!")

    async def test_tie_breaking_rules(self):
        """تست قوانین ۳ مرحله‌ای تعیین برنده در صورت تساوی"""
        # حالت ۱: تساوی در XP، برتری در تعداد ضربات موفق
        _, _, war_id1, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        await self.service.handle_war_response(201, war_id1, accept=True)
        async with aiosqlite.connect(self.DB_PATH) as db:
            await self.repo.update_war_status(db, war_id1, WarStatus.ACTIVE)
            await db.execute(
                "UPDATE cartel_wars SET attacker_xp = 100, defender_xp = 100, "
                "attacker_success_hits = 6, defender_success_hits = 4 WHERE id = ?",
                (war_id1,)
            )
            await db.commit()

        winner1, _ = await self.service.finalize_war(war_id1)
        self.assertEqual(winner1, 1, "تیم ۱ به دلیل ضربات موفق بیشتر باید برنده شود")

        # حالت ۲: تساوی در XP و ضربات، برتری در تعداد شرکت‌کنندگان فعال
        # ریست روزانه برای امکان تست بعدی
        await job_daily_midnight_reset(self.service)
        _, _, war_id2, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        await self.service.handle_war_response(201, war_id2, accept=True)
        async with aiosqlite.connect(self.DB_PATH) as db:
            await self.repo.update_war_status(db, war_id2, WarStatus.ACTIVE)
            await db.execute(
                "UPDATE cartel_wars SET attacker_xp = 100, defender_xp = 100, "
                "attacker_success_hits = 5, defender_success_hits = 5 WHERE id = ?",
                (war_id2,)
            )
            # ثبت لاگ برای شرکت‌کنندگان: تیم ۱ دو شرکت‌کننده (101 و 102)، تیم ۲ یک شرکت‌کننده (201)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await db.execute("INSERT INTO war_attack_logs (war_id, attacker_id, defender_id, success, xp_gained, medals_gained, created_at) VALUES (?, 101, 201, 1, 15, 2, ?)", (war_id2, now_str))
            await db.execute("INSERT INTO war_attack_logs (war_id, attacker_id, defender_id, success, xp_gained, medals_gained, created_at) VALUES (?, 102, 201, 1, 15, 2, ?)", (war_id2, now_str))
            await db.execute("INSERT INTO war_attack_logs (war_id, attacker_id, defender_id, success, xp_gained, medals_gained, created_at) VALUES (?, 201, 101, 1, 15, 2, ?)", (war_id2, now_str))
            await db.commit()

        winner2, _ = await self.service.finalize_war(war_id2)
        self.assertEqual(winner2, 1, "تیم ۱ به دلیل شرکت‌کنندگان فعال بیشتر باید برنده شود")

        # حالت ۳: برابری کامل در همه موارد -> تساوی
        await job_daily_midnight_reset(self.service)
        _, _, war_id3, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        await self.service.handle_war_response(201, war_id3, accept=True)
        async with aiosqlite.connect(self.DB_PATH) as db:
            await self.repo.update_war_status(db, war_id3, WarStatus.ACTIVE)
            await db.execute(
                "UPDATE cartel_wars SET attacker_xp = 50, defender_xp = 50, "
                "attacker_success_hits = 3, defender_success_hits = 3 WHERE id = ?",
                (war_id3,)
            )
            await db.commit()

        winner3, summary3 = await self.service.finalize_war(war_id3)
        self.assertIsNone(winner3, "در صورت برابری کامل باید تساوی ثبت شود")
        self.assertEqual(summary3["winner_name"], "تساوی")

    async def test_war_finalization_and_rewards(self):
        """تست پایان وار، تعیین برنده و اعطای پاداش‌ها"""
        _, _, war_id, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        await self.service.handle_war_response(201, war_id, accept=True)

        async with aiosqlite.connect(self.DB_PATH) as db:
            await self.repo.update_war_status(db, war_id, WarStatus.ACTIVE)
            # ثبت امتیاز برای کارتل ۱
            await db.execute("UPDATE cartel_wars SET attacker_xp = 150, defender_xp = 80 WHERE id = ?", (war_id,))
            await db.commit()

        winner_id, summary = await self.service.finalize_war(war_id)
        self.assertEqual(winner_id, 1)
        self.assertEqual(summary["winner_name"], "گرگ‌های شب")

        # بررسی واریز پاداش‌ها
        async with aiosqlite.connect(self.DB_PATH) as db:
            c1 = await self.repo.get_cartel_by_id(db, 1)
            self.assertEqual(c1.war_wins, 1)
            self.assertEqual(c1.war_trophies, 1)
            self.assertEqual(c1.total_wars, 1)
            self.assertEqual(c1.win_rate, 100.0)

            # پاداش اعضای تیم ۱
            u101 = await self.repo.get_user_by_id(db, 101)
            self.assertEqual(u101.tp, 50000)
            self.assertEqual(u101.personal_xp, 300)
            self.assertEqual(u101.war_medals, 1)

    async def test_scheduler_jobs_and_midnight_reset(self):
        """تست عملکرد جاب‌های زمان‌بندی و ریست شبانه"""
        # ۱. تست انقضای خودکار درخواست وار
        _, _, war_id, _ = await self.service.initiate_war_request(101, "شاهین‌های سرخ")
        past_time = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.DB_PATH) as db:
            await db.execute("UPDATE cartel_wars SET expires_at = ? WHERE id = ?", (past_time, war_id))
            await db.commit()

        await job_check_pending_wars(self.service, bot=None)

        async with aiosqlite.connect(self.DB_PATH) as db:
            war = await self.repo.get_war_by_id(db, war_id)
            self.assertEqual(war.status, WarStatus.EXPIRED)

        # ۲. تست ریست شبانه سهمیه روزانه
        async with aiosqlite.connect(self.DB_PATH) as db:
            await db.execute("UPDATE cartels SET daily_war_count = 1")
            await db.commit()

        await job_daily_midnight_reset(self.service)

        async with aiosqlite.connect(self.DB_PATH) as db:
            c1 = await self.repo.get_cartel_by_id(db, 1)
            self.assertEqual(c1.daily_war_count, 0)


if __name__ == "__main__":
    unittest.main()
