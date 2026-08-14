"""
Cartel War Package for Telegram Bots (Aiogram 3.x).
"""
from cartel_war.models import (
    WarStatus,
    Cartel,
    UserProfile,
    CartelWar,
    WarAttackLog,
    WarAttackCooldown,
    BattleResult
)
from cartel_war.database import init_cartel_war_db, SCHEMA_SQL
from cartel_war.repository import WarRepository
from cartel_war.service import WarService
from cartel_war.handlers import war_router
from cartel_war.keyboards import (
    WarRequestCallback,
    WarMenuCallback,
    get_war_request_keyboard,
    get_war_active_keyboard
)
from cartel_war.scheduler import setup_war_scheduler

__all__ = [
    "WarStatus",
    "Cartel",
    "UserProfile",
    "CartelWar",
    "WarAttackLog",
    "WarAttackCooldown",
    "BattleResult",
    "init_cartel_war_db",
    "SCHEMA_SQL",
    "WarRepository",
    "WarService",
    "war_router",
    "WarRequestCallback",
    "WarMenuCallback",
    "get_war_request_keyboard",
    "get_war_active_keyboard",
    "setup_war_scheduler",
]
