"""
Repository Layer for Cartel War System.
"""
from datetime import datetime
import logging
from typing import Optional, List, Tuple
import aiosqlite

from cartel_war.models import (
    Cartel,
    UserProfile,
    CartelWar,
    WarStatus,
    WarAttackLog,
    WarAttackCooldown
)

logger = logging.getLogger(__name__)


def parse_datetime(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")


class WarRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def get_cartel_by_id(self, db: aiosqlite.Connection, cartel_id: int) -> Optional[Cartel]:
        async with db.execute(
            """
            SELECT id, name, leader_id, xp, war_trophies, war_wins, total_wars, 
                   war_medals_total, daily_war_count, pending_war_id, created_at 
            FROM cartels WHERE id = ?
            """,
            (cartel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Cartel(
                id=row[0], name=row[1], leader_id=row[2], xp=row[3], war_trophies=row[4],
                war_wins=row[5], total_wars=row[6], war_medals_total=row[7],
                daily_war_count=row[8], pending_war_id=row[9], created_at=parse_datetime(row[10])
            )

    async def get_cartel_by_name(self, db: aiosqlite.Connection, name: str) -> Optional[Cartel]:
        async with db.execute(
            """
            SELECT id, name, leader_id, xp, war_trophies, war_wins, total_wars, 
                   war_medals_total, daily_war_count, pending_war_id, created_at 
            FROM cartels WHERE LOWER(name) = LOWER(?)
            """,
            (name.strip(),)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Cartel(
                id=row[0], name=row[1], leader_id=row[2], xp=row[3], war_trophies=row[4],
                war_wins=row[5], total_wars=row[6], war_medals_total=row[7],
                daily_war_count=row[8], pending_war_id=row[9], created_at=parse_datetime(row[10])
            )

    async def get_user_by_id(self, db: aiosqlite.Connection, user_id: int) -> Optional[UserProfile]:
        async with db.execute(
            """
            SELECT id, username, full_name, cartel_id, cartel_joined_at, attack_power, 
                   defense_power, level, tp, personal_xp, war_medals, war_attacks, war_wins 
            FROM users WHERE id = ?
            """,
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return UserProfile(
                id=row[0], username=row[1], full_name=row[2], cartel_id=row[3],
                cartel_joined_at=parse_datetime(row[4]), attack_power=row[5],
                defense_power=row[6], level=row[7], tp=row[8], personal_xp=row[9],
                war_medals=row[10], war_attacks=row[11], war_wins=row[12]
            )

    async def get_cartel_members(self, db: aiosqlite.Connection, cartel_id: int) -> List[UserProfile]:
        async with db.execute(
            """
            SELECT id, username, full_name, cartel_id, cartel_joined_at, attack_power, 
                   defense_power, level, tp, personal_xp, war_medals, war_attacks, war_wins 
            FROM users WHERE cartel_id = ?
            """,
            (cartel_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                UserProfile(
                    id=row[0], username=row[1], full_name=row[2], cartel_id=row[3],
                    cartel_joined_at=parse_datetime(row[4]), attack_power=row[5],
                    defense_power=row[6], level=row[7], tp=row[8], personal_xp=row[9],
                    war_medals=row[10], war_attacks=row[11], war_wins=row[12]
                )
                for row in rows
            ]

    async def get_war_by_id(self, db: aiosqlite.Connection, war_id: int) -> Optional[CartelWar]:
        async with db.execute(
            """
            SELECT id, attacker_cartel_id, defender_cartel_id, attacker_leader_id, defender_leader_id, 
                   status, requested_at, expires_at, accepted_at, starts_at, ends_at, attacker_xp, 
                   defender_xp, attacker_success_hits, defender_success_hits, attacker_participants, 
                   defender_participants, winner_cartel_id 
            FROM cartel_wars WHERE id = ?
            """,
            (war_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return CartelWar(
                id=row[0], attacker_cartel_id=row[1], defender_cartel_id=row[2],
                attacker_leader_id=row[3], defender_leader_id=row[4], status=WarStatus(row[5]),
                requested_at=parse_datetime(row[6]), expires_at=parse_datetime(row[7]),
                accepted_at=parse_datetime(row[8]), starts_at=parse_datetime(row[9]),
                ends_at=parse_datetime(row[10]), attacker_xp=row[11], defender_xp=row[12],
                attacker_success_hits=row[13], defender_success_hits=row[14],
                attacker_participants=row[15], defender_participants=row[16],
                winner_cartel_id=row[17]
            )

    async def create_war_request(
        self,
        db: aiosqlite.Connection,
        attacker_cartel_id: int,
        defender_cartel_id: int,
        attacker_leader_id: int,
        defender_leader_id: int,
        requested_at: datetime,
        expires_at: datetime
    ) -> int:
        async with db.execute(
            """
            INSERT INTO cartel_wars (
                attacker_cartel_id, defender_cartel_id, attacker_leader_id, defender_leader_id, 
                status, requested_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (attacker_cartel_id, defender_cartel_id, attacker_leader_id, defender_leader_id,
             WarStatus.PENDING.value, requested_at.strftime("%Y-%m-%d %H:%M:%S"),
             expires_at.strftime("%Y-%m-%d %H:%M:%S"))
        ) as cursor:
            war_id = cursor.lastrowid

        await db.execute(
            "UPDATE cartels SET pending_war_id = ? WHERE id IN (?, ?)",
            (war_id, attacker_cartel_id, defender_cartel_id)
        )
        return war_id

    async def update_war_status(
        self,
        db: aiosqlite.Connection,
        war_id: int,
        status: WarStatus,
        accepted_at: Optional[datetime] = None,
        starts_at: Optional[datetime] = None,
        ends_at: Optional[datetime] = None,
        winner_cartel_id: Optional[int] = None
    ) -> None:
        params = [status.value]
        query = "UPDATE cartel_wars SET status = ?"
        
        if accepted_at:
            query += ", accepted_at = ?"
            params.append(accepted_at.strftime("%Y-%m-%d %H:%M:%S"))
        if starts_at:
            query += ", starts_at = ?"
            params.append(starts_at.strftime("%Y-%m-%d %H:%M:%S"))
        if ends_at:
            query += ", ends_at = ?"
            params.append(ends_at.strftime("%Y-%m-%d %H:%M:%S"))
        if winner_cartel_id is not None:
            query += ", winner_cartel_id = ?"
            params.append(winner_cartel_id)
            
        query += " WHERE id = ?"
        params.append(war_id)
        await db.execute(query, tuple(params))

    async def clear_cartels_pending_war(self, db: aiosqlite.Connection, war_id: int) -> None:
        await db.execute("UPDATE cartels SET pending_war_id = NULL WHERE pending_war_id = ?", (war_id,))

    async def increment_daily_war_count(self, db: aiosqlite.Connection, cartel_ids: List[int]) -> None:
        placeholders = ",".join("?" * len(cartel_ids))
        await db.execute(
            f"UPDATE cartels SET daily_war_count = daily_war_count + 1 WHERE id IN ({placeholders})",
            tuple(cartel_ids)
        )

    async def get_user_last_attack_time(self, db: aiosqlite.Connection, user_id: int, war_id: int) -> Optional[datetime]:
        async with db.execute(
            "SELECT last_attack_at FROM war_attack_cooldowns WHERE user_id = ? AND war_id = ?",
            (user_id, war_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return parse_datetime(row[0])
            return None

    async def set_user_attack_cooldown(self, db: aiosqlite.Connection, user_id: int, war_id: int, attack_time: datetime) -> None:
        await db.execute(
            """
            INSERT INTO war_attack_cooldowns (user_id, war_id, last_attack_at) VALUES (?, ?, ?) 
            ON CONFLICT(user_id, war_id) DO UPDATE SET last_attack_at = excluded.last_attack_at
            """,
            (user_id, war_id, attack_time.strftime("%Y-%m-%d %H:%M:%S"))
        )

    async def record_attack_result(
        self,
        db: aiosqlite.Connection,
        war_id: int,
        attacker_id: int,
        defender_id: int,
        is_attacker_side: bool,
        is_win: bool,
        xp_gained: int,
        medals_gained: int,
        tp_reward: int,
        now: datetime
    ) -> None:
        # ۱. لاگ حمله
        await db.execute(
            """
            INSERT INTO war_attack_logs (war_id, attacker_id, defender_id, success, xp_gained, medals_gained, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (war_id, attacker_id, defender_id, is_win, xp_gained, medals_gained, now.strftime("%Y-%m-%d %H:%M:%S"))
        )

        # ۲. بروزرسانی جدول جنگ
        if is_attacker_side:
            xp_col = "attacker_xp"
            hits_col = "attacker_success_hits"
        else:
            xp_col = "defender_xp"
            hits_col = "defender_success_hits"

        success_add = 1 if is_win else 0
        await db.execute(
            f"UPDATE cartel_wars SET {xp_col} = {xp_col} + ?, {hits_col} = {hits_col} + ? WHERE id = ?",
            (xp_gained, success_add, war_id)
        )

        # ۳. بروزرسانی اطلاعات مهاجم
        win_add = 1 if is_win else 0
        await db.execute(
            """
            UPDATE users SET tp = tp + ?, war_medals = war_medals + ?, war_attacks = war_attacks + 1, 
                   war_wins = war_wins + ? WHERE id = ?
            """,
            (tp_reward, medals_gained, win_add, attacker_id)
        )

        # ۴. ثبت کول‌دان
        await self.set_user_attack_cooldown(db, attacker_id, war_id, now)

    async def get_active_wars_for_user_cartel(self, db: aiosqlite.Connection, cartel_id: int) -> Optional[CartelWar]:
        async with db.execute(
            """
            SELECT id, attacker_cartel_id, defender_cartel_id, attacker_leader_id, defender_leader_id, 
                   status, requested_at, expires_at, accepted_at, starts_at, ends_at, attacker_xp, 
                   defender_xp, attacker_success_hits, defender_success_hits, attacker_participants, 
                   defender_participants, winner_cartel_id 
            FROM cartel_wars WHERE (attacker_cartel_id = ? OR defender_cartel_id = ?) 
            AND status IN ('scheduled', 'active')
            """,
            (cartel_id, cartel_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return CartelWar(
                id=row[0], attacker_cartel_id=row[1], defender_cartel_id=row[2],
                attacker_leader_id=row[3], defender_leader_id=row[4], status=WarStatus(row[5]),
                requested_at=parse_datetime(row[6]), expires_at=parse_datetime(row[7]),
                accepted_at=parse_datetime(row[8]), starts_at=parse_datetime(row[9]),
                ends_at=parse_datetime(row[10]), attacker_xp=row[11], defender_xp=row[12],
                attacker_success_hits=row[13], defender_success_hits=row[14],
                attacker_participants=row[15], defender_participants=row[16],
                winner_cartel_id=row[17]
            )

    async def get_war_leaderboard(self, db: aiosqlite.Connection, war_id: int) -> List[Tuple[str, int, int, int]]:
        async with db.execute(
            """
            SELECT u.full_name, COUNT(l.id) as total_attacks, 
                   SUM(CASE WHEN l.success = 1 THEN 1 ELSE 0 END) as wins,
                   SUM(l.xp_gained) as total_xp
            FROM war_attack_logs l
            JOIN users u ON l.attacker_id = u.id
            WHERE l.war_id = ?
            GROUP BY l.attacker_id
            ORDER BY total_xp DESC, wins DESC
            LIMIT 10
            """,
            (war_id,)
        ) as cursor:
            return await cursor.fetchall()
