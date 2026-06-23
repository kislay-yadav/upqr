"""
common.py — /start, /help, profile, donate handlers and home card callback.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database import repo
from app.utils.helpers import format_dt, qr_type_label
from app.utils.keyboards import (
    admin_panel_keyboard,
    home_keyboard,
    home_button,
    owner_panel_keyboard,
)

router = Router(name="common")


# ── /start ────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    await repo.upsert_user(
        user.id, user.username, user.full_name or "",
        user.language_code or "en",
    )

    # Maintenance check
    maintenance = await repo.get_setting("maintenance_mode", "false")
    if maintenance.lower() == "true" and user.id != settings.owner_id:
        msg = await repo.get_setting("maintenance_msg", "🔧 Bot is under maintenance.")
        await message.answer(f"⚠️ {msg}")
        return

    await _send_home(message, user.full_name or user.username or "there")


async def _send_home(message: Message, name: str) -> None:
    text = (
        f"👋 <b>Hey, {name}!</b>\n\n"
        "Welcome to <b>@myqrro_bot</b> — your premium QR & payment poster generator.\n\n"
        "🎨 <b>12 stunning templates</b>  ·  💳 <b>UPI-first</b>  ·  🔗 <b>All QR types</b>\n"
        "📐 <b>HD 2048px output</b>  ·  🖼️ <b>Logo overlay</b>  ·  ⚡ <b>Instant delivery</b>\n\n"
        "<i>Tap a button below to get started.</i>"
    )
    await message.answer(text, reply_markup=home_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = call.from_user
    text = (
        f"🏠 <b>Home</b> · @myqrro_bot\n\n"
        "Choose what to generate or manage your account below."
    )
    await call.message.edit_text(text, reply_markup=home_keyboard(), parse_mode="HTML")
    await call.answer()


# ── /help ────────────────────────────────────────────────────────────────

@router.message(Command("help"))
@router.callback_query(F.data == "help:main")
async def cmd_help(event: Message | CallbackQuery) -> None:
    text = (
        "📖 <b>@myqrro_bot Help</b>\n\n"
        "<b>Generation</b>\n"
        "/upi — UPI payment QR wizard\n"
        "/qr — QR code wizard (URL, Text, Wi-Fi, vCard…)\n"
        "/generate — Quick generate menu\n"
        "/mypayees — Saved payees (1-tap generate)\n\n"
        "<b>Shortcuts</b>\n"
        "/qr_url  /qr_text  /qr_wifi  /qr_vcard\n"
        "/qr_email  /qr_sms  /qr_geo\n\n"
        "<b>Account</b>\n"
        "/profile — Your stats & info\n"
        "/history — Regenerate past QRs\n"
        "/settings — Template, size, watermark, logo\n"
        "/setlogo — Upload a logo image\n"
        "/dellogo — Remove your logo\n"
        "/templates — Browse all 12 themes\n"
        "/delete_me — Delete all your data\n\n"
        "<b>Tips</b>\n"
        "• Save frequent payees in /mypayees for instant generation\n"
        "• Use HD 2048×2048 for print-quality QR codes\n"
        "• Upload a PNG logo for branded QR overlays\n"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=home_button())
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=home_button())
        await event.answer()


# ── /profile ─────────────────────────────────────────────────────────────

@router.message(Command("profile"))
@router.callback_query(F.data == "profile:view")
async def cmd_profile(event: Message | CallbackQuery) -> None:
    user_obj = event.from_user if isinstance(event, Message) else event.from_user
    user = await repo.get_user(user_obj.id)
    us   = await repo.get_user_settings(user_obj.id)
    hist = await repo.get_history(user_obj.id, limit=1)

    if not user:
        text = "❌ Profile not found. Send /start first."
    else:
        last_gen = format_dt(hist[0]["created_at"]) if hist else "Never"
        admin_badge = ""
        if user_obj.id == settings.owner_id:
            admin_badge = " 👑 Owner"
        elif await repo.is_admin(user_obj.id):
            admin_badge = " 🛡️ Admin"

        text = (
            f"👤 <b>Your Profile</b>{admin_badge}\n\n"
            f"🆔 ID: <code>{user['user_id']}</code>\n"
            f"📛 Name: {user['full_name']}\n"
            f"🔤 Username: @{user['username'] or '—'}\n\n"
            f"📊 Total Generated: <b>{user['total_generated']}</b>\n"
            f"🕘 Last Generated: {last_gen}\n"
            f"📅 Joined: {format_dt(user['created_at'])}\n\n"
            f"🎨 Template: <b>{us.get('preferred_template', 'minimal_pro')}</b>\n"
            f"📐 Size: <b>{us.get('preferred_size', '1080x1350')}</b>\n"
            f"💧 Watermark: {'✅' if us.get('watermark_enabled') else '❌'}\n"
            f"🖼️ Logo: {'✅ Set' if user.get('logo_file_id') else '❌ Not set'}\n"
        )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=home_button())
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=home_button())
        await event.answer()


# ── /donate ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "donate:stars")
async def cb_donate(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "⭐ <b>Donate Stars</b>\n\n"
        "Love @myqrro_bot? Support the developer with Telegram Stars!\n\n"
        "Stars help keep the bot fast, free, and feature-rich.\n"
        "Every donation is deeply appreciated 🙏",
        parse_mode="HTML",
        reply_markup=home_button(),
    )
    await call.answer()


# ── Verify ForceSub ───────────────────────────────────────────────────────

@router.callback_query(F.data == "forcesub:verify")
async def cb_forcesub_verify(call: CallbackQuery) -> None:
    """Re-check membership. ForceSub middleware will gate if not joined."""
    from app.middleware.forcesub import _check_membership
    chats = await repo.get_forcesub_chats()
    not_joined = []
    for chat in chats:
        joined = await _check_membership(call.bot, call.from_user.id, chat["chat_id"])
        if not joined:
            not_joined.append(chat)

    if not not_joined:
        await call.answer("✅ Verified! Welcome!", show_alert=True)
        user = call.from_user
        await _send_home(call.message, user.full_name or "there")
    else:
        names = ", ".join(c.get("title", str(c["chat_id"])) for c in not_joined)
        await call.answer(f"❌ Still not joined: {names}", show_alert=True)
