"""
owner.py — Owner-only commands: addadmin, deladmin, export, maintenance, purge.
"""
from __future__ import annotations

import csv
import io
import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.database import repo
from app.logger import get_logger
from app.middleware.permissions import owner_only
from app.utils.keyboards import home_button, owner_panel_keyboard

log = get_logger(__name__)
router = Router(name="owner")


# ── /owner panel ──────────────────────────────────────────────────────────

@router.message(Command("owner"))
@owner_only
async def cmd_owner(message: Message) -> None:
    admins = await repo.get_all_admins()
    admin_list = "\n".join(
        f"• {a.get('full_name', 'Unknown')} (<code>{a['user_id']}</code>)"
        for a in admins
    ) or "No admins set."
    await message.answer(
        f"👑 <b>Owner Panel</b>\n\n<b>Current Admins:</b>\n{admin_list}",
        parse_mode="HTML",
        reply_markup=owner_panel_keyboard()
    )


# ── Add / Remove Admin ────────────────────────────────────────────────────

@router.message(Command("addadmin"))
@owner_only
async def cmd_addadmin(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user_id.")
        return

    # Ensure user exists
    user = await repo.get_user(uid)
    if not user:
        await message.answer(f"❌ User <code>{uid}</code> not found. They must /start the bot first.",
                             parse_mode="HTML")
        return

    await repo.add_admin(uid, message.from_user.id)
    await message.answer(f"✅ <code>{uid}</code> is now an admin.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "🛡️ You have been granted admin access to this bot.")
    except Exception:
        pass


@router.message(Command("deladmin"))
@owner_only
async def cmd_deladmin(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /deladmin <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user_id.")
        return
    await repo.remove_admin(uid, message.from_user.id)
    await message.answer(f"✅ Admin access removed from <code>{uid}</code>.", parse_mode="HTML")
    try:
        await message.bot.send_message(uid, "ℹ️ Your admin access to this bot has been revoked.")
    except Exception:
        pass


@router.callback_query(F.data == "owner:addadmin")
@owner_only
async def cb_addadmin(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "Use the command:\n<code>/addadmin &lt;user_id&gt;</code>",
        parse_mode="HTML", reply_markup=home_button()
    )
    await call.answer()


@router.callback_query(F.data == "owner:deladmin")
@owner_only
async def cb_deladmin(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "Use the command:\n<code>/deladmin &lt;user_id&gt;</code>",
        parse_mode="HTML", reply_markup=home_button()
    )
    await call.answer()


# ── Export ────────────────────────────────────────────────────────────────

@router.message(Command("export"))
@owner_only
async def cmd_export(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2 or parts[1] not in ("users", "stats", "audit"):
        await message.answer("Usage: /export users|stats|audit")
        return
    await _do_export(message, parts[1])


@router.callback_query(F.data.startswith("owner:export:"))
@owner_only
async def cb_export(call: CallbackQuery) -> None:
    kind = call.data.split(":")[2]
    await call.answer("⏳ Generating export…")
    await _do_export(call.message, kind)


async def _do_export(message: Message, kind: str) -> None:
    if kind == "users":
        rows = await repo.get_all_users()
        buf  = io.StringIO()
        w    = csv.DictWriter(buf, fieldnames=["user_id","username","full_name",
                                               "is_banned","total_generated","created_at"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
        data     = buf.getvalue().encode()
        filename = "users_export.csv"

    elif kind == "stats":
        stats    = await repo.get_stats()
        data     = json.dumps(stats, indent=2, default=str).encode()
        filename = "stats_export.json"

    elif kind == "audit":
        rows     = await repo.get_audit_log(limit=1000)
        data     = json.dumps([dict(r) for r in rows], indent=2, default=str).encode()
        filename = "audit_export.json"
    else:
        return

    file = BufferedInputFile(data, filename=filename)
    await message.answer_document(file, caption=f"📤 Export: <b>{kind}</b>",
                                  parse_mode="HTML")


# ── Maintenance ───────────────────────────────────────────────────────────

@router.message(Command("maintenance"))
@owner_only
async def cmd_maintenance(message: Message) -> None:
    parts   = message.text.split(maxsplit=2)
    if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
        await message.answer("Usage: /maintenance on|off [message]")
        return
    enabled = parts[1].lower() == "on"
    await repo.set_setting("maintenance_mode", "true" if enabled else "false",
                           message.from_user.id)
    if enabled and len(parts) > 2:
        await repo.set_setting("maintenance_msg", parts[2], message.from_user.id)
    status = "🔧 Maintenance mode <b>ON</b>" if enabled else "✅ Maintenance mode <b>OFF</b>"
    await message.answer(status, parse_mode="HTML")


@router.callback_query(F.data == "owner:maintenance:on")
@owner_only
async def cb_maint_on(call: CallbackQuery) -> None:
    await repo.set_setting("maintenance_mode", "true", call.from_user.id)
    await call.answer("🔧 Maintenance ON", show_alert=True)


@router.callback_query(F.data == "owner:maintenance:off")
@owner_only
async def cb_maint_off(call: CallbackQuery) -> None:
    await repo.set_setting("maintenance_mode", "false", call.from_user.id)
    await call.answer("✅ Maintenance OFF", show_alert=True)


# ── Purge user ────────────────────────────────────────────────────────────

@router.message(Command("purge"))
@owner_only
async def cmd_purge(message: Message) -> None:
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /purge <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user_id.")
        return
    await repo.purge_user(uid, message.from_user.id)
    await message.answer(f"🗑️ User <code>{uid}</code> and all their data have been purged.",
                         parse_mode="HTML")
