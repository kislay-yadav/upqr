"""
admin.py — Admin panel: stats, watermark, ForceSub config, ban/unban, broadcast, audit.
"""
from __future__ import annotations

import asyncio
import csv
import io
import json

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, Message,
)

from app.database import repo
from app.logger import get_logger
from app.middleware.permissions import admin_only
from app.utils.keyboards import (
    admin_panel_keyboard, back_keyboard, confirm_keyboard,
    home_button, build_forcesub_keyboard,
)

log = get_logger(__name__)
router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_ban_id         = State()
    waiting_ban_reason     = State()
    waiting_unban_id       = State()
    waiting_wm_text        = State()
    waiting_broadcast_text = State()
    waiting_broadcast_confirm = State()
    waiting_forcesub_add   = State()
    waiting_forcesub_del   = State()
    waiting_limits         = State()


# ── /admin panel ──────────────────────────────────────────────────────────

@router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "🛡️ <b>Admin Panel</b>\n\nChoose an action:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )


@router.callback_query(F.data == "admin:stats")
@admin_only
async def cb_admin_stats(call: CallbackQuery) -> None:
    stats = await repo.get_stats()
    from app.database.engine import check_db_health
    db    = await check_db_health()
    text  = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total Users: <b>{stats['total_users']}</b>\n"
        f"🚫 Banned: <b>{stats['banned_users']}</b>\n"
        f"📸 Total Generated: <b>{stats['total_generated']}</b>\n"
        f"📅 Today Generated: <b>{stats['today_generated']}</b>\n\n"
        f"🗄️ DB: <b>{db['status']}</b>  "
        f"{'(' + str(db.get('latency_ms')) + 'ms)' if db.get('latency_ms') else ''}"
    )
    await call.message.edit_text(text, parse_mode="HTML",
                                 reply_markup=back_keyboard("admin:panel_home"))
    await call.answer()


@router.callback_query(F.data == "admin:panel_home")
async def cb_admin_home(call: CallbackQuery) -> None:
    await call.message.edit_text("🛡️ <b>Admin Panel</b>", parse_mode="HTML",
                                 reply_markup=admin_panel_keyboard())
    await call.answer()


# ── Watermark ─────────────────────────────────────────────────────────────

@router.message(Command("setwatermark"))
@admin_only
async def cmd_setwatermark(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
        await message.answer("Usage: /setwatermark on|off")
        return
    val = "true" if parts[1].lower() == "on" else "false"
    await repo.set_setting("watermark_enabled", val, message.from_user.id)
    await message.answer(f"💧 Watermark globally {'enabled' if val == 'true' else 'disabled'}.")


@router.message(Command("setwatermarktext"))
@admin_only
async def cmd_setwatermarktext(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /setwatermarktext <text>")
        return
    await repo.set_setting("watermark_text", parts[1].strip()[:40], message.from_user.id)
    await message.answer(f"💧 Watermark text set to: <b>{parts[1].strip()}</b>", parse_mode="HTML")


@router.callback_query(F.data == "admin:watermark")
@admin_only
async def cb_watermark(call: CallbackQuery, state: FSMContext) -> None:
    wm_on   = await repo.get_setting("watermark_enabled", "true") == "true"
    wm_text = await repo.get_setting("watermark_text", "@myqrro_bot")
    await call.message.edit_text(
        f"💧 <b>Watermark Settings</b>\n\n"
        f"Status: {'✅ Enabled' if wm_on else '❌ Disabled'}\n"
        f"Text: <code>{wm_text}</code>\n\n"
        f"Use /setwatermark on|off and /setwatermarktext to change.",
        parse_mode="HTML", reply_markup=back_keyboard("admin:panel_home")
    )
    await call.answer()


# ── Rate limits ───────────────────────────────────────────────────────────

@router.message(Command("setlimits"))
@admin_only
async def cmd_setlimits(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /setlimits <per_min> <per_day>")
        return
    try:
        per_min = int(parts[1])
        per_day = int(parts[2])
    except ValueError:
        await message.answer("❌ Invalid numbers.")
        return
    await repo.set_setting("rate_per_minute", str(per_min), message.from_user.id)
    await repo.set_setting("rate_per_day",    str(per_day), message.from_user.id)
    await message.answer(f"✅ Rate limits set: <b>{per_min}/min</b>, <b>{per_day}/day</b>",
                         parse_mode="HTML")


# ── Ban / Unban ───────────────────────────────────────────────────────────

@router.message(Command("ban"))
@admin_only
async def cmd_ban_start(message: Message, state: FSMContext) -> None:
    parts = message.text.split()
    if len(parts) >= 2:
        try:
            uid = int(parts[1])
            reason = " ".join(parts[2:]) if len(parts) > 2 else "Banned by admin"
            await _do_ban(message, uid, reason, message.bot)
            return
        except ValueError:
            pass
    await state.set_state(AdminStates.waiting_ban_id)
    await message.answer("🚫 Enter the user_id to ban:")


@router.message(AdminStates.waiting_ban_id)
@admin_only
async def ban_got_id(message: Message, state: FSMContext) -> None:
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    await state.update_data(ban_uid=uid)
    await state.set_state(AdminStates.waiting_ban_reason)
    await message.answer("Enter ban reason (or <i>skip</i>):", parse_mode="HTML")


@router.message(AdminStates.waiting_ban_reason)
@admin_only
async def ban_got_reason(message: Message, state: FSMContext) -> None:
    data   = await state.get_data()
    reason = "Banned by admin" if message.text.strip().lower() == "skip" else message.text.strip()
    await state.clear()
    await _do_ban(message, data["ban_uid"], reason, message.bot)


async def _do_ban(message: Message, uid: int, reason: str, bot: Bot) -> None:
    await repo.ban_user(uid, reason, message.from_user.id)
    await message.answer(f"🚫 User <code>{uid}</code> banned.\nReason: {reason}", parse_mode="HTML")
    try:
        await bot.send_message(uid, f"🚫 You have been banned from this bot.\nReason: {reason}")
    except Exception:
        pass


@router.message(Command("unban"))
@admin_only
async def cmd_unban(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unban <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    await repo.unban_user(uid, message.from_user.id)
    await message.answer(f"✅ User <code>{uid}</code> unbanned.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "✅ You have been unbanned. Send /start to continue.")
    except Exception:
        pass


# ── ForceSub management ───────────────────────────────────────────────────

@router.message(Command("forcesub_on"))
@admin_only
async def cmd_fs_on(message: Message) -> None:
    await repo.set_setting("forcesub_enabled", "true", message.from_user.id)
    await message.answer("🔐 ForceSub <b>enabled</b>.", parse_mode="HTML")


@router.message(Command("forcesub_off"))
@admin_only
async def cmd_fs_off(message: Message) -> None:
    await repo.set_setting("forcesub_enabled", "false", message.from_user.id)
    await message.answer("🔓 ForceSub <b>disabled</b>.", parse_mode="HTML")


@router.message(Command("forcesub_add"))
@admin_only
async def cmd_fs_add(message: Message) -> None:
    """
    /forcesub_add @username
    /forcesub_add <chat_id> <invite_link>
    """
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage:\n/forcesub_add @username\n/forcesub_add <chat_id> <invite_link>")
        return

    arg1 = parts[1]
    invite_link = parts[2] if len(parts) > 2 else None

    if arg1.startswith("@"):
        username = arg1.lstrip("@")
        try:
            chat = await message.bot.get_chat(f"@{username}")
            await repo.add_forcesub_chat(
                chat.id, username, None, chat.title or username, message.from_user.id
            )
            await message.answer(f"✅ Added @{username} (ID: {chat.id}) to ForceSub list.")
        except Exception as exc:
            await message.answer(f"❌ Failed: {exc}\nMake sure the bot is an admin in that chat.")
        return

    try:
        chat_id = int(arg1)
    except ValueError:
        await message.answer("❌ Invalid chat_id. Must be a number or @username.")
        return

    try:
        chat = await message.bot.get_chat(chat_id)
        title = chat.title or str(chat_id)
    except Exception:
        title = str(chat_id)

    await repo.add_forcesub_chat(chat_id, None, invite_link, title, message.from_user.id)
    await message.answer(f"✅ Added chat <code>{chat_id}</code> to ForceSub list.", parse_mode="HTML")


@router.message(Command("forcesub_list"))
@admin_only
async def cmd_fs_list(message: Message) -> None:
    chats = await repo.get_forcesub_chats()
    if not chats:
        await message.answer("📋 ForceSub list is empty.")
        return
    lines = ["📋 <b>ForceSub Chats:</b>\n"]
    for c in chats:
        handle = f"@{c['username']}" if c.get("username") else str(c["chat_id"])
        link   = f" · <a href='{c['invite_link']}'>Invite</a>" if c.get("invite_link") else ""
        lines.append(f"• <b>{c.get('title', handle)}</b> ({c['chat_id']}){link}")
    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("forcesub_del"))
@admin_only
async def cmd_fs_del(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /forcesub_del <chat_id>")
        return
    try:
        chat_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid chat_id.")
        return
    await repo.remove_forcesub_chat(chat_id, message.from_user.id)
    await message.answer(f"✅ Removed <code>{chat_id}</code> from ForceSub list.", parse_mode="HTML")


@router.callback_query(F.data == "admin:forcesub")
@admin_only
async def cb_admin_forcesub(call: CallbackQuery) -> None:
    chats   = await repo.get_forcesub_chats()
    enabled = await repo.get_setting("forcesub_enabled", "false") == "true"
    lines   = [f"🔐 <b>ForceSub</b>  {'✅ Enabled' if enabled else '❌ Disabled'}\n"]
    if chats:
        for c in chats:
            lines.append(f"• {c.get('title', c['chat_id'])} (<code>{c['chat_id']}</code>)")
    else:
        lines.append("No chats configured. Use /forcesub_add to add channels.")
    await call.message.edit_text("\n".join(lines), parse_mode="HTML",
                                 reply_markup=back_keyboard("admin:panel_home"))
    await call.answer()


# ── Broadcast ─────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
@admin_only
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_broadcast_text)
    await message.answer(
        "📢 <b>Broadcast</b>\n\nSend the message text (HTML supported).\n"
        "It will be sent to all users.\n\n<i>Send /cancel to abort.</i>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin:broadcast")
@admin_only
async def cb_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_broadcast_text)
    await call.message.edit_text(
        "📢 <b>Broadcast Wizard</b>\n\nEnter your broadcast message (HTML supported):",
        parse_mode="HTML", reply_markup=back_keyboard("admin:panel_home")
    )
    await call.answer()


@router.message(AdminStates.waiting_broadcast_text)
@admin_only
async def broadcast_got_text(message: Message, state: FSMContext) -> None:
    text = message.text or message.caption or ""
    await state.update_data(broadcast_text=text)
    await state.set_state(AdminStates.waiting_broadcast_confirm)
    await message.answer(
        f"📢 <b>Preview:</b>\n\n{text}\n\n<b>Send to all users?</b>",
        parse_mode="HTML",
        reply_markup=confirm_keyboard("broadcast:confirm", "broadcast:cancel")
    )


@router.callback_query(F.data == "broadcast:confirm")
@admin_only
async def cb_broadcast_confirm(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    await state.clear()

    users    = await repo.get_all_users()
    ok, fail = 0, 0
    status   = await call.message.edit_text(f"📢 Broadcasting to {len(users)} users…")

    for user in users:
        try:
            await call.bot.send_message(user["user_id"], text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # ~20 msg/s to respect Telegram limits

    await status.edit_text(
        f"📢 <b>Broadcast complete.</b>\n✅ Sent: {ok}\n❌ Failed: {fail}",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "broadcast:cancel")
async def cb_broadcast_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("❌ Broadcast cancelled.", reply_markup=home_button())
    await call.answer()


# ── Audit log ─────────────────────────────────────────────────────────────

@router.message(Command("audit"))
@router.callback_query(F.data == "admin:audit")
@admin_only
async def cmd_audit(event: Message | CallbackQuery) -> None:
    records = await repo.get_audit_log(limit=20)
    if not records:
        text = "📋 <b>Audit Log</b>\n\nNo events yet."
    else:
        lines = ["📋 <b>Audit Log</b> (last 20)\n"]
        for r in records:
            ts = str(r["created_at"])[:16]
            actor = f"@{r['username']}" if r.get("username") else str(r["actor_id"])
            lines.append(f"<code>{ts}</code> — {actor}: <b>{r['action']}</b>"
                         + (f" → {r['target_id']}" if r.get("target_id") else ""))
        text = "\n".join(lines)

    kb = back_keyboard("admin:panel_home")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


# ── Health ────────────────────────────────────────────────────────────────

@router.message(Command("health"))
@router.callback_query(F.data == "admin:health")
@admin_only
async def cmd_health(event: Message | CallbackQuery) -> None:
    import psutil, time
    from app.database.engine import check_db_health
    db = await check_db_health()
    proc = psutil.Process()
    mem_mb = round(proc.memory_info().rss / 1024 / 1024, 2)
    uptime = round(time.time() - proc.create_time(), 0)

    text = (
        "🏥 <b>Health Status</b>\n\n"
        f"🗄️ Database: <b>{db['status']}</b>"
        + (f"  ({db.get('latency_ms')}ms)" if db.get("latency_ms") else "") + "\n"
        f"🧠 Memory RSS: <b>{mem_mb} MB</b>\n"
        f"⏱️ Uptime: <b>{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m</b>\n"
    )
    kb = back_keyboard("admin:panel_home")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
