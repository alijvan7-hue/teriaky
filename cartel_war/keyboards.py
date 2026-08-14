"""
Inline Keyboards using Aiogram 3.x CallbackData for Cartel War System.
"""
from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class WarRequestCallback(CallbackData, prefix="war_req"):
    action: str  # "accept" or "reject"
    war_id: int


class WarMenuCallback(CallbackData, prefix="war_menu"):
    action: str  # "attack", "stats", "leaderboard", "refresh"
    war_id: int


def get_war_request_keyboard(war_id: int) -> InlineKeyboardMarkup:
    """کیبورد دعوت به جنگ برای لیدر کارتل مدافع"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ قبول",
                    callback_data=WarRequestCallback(action="accept", war_id=war_id).pack()
                ),
                InlineKeyboardButton(
                    text="❌ رد",
                    callback_data=WarRequestCallback(action="reject", war_id=war_id).pack()
                )
            ]
        ]
    )


def get_war_active_keyboard(war_id: int) -> InlineKeyboardMarkup:
    """کیبورد بخش وار در حین نبرد فعال"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ حمله وار",
                    callback_data=WarMenuCallback(action="attack", war_id=war_id).pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 آمار جنگ",
                    callback_data=WarMenuCallback(action="stats", war_id=war_id).pack()
                ),
                InlineKeyboardButton(
                    text="🏆 جدول نبرد",
                    callback_data=WarMenuCallback(action="leaderboard", war_id=war_id).pack()
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 بروزرسانی",
                    callback_data=WarMenuCallback(action="refresh", war_id=war_id).pack()
                )
            ]
        ]
    )
