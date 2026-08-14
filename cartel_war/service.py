"""
Service Layer for Cartel War System.
Contains game rules, validation, combat formulas, rewards, and concurrency locks.
"""
import asyncio
from datetime import datetime, timedelta
import logging
import random
from typing import Optional, Tuple, Dict, List
import aiosqlite

from cartel_war.models import (
    Cartel,
    UserProfile,
    CartelWar,
    WarStatus,
    BattleResult
)
from cartel_war.repository import WarRepository

logger = logging.getLogger(__name__)


class WarService:
    def __init__(self, db_path: str, repo: WarRepository):
        self.db_path = db_path
        self.repo = repo
        self._user_locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        async with self._global_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]

    @staticmethod
    def get_balance_multiplier(attacker_team_size: int, defender_team_size: int, is_attacker_smaller: bool) -> float:
        """
        محاسبه ضریب بالانس برای تیمی که تعداد اعضای کمتری دارد:
        0-4: 1.0x
        5-9: 1.15x
        10-14: 1.30x
        15+: 1.50x
        """
        diff = abs(attacker_team_size - defender_team_size)
        if diff <= 4:
            mult = 1.0
        elif diff <= 9:
            mult = 1.15
        elif diff <= 14:
            mult = 1.30
        else:
            mult = 1.50

        return mult if is_attacker_smaller else 1.0

    async def initiate_war_request(
        self,
        user_id: int,
        target_cartel_name: str
    ) -> Tuple[bool, str, Optional[int], Optional[int]]:
        """
        ارسال درخواست کارتل وار توسط رهبر
        خروجی: (موفقیت, پیام, war_id, defender_leader_id)
        """
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")

            # ۱. بررسی کاربر و کارتل خودی
            user = await self.repo.get_user_by_id(db, user_id)
            if not user or not user.cartel_id:
                return False, "❌ شما عضو هیچ کارتلی نیستید!", None, None

            attacker_cartel = await self.repo.get_cartel_by_id(db, user.cartel_id)
            if not attacker_cartel:
                return False, "❌ کارتل شما یافت نشد!", None, None

            if attacker_cartel.leader_id != user_id:
                return False, "❌ فقط رهبر کارتل مجاز به اعلان جنگ است!", None, None

            if attacker_cartel.pending_war_id is not None:
                return False, "❌ کارتل شما در حال حاضر یک درخواست یا جنگ فعال دارد!", None, None

            if attacker_cartel.daily_war_count >= 1:
                return False, "❌ کارتل شما سهمیه ۱ وار در روز را مصرف کرده است!", None, None

            # ۲. بررسی کارتل هدف
            target_cartel = await self.repo.get_cartel_by_name(db, target_cartel_name)
            if not target_cartel:
                return False, f"❌ کارتل هدف با نام «{target_cartel_name}» پیدا نشد!", None, None

            if target_cartel.id == attacker_cartel.id:
                return False, "❌ شما نمی‌توانید به کارتل خودی اعلان جنگ دهید!", None, None

            if target_cartel.pending_war_id is not None:
                return False, "❌ کارتل حریف در حال حاضر درگیر یک وار یا درخواست دیگر است!", None, None

            if target_cartel.daily_war_count >= 1:
                return False, "❌ کارتل حریف سهمیه جنگ امروز خود را مصرف کرده است!", None, None

            # ۳. ثبت در دیتابیس
            expires_at = now + timedelta(hours=1)
            war_id = await self.repo.create_war_request(
                db,
                attacker_cartel_id=attacker_cartel.id,
                defender_cartel_id=target_cartel.id,
                attacker_leader_id=attacker_cartel.leader_id,
                defender_leader_id=target_cartel.leader_id,
                requested_at=now,
                expires_at=expires_at
            )
            await db.commit()

            return True, "✅ درخواست جنگ با موفقیت برای رهبر کارتل حریف ارسال شد.", war_id, target_cartel.leader_id

    async def handle_war_response(
        self,
        user_id: int,
        war_id: int,
        accept: bool
    ) -> Tuple[bool, str, Optional[CartelWar]]:
        """
        پاسخ به درخواست وار (قبول یا رد) توسط رهبر مدافع
        """
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            war = await self.repo.get_war_by_id(db, war_id)
            if not war:
                return False, "❌ درخواست وار یافت نشد!", None

            if war.status != WarStatus.PENDING:
                return False, f"❌ این درخواست قبلاً تعیین وضعیت شده است ({war.status.value})!", None

            if war.defender_leader_id != user_id:
                return False, "❌ فقط رهبر کارتل مدافع می‌تواند به این درخواست پاسخ دهد!", None

            if now > war.expires_at:
                await self.repo.update_war_status(db, war_id, WarStatus.EXPIRED)
                await self.repo.clear_cartels_pending_war(db, war_id)
                await db.commit()
                return False, "⏳ مهلت پاسخگویی به این درخواست (۱ ساعت) به پایان رسیده است!", None

            if not accept:
                # رد درخواست: وضعیت rejected، سهمیه روزانه مصرف نمی‌شود، pending آزاد می‌شود
                await self.repo.update_war_status(db, war_id, WarStatus.REJECTED)
                await self.repo.clear_cartels_pending_war(db, war_id)
                await db.commit()
                return True, "❌ درخواست جنگ رد شد.", war

            # قبول درخواست: وضعیت scheduled، شروع ۳۰ دقیقه بعد، پایان ۶ ساعت بعد
            starts_at = now + timedelta(minutes=30)
            ends_at = starts_at + timedelta(hours=6)

            await self.repo.update_war_status(
                db,
                war_id=war_id,
                status=WarStatus.SCHEDULED,
                accepted_at=now,
                starts_at=starts_at,
                ends_at=ends_at
            )
            # سهمیه روزانه هر دو کارتل با پذیرش مصرف می‌شود
            await self.repo.increment_daily_war_count(db, [war.attacker_cartel_id, war.defender_cartel_id])
            await db.commit()

            updated_war = await self.repo.get_war_by_id(db, war_id)
            return True, "⚔️ درخواست جنگ پذیرفته شد! جنگ تا ۳۰ دقیقه دیگر آغاز خواهد شد.", updated_war

    async def execute_attack(
        self,
        user_id: int,
        war_id: int
    ) -> Tuple[bool, str, Optional[BattleResult]]:
        """
        اجرای حمله وار توسط بازیکن با قفل همزمانی
        """
        lock = await self._get_user_lock(user_id)
        async with lock:
            now = datetime.now()
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA foreign_keys = ON;")

                # ۱. اعتبارسنجی وار
                war = await self.repo.get_war_by_id(db, war_id)
                if not war:
                    return False, "❌ چنین جنگی وجود ندارد!", None

                if war.status != WarStatus.ACTIVE:
                    return False, f"❌ این جنگ در وضعیت فعال قرار ندارد (وضعیت: {war.status.value})!", None

                if war.ends_at and now >= war.ends_at:
                    return False, "⏳ زمان جنگ به پایان رسیده است!", None

                # ۲. اعتبارسنجی مهاجم
                attacker = await self.repo.get_user_by_id(db, user_id)
                if not attacker or not attacker.cartel_id:
                    return False, "❌ شما عضو هیچ کارتلی نیستید!", None

                is_attacker_side = (attacker.cartel_id == war.attacker_cartel_id)
                is_defender_side = (attacker.cartel_id == war.defender_cartel_id)

                if not is_attacker_side and not is_defender_side:
                    return False, "❌ کارتل شما در این جنگ حضور ندارد!", None

                # ۳. قانون ۲۴ ساعت عضویت
                if attacker.cartel_joined_at:
                    elapsed_joined = (now - attacker.cartel_joined_at).total_seconds()
                    if elapsed_joined < 86400:
                        rem_hours = round((86400 - elapsed_joined) / 3600, 1)
                        return False, f"⏳ شما به تازگی عضو شدید (حداقل ۲۴ ساعت عضویت الزامی است). تا {rem_hours} ساعت دیگر اجازه شرکت در وار را ندارید.", None

                # ۴. بررسی کول‌دان ۵ دقیقه‌ای فردی
                last_attack = await self.repo.get_user_last_attack_time(db, user_id, war_id)
                if last_attack:
                    elapsed = (now - last_attack).total_seconds()
                    if elapsed < 300:
                        rem_sec = int(300 - elapsed)
                        mins, secs = divmod(rem_sec, 60)
                        return False, f"⏳ کول‌دان حمله وار فعال است! زمان باقی‌مانده: {mins:02d}:{secs:02d}", None

                # ۵. انتخاب رندوم حریف از کارتل مقابل (آنلاین/آفلاین)
                opponent_cartel_id = war.defender_cartel_id if is_attacker_side else war.attacker_cartel_id
                opponent_members = await self.repo.get_cartel_members(db, opponent_cartel_id)

                if not opponent_members:
                    return False, "❌ کارتل حریف عضوی برای حمله ندارد!", None

                defender = random.choice(opponent_members)

                # ۶. ضریب بالانس
                attacker_members = await self.repo.get_cartel_members(db, attacker.cartel_id)
                is_attacker_smaller = len(attacker_members) < len(opponent_members)
                balance_mult = self.get_balance_multiplier(
                    len(attacker_members), len(opponent_members), is_attacker_smaller
                )

                # ۷. الگوریتم نبرد
                # attack_score = (power + lvl * 5) * uniform(0.85, 1.15)
                att_rand = random.uniform(0.85, 1.15)
                def_rand = random.uniform(0.85, 1.15)

                attacker_score = (attacker.attack_power + (attacker.level * 5)) * att_rand
                defender_score = (defender.defense_power + (defender.level * 5)) * def_rand

                is_win = attacker_score > defender_score

                # ۸. پاداش و XP
                if is_win:
                    base_xp = 15
                    medals_gained = 2
                    tp_reward = 5000
                else:
                    base_xp = 5
                    medals_gained = 1
                    tp_reward = 0

                xp_gained = int(base_xp * balance_mult)

                # ۹. ثبت اتمیک
                await self.repo.record_attack_result(
                    db=db,
                    war_id=war_id,
                    attacker_id=attacker.id,
                    defender_id=defender.id,
                    is_attacker_side=is_attacker_side,
                    is_win=is_win,
                    xp_gained=xp_gained,
                    medals_gained=medals_gained,
                    tp_reward=tp_reward,
                    now=now
                )
                await db.commit()

                result = BattleResult(
                    is_win=is_win,
                    attacker_score=round(attacker_score, 1),
                    defender_score=round(defender_score, 1),
                    xp_gained=xp_gained,
                    medals_gained=medals_gained,
                    tp_reward=tp_reward,
                    attacker_name=attacker.full_name,
                    defender_name=defender.full_name,
                    balance_multiplier=balance_mult
                )

                return True, "✅ نبرد با موفقیت انجام شد.", result

    async def finalize_war(self, war_id: int) -> Tuple[Optional[int], Dict]:
        """
        پایان دادن به جنگ، تعیین برنده و توزیع جوایز
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            war = await self.repo.get_war_by_id(db, war_id)
            if not war or war.status != WarStatus.ACTIVE:
                return None, {}

            # شمارش شرکت‌کنندگان فعال
            async with db.execute(
                """
                SELECT COUNT(DISTINCT attacker_id) FROM war_attack_logs 
                WHERE war_id = ? AND attacker_id IN (SELECT id FROM users WHERE cartel_id = ?)
                """,
                (war_id, war.attacker_cartel_id)
            ) as c:
                row = await c.fetchone()
                attacker_part = row[0] if row else 0

            async with db.execute(
                """
                SELECT COUNT(DISTINCT attacker_id) FROM war_attack_logs 
                WHERE war_id = ? AND attacker_id IN (SELECT id FROM users WHERE cartel_id = ?)
                """,
                (war_id, war.defender_cartel_id)
            ) as c:
                row = await c.fetchone()
                defender_part = row[0] if row else 0

            # تعیین برنده
            winner_id = None
            if war.attacker_xp > war.defender_xp:
                winner_id = war.attacker_cartel_id
            elif war.defender_xp > war.attacker_xp:
                winner_id = war.defender_cartel_id
            else:
                # تساوی در XP -> مقایسه تعداد حملات موفق
                if war.attacker_success_hits > war.defender_success_hits:
                    winner_id = war.attacker_cartel_id
                elif war.defender_success_hits > war.attacker_success_hits:
                    winner_id = war.defender_cartel_id
                else:
                    # تساوی در حملات موفق -> مقایسه شرکت‌کنندگان فعال
                    if attacker_part > defender_part:
                        winner_id = war.attacker_cartel_id
                    elif defender_part > attacker_part:
                        winner_id = war.defender_cartel_id
                    else:
                        winner_id = None  # مساوی قطعی

            # بروزرسانی جنگ
            await self.repo.update_war_status(db, war_id, WarStatus.FINISHED, winner_cartel_id=winner_id)
            await self.repo.clear_cartels_pending_war(db, war_id)

            # افزایش تعداد کل جنگ‌ها برای هر دو کارتل
            await db.execute(
                "UPDATE cartels SET total_wars = total_wars + 1 WHERE id IN (?, ?)",
                (war.attacker_cartel_id, war.defender_cartel_id)
            )

            # واریز پاداش‌ها
            if winner_id is not None:
                # پاداش کارتل برنده: +1 War Trophy, +1 War Win, +500 Cartel XP
                await db.execute(
                    """
                    UPDATE cartels 
                    SET war_trophies = war_trophies + 1, war_wins = war_wins + 1, xp = xp + 500 
                    WHERE id = ?
                    """,
                    (winner_id,)
                )

                # پاداش تمام اعضای کارتل برنده: +50k TP, +300 XP شخصی, +1 مدال افتخار
                await db.execute(
                    """
                    UPDATE users 
                    SET tp = tp + 50000, personal_xp = personal_xp + 300, war_medals = war_medals + 1 
                    WHERE cartel_id = ?
                    """,
                    (winner_id,)
                )

            await db.commit()

            cartel_a = await self.repo.get_cartel_by_id(db, war.attacker_cartel_id)
            cartel_b = await self.repo.get_cartel_by_id(db, war.defender_cartel_id)

            winner_name = "تساوی"
            trophies = 0
            if winner_id == cartel_a.id:
                winner_name = cartel_a.name
                trophies = cartel_a.war_trophies
            elif winner_id == cartel_b.id:
                winner_name = cartel_b.name
                trophies = cartel_b.war_trophies

            summary = {
                "war_id": war_id,
                "winner_id": winner_id,
                "winner_name": winner_name,
                "cartel_a_name": cartel_a.name if cartel_a else "کارتل ۱",
                "cartel_b_name": cartel_b.name if cartel_b else "کارتل ۲",
                "xp_a": war.attacker_xp,
                "xp_b": war.defender_xp,
                "hits_a": war.attacker_success_hits,
                "hits_b": war.defender_success_hits,
                "part_a": attacker_part,
                "part_b": defender_part,
                "winner_trophies": trophies
            }
            return winner_id, summary
