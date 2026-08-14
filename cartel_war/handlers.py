"""
Aiogram 3.x Handlers and Router for Cartel War System.
"""
from datetime import datetime
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
import aiosqlite

from cartel_war.keyboards import (
    WarRequestCallback,
    WarMenuCallback,
    get_war_request_keyboard,
    get_war_active_keyboard
)
from cartel_war.models import WarStatus
from cartel_war.service import WarService

logger = logging.getLogger(__name__)
war_router = Router(name="cartel_war_router")


# -------------------------------------------------------------
# ۱. دستور شروع وار: کارتل وار [نام کارتل]
# -------------------------------------------------------------
@war_router.message(F.text.startswith("کارتل وار") | F.text.startswith("/cartel_war"))
async def cmd_start_war(message: Message, bot: Bot, war_service: WarService):
    text = (message.text or "").strip()
    
    if text.startswith("/cartel_war"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("📌 نحوه استفاده: `/cartel_war [نام کارتل]`", parse_mode="Markdown")
            return
        target_name = parts[1].strip()
    else:
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("📌 نحوه استفاده: `کارتل وار [نام کارتل]`\nمثال: `کارتل وار عقاب‌ها`", parse_mode="Markdown")
            return
        target_name = parts[2].strip()

    user_id = message.from_user.id
    success, msg, war_id, defender_leader_id = await war_service.initiate_war_request(user_id, target_name)

    if not success:
        await message.reply(msg)
        return

    await message.reply(msg)

    # دریافت نام کارتل فرستنده
    async with aiosqlite.connect(war_service.db_path) as db:
        user = await war_service.repo.get_user_by_id(db, user_id)
        attacker_cartel = await war_service.repo.get_cartel_by_id(db, user.cartel_id)
        attacker_name = attacker_cartel.name if attacker_cartel else "حریف"

    invite_text = (
        "🚨 **درخواست Cartel War**\n\n"
        f"کارتل 🏴 **{attacker_name}** شما را به جنگ دعوت کرده است.\n\n"
        "⏳ **مهلت پاسخ:** ۱ ساعت\n\n"
        "در صورت پذیرش، جنگ ۳۰ دقیقه بعد آغاز می‌شود."
    )
    try:
        await bot.send_message(
            chat_id=defender_leader_id,
            text=invite_text,
            reply_markup=get_war_request_keyboard(war_id),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning("نتوانستیم به لیدر مدافع پیام ارسال کنیم: %s", e)


# -------------------------------------------------------------
# ۲. پاسخ لیدر مدافع: قبول یا رد درخواست
# -------------------------------------------------------------
@war_router.callback_query(WarRequestCallback.filter())
async def cb_war_request_response(
    callback: CallbackQuery,
    callback_data: WarRequestCallback,
    bot: Bot,
    war_service: WarService
):
    user_id = callback.from_user.id
    war_id = callback_data.war_id
    accept = (callback_data.action == "accept")

    success, msg, war = await war_service.handle_war_response(user_id, war_id, accept)
    if not success:
        await callback.answer(msg, show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text(msg)

    if accept and war:
        async with aiosqlite.connect(war_service.db_path) as db:
            cartel_a = await war_service.repo.get_cartel_by_id(db, war.attacker_cartel_id)
            cartel_b = await war_service.repo.get_cartel_by_id(db, war.defender_cartel_id)
            members_a = await war_service.repo.get_cartel_members(db, war.attacker_cartel_id)
            members_b = await war_service.repo.get_cartel_members(db, war.defender_cartel_id)

        prep_text = (
            f"⚔️ **جنگ بین {cartel_a.name} و {cartel_b.name} تا ۳۰ دقیقه دیگر آغاز می‌شود.**\n\n"
            "خودتان را آماده کنید."
        )
        for member in members_a + members_b:
            try:
                await bot.send_message(chat_id=member.id, text=prep_text, parse_mode="Markdown")
            except Exception:
                pass
    else:
        if war:
            try:
                await bot.send_message(
                    chat_id=war.attacker_leader_id,
                    text="❌ درخواست جنگ کارتل شما توسط لیدر کارتل حریف رد شد."
                )
            except Exception:
                pass


# -------------------------------------------------------------
# ۳. منوی وار (نمایش داشبورد زنده)
# -------------------------------------------------------------
@war_router.message(F.text == "⚔️ وار" or F.text == "/war")
async def cmd_war_menu(message: Message, war_service: WarService):
    user_id = message.from_user.id
    async with aiosqlite.connect(war_service.db_path) as db:
        user = await war_service.repo.get_user_by_id(db, user_id)
        if not user or not user.cartel_id:
            await message.reply("❌ شما عضو هیچ کارتلی نیستید.")
            return

        war = await war_service.repo.get_active_wars_for_user_cartel(db, user.cartel_id)
        if not war:
            await message.reply("ℹ️ در حال حاضر کارتل شما هیچ جنگ فعالی ندارد.")
            return

        cartel_a = await war_service.repo.get_cartel_by_id(db, war.attacker_cartel_id)
        cartel_b = await war_service.repo.get_cartel_by_id(db, war.defender_cartel_id)
        last_attack = await war_service.repo.get_user_last_attack_time(db, user_id, war.id)

    now = datetime.now()
    if war.status == WarStatus.SCHEDULED:
        rem_start = max(0, int((war.starts_at - now).total_seconds())) if war.starts_at else 0
        mins, secs = divmod(rem_start, 60)
        await message.reply(f"⏳ جنگ تا `{mins:02d}:{secs:02d}` دیگر آغاز خواهد شد. آماده باشید!", parse_mode="Markdown")
        return

    rem_war = max(0, int((war.ends_at - now).total_seconds())) if war.ends_at else 0
    hours, remainder = divmod(rem_war, 3600)
    minutes, seconds = divmod(remainder, 60)

    cd_text = "🟢 آماده حمله"
    if last_attack:
        elapsed = (now - last_attack).total_seconds()
        if elapsed < 300:
            rem_cd = int(300 - elapsed)
            cd_m, cd_s = divmod(rem_cd, 60)
            cd_text = f"🔴 {cd_m:02d}:{cd_s:02d}"

    menu_text = (
        "⚔️ **میدان نبرد Cartel War**\n\n"
        f"🏴 **{cartel_a.name}** vs 🏴 **{cartel_b.name}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💥 **XP جنگ:**\n"
        f"• {cartel_a.name}: `{war.attacker_xp}` XP\n"
        f"• {cartel_b.name}: `{war.defender_xp}` XP\n\n"
        f"🎯 **حملات موفق:**\n"
        f"• {cartel_a.name}: `{war.attacker_success_hits}`\n"
        f"• {cartel_b.name}: `{war.defender_success_hits}`\n\n"
        f"⏳ **زمان باقی‌مانده از جنگ:** `{hours:02d}:{minutes:02d}:{seconds:02d}`\n"
        f"⚡ **وضعیت کول‌دان شما:** {cd_text}\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    await message.reply(menu_text, reply_markup=get_war_active_keyboard(war.id), parse_mode="Markdown")


# -------------------------------------------------------------
# ۴. اجرای حمله وار و اکشن‌های منوی وار
# -------------------------------------------------------------
@war_router.callback_query(WarMenuCallback.filter())
async def cb_war_menu_actions(
    callback: CallbackQuery,
    callback_data: WarMenuCallback,
    war_service: WarService
):
    user_id = callback.from_user.id
    war_id = callback_data.war_id
    action = callback_data.action

    if action == "attack":
        success, msg, result = await war_service.execute_attack(user_id, war_id)
        if not success:
            await callback.answer(msg, show_alert=True)
            return

        if result.is_win:
            res_msg = (
                f"🔥 **پیروزی در حمله وار!**\n\n"
                f"🎯 هدف: `{result.defender_name}`\n"
                f"⚔️ قدرت شما: `{result.attacker_score}` | 🛡 قدرت حریف: `{result.defender_score}`\n\n"
                f"🎁 **جوایز:**\n"
                f"• +{result.xp_gained} War XP برای کارتل (ضریب: {result.balance_multiplier}x)\n"
                f"• +{result.medals_gained} مدال جنگی 🎖\n"
                f"• +{result.tp_reward:,} TP نقد"
            )
        else:
            res_msg = (
                f"💀 **شکست در حمله وار!**\n\n"
                f"🎯 هدف: `{result.defender_name}`\n"
                f"⚔️ قدرت شما: `{result.attacker_score}` | 🛡 قدرت حریف: `{result.defender_score}`\n\n"
                f"🎁 **پاداش تلاش:**\n"
                f"• +{result.xp_gained} War XP برای کارتل\n"
                f"• +{result.medals_gained} مدال جنگی 🎖"
            )

        await callback.answer("حمله انجام شد!", show_alert=False)
        await callback.message.reply(res_msg, parse_mode="Markdown")

    elif action in ("stats", "refresh"):
        async with aiosqlite.connect(war_service.db_path) as db:
            war = await war_service.repo.get_war_by_id(db, war_id)
            if not war or war.status != WarStatus.ACTIVE:
                await callback.answer("جنگ پایان یافته یا در دسترس نیست.", show_alert=True)
                return

            cartel_a = await war_service.repo.get_cartel_by_id(db, war.attacker_cartel_id)
            cartel_b = await war_service.repo.get_cartel_by_id(db, war.defender_cartel_id)
            last_attack = await war_service.repo.get_user_last_attack_time(db, user_id, war.id)

        now = datetime.now()
        rem_war = max(0, int((war.ends_at - now).total_seconds())) if war.ends_at else 0
        hours, remainder = divmod(rem_war, 3600)
        minutes, seconds = divmod(remainder, 60)

        cd_text = "🟢 آماده حمله"
        if last_attack:
            elapsed = (now - last_attack).total_seconds()
            if elapsed < 300:
                rem_cd = int(300 - elapsed)
                cd_m, cd_s = divmod(rem_cd, 60)
                cd_text = f"🔴 {cd_m:02d}:{cd_s:02d}"

        menu_text = (
            "⚔️ **میدان نبرد Cartel War (بروزرسانی)**\n\n"
            f"🏴 **{cartel_a.name}** vs 🏴 **{cartel_b.name}**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"💥 **XP جنگ:**\n"
            f"• {cartel_a.name}: `{war.attacker_xp}` XP\n"
            f"• {cartel_b.name}: `{war.defender_xp}` XP\n\n"
            f"🎯 **حملات موفق:**\n"
            f"• {cartel_a.name}: `{war.attacker_success_hits}`\n"
            f"• {cartel_b.name}: `{war.defender_success_hits}`\n\n"
            f"⏳ **زمان باقی‌مانده:** `{hours:02d}:{minutes:02d}:{seconds:02d}`\n"
            f"⚡ **وضعیت کول‌دان شما:** {cd_text}\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        try:
            await callback.message.edit_text(
                menu_text,
                reply_markup=get_war_active_keyboard(war.id),
                parse_mode="Markdown"
            )
            await callback.answer("بروزرسانی شد.")
        except Exception:
            await callback.answer("اطلاعات تغییری نکرده است.")

    elif action == "leaderboard":
        async with aiosqlite.connect(war_service.db_path) as db:
            rows = await war_service.repo.get_war_leaderboard(db, war_id)

        if not rows:
            await callback.answer("هنوز حمله‌ای در این وار ثبت نشده است.", show_alert=True)
            return

        lines = ["🏆 **برترین رزمندگان جنگ:**\n"]
        for idx, (name, total, wins, total_xp) in enumerate(rows, start=1):
            lines.append(f"{idx}. 👤 **{name}** — `{total_xp}` XP | 💥 {wins}/{total} پیروزی")

        await callback.message.reply("\n".join(lines), parse_mode="Markdown")
        await callback.answer()
