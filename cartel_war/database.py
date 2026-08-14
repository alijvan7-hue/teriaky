"""
Database Initialization and DDL for Cartel War System.
"""
import aiosqlite

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- جدول کارتل‌ها
CREATE TABLE IF NOT EXISTS cartels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    leader_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    war_trophies INTEGER NOT NULL DEFAULT 0,
    war_wins INTEGER NOT NULL DEFAULT 0,
    total_wars INTEGER NOT NULL DEFAULT 0,
    war_medals_total INTEGER NOT NULL DEFAULT 0,
    daily_war_count INTEGER NOT NULL DEFAULT 0,
    pending_war_id INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- جدول کاربران
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, -- Telegram User ID
    username TEXT,
    full_name TEXT NOT NULL,
    cartel_id INTEGER DEFAULT NULL,
    cartel_joined_at TIMESTAMP DEFAULT NULL,
    attack_power INTEGER NOT NULL DEFAULT 100,
    defense_power INTEGER NOT NULL DEFAULT 100,
    level INTEGER NOT NULL DEFAULT 1,
    tp INTEGER NOT NULL DEFAULT 0,
    personal_xp INTEGER NOT NULL DEFAULT 0,
    war_medals INTEGER NOT NULL DEFAULT 0,
    war_attacks INTEGER NOT NULL DEFAULT 0,
    war_wins INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (cartel_id) REFERENCES cartels(id) ON DELETE SET NULL
);

-- جدول جنگ‌های کارتل
CREATE TABLE IF NOT EXISTS cartel_wars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attacker_cartel_id INTEGER NOT NULL,
    defender_cartel_id INTEGER NOT NULL,
    attacker_leader_id INTEGER NOT NULL,
    defender_leader_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP DEFAULT NULL,
    starts_at TIMESTAMP DEFAULT NULL,
    ends_at TIMESTAMP DEFAULT NULL,
    attacker_xp INTEGER NOT NULL DEFAULT 0,
    defender_xp INTEGER NOT NULL DEFAULT 0,
    attacker_success_hits INTEGER NOT NULL DEFAULT 0,
    defender_success_hits INTEGER NOT NULL DEFAULT 0,
    attacker_participants INTEGER NOT NULL DEFAULT 0,
    defender_participants INTEGER NOT NULL DEFAULT 0,
    winner_cartel_id INTEGER DEFAULT NULL,
    FOREIGN KEY (attacker_cartel_id) REFERENCES cartels(id),
    FOREIGN KEY (defender_cartel_id) REFERENCES cartels(id)
);

-- جدول کول‌دان حملات وار
CREATE TABLE IF NOT EXISTS war_attack_cooldowns (
    user_id INTEGER NOT NULL,
    war_id INTEGER NOT NULL,
    last_attack_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, war_id),
    FOREIGN KEY (war_id) REFERENCES cartel_wars(id) ON DELETE CASCADE
);

-- جدول لاگ حملات وار
CREATE TABLE IF NOT EXISTS war_attack_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    war_id INTEGER NOT NULL,
    attacker_id INTEGER NOT NULL,
    defender_id INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    xp_gained INTEGER NOT NULL,
    medals_gained INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (war_id) REFERENCES cartel_wars(id) ON DELETE CASCADE
);

-- ایندکس‌ها برای بهینه‌سازی سرعت کوئری‌ها
CREATE INDEX IF NOT EXISTS idx_cartel_wars_status ON cartel_wars(status);
CREATE INDEX IF NOT EXISTS idx_cartel_wars_starts_at ON cartel_wars(starts_at);
CREATE INDEX IF NOT EXISTS idx_cartel_wars_ends_at ON cartel_wars(ends_at);
CREATE INDEX IF NOT EXISTS idx_users_cartel_id ON users(cartel_id);
CREATE INDEX IF NOT EXISTS idx_attack_logs_war_id ON war_attack_logs(war_id);
CREATE INDEX IF NOT EXISTS idx_attack_logs_attacker ON war_attack_logs(attacker_id);
"""


async def init_cartel_war_db(db_path: str = "cartel_war.db") -> None:
    """ایجاد ساختار اولیه دیتابیس در صورت عدم وجود"""
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
