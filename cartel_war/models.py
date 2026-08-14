"""
Data Models and Enums for Cartel War System.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class WarStatus(str, Enum):
    PENDING = "pending"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Cartel:
    id: int
    name: str
    leader_id: int
    xp: int = 0
    war_trophies: int = 0
    war_wins: int = 0
    total_wars: int = 0
    war_medals_total: int = 0
    daily_war_count: int = 0
    pending_war_id: Optional[int] = None
    created_at: Optional[datetime] = None

    @property
    def win_rate(self) -> float:
        if self.total_wars == 0:
            return 0.0
        return round((self.war_wins / self.total_wars) * 100, 1)


@dataclass(slots=True)
class UserProfile:
    id: int
    username: Optional[str]
    full_name: str
    cartel_id: Optional[int]
    cartel_joined_at: Optional[datetime]
    attack_power: int = 100
    defense_power: int = 100
    level: int = 1
    tp: int = 0
    personal_xp: int = 0
    war_medals: int = 0
    war_attacks: int = 0
    war_wins: int = 0


@dataclass(slots=True)
class CartelWar:
    id: int
    attacker_cartel_id: int
    defender_cartel_id: int
    attacker_leader_id: int
    defender_leader_id: int
    status: WarStatus
    requested_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    attacker_xp: int = 0
    defender_xp: int = 0
    attacker_success_hits: int = 0
    defender_success_hits: int = 0
    attacker_participants: int = 0
    defender_participants: int = 0
    winner_cartel_id: Optional[int] = None


@dataclass(slots=True)
class WarAttackCooldown:
    user_id: int
    war_id: int
    last_attack_at: datetime


@dataclass(slots=True)
class WarAttackLog:
    id: int
    war_id: int
    attacker_id: int
    defender_id: int
    success: bool
    xp_gained: int
    medals_gained: int
    created_at: datetime


@dataclass(slots=True)
class BattleResult:
    is_win: bool
    attacker_score: float
    defender_score: float
    xp_gained: int
    medals_gained: int
    tp_reward: int
    attacker_name: str
    defender_name: str
    balance_multiplier: float
