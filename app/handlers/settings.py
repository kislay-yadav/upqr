"""
settings.py — User settings: template picker, size, watermark, logo upload, delete_me.
"""
from __future__ import annotations

import io

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, PhotoSize

from app.database import repo
from app.logger import get_logger
from app.services.poster_renderer import list_themes
from app.utils.keyboards import (
    back_keyboard, confirm_keyboard, home_button,
    settings_keyboard, size_keyboard, templates_keyboard,
)

log = get_logger(__name__)
router = Router(name="settings")


class SettingsStates(StatesGroup):
    waiting_logo = State()


# ── /settings ─────────────────────────────────────────────────────────────

@router.message(Command("settings"))
@router.callback_query(F.data == "settings:main")
async def cmd_settings(event: Message | CallbackQuery) -> None:
    user_id = event.from_user.id
    us = await repo.get_user_settings(user_id)
    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"🎨 Template: <b>{us.get('preferred_template', 'minimal_pro')}</b>\n"
        f"📐 Size: <b>{us.get('preferred_size', '1080x1350')}</b>\n"
        f"💧 Watermark: {'✅ On' if us.get('watermark_enabled') else '❌ Off'}\n"
    )
    kb = settings_keyboard(us)
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


# ── Templates ─────────────────────────────────────────────────────────────

@router.message(Command("templates"))
@router.callback_query(F.data == "templates:list")
@router.callback_query(F.data.startswith("template:page:"))
async def cmd_templates(event: Message | CallbackQuery) -> None:
    user_id = event.from_user.id
    us = await repo.get_user_settings(user_id)
    current = us.get("preferred_template", "minimal_pro")
    themes  = list_themes()

    page = 0
    if isinstance(event, CallbackQuery) and event.data.startswith("template:page:"):
        page = int(event.data.split(":")[2])

    text = "🎨 <b>Templates</b>\n\nChoose your poster style:"
    kb   = templates_keyboard(themes, current, page)

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.callback_query(F.data.startswith("template:select:"))
async def cb_template_select(call: CallbackQuery) -> None:
    theme_id = call.data.split(":")[2]
    await repo.update_user_settings(call.from_user.id, preferred_template=theme_id)
    await call.answer(f"✅ Template set to: {theme_id}", show_alert=False)
    # Refresh list
    us      = await repo.get_user_settings(call.from_user.id)
    themes  = list_themes()
    await call.message.edit_reply_markup(reply_markup=templates_keyboard(themes, theme_id))


# ── Size ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:size")
async def cb_size_menu(call: CallbackQuery) -> None:
    us = await repo.get_user_settings(call.from_user.id)
    await call.message.edit_text(
        "📐 <b>Output Size</b>\n\nChoose your preferred poster size:",
        parse_mode="HTML",
        reply_markup=size_keyboard(us.get("preferred_size", "1080x1350"))
    )
    await call.answer()


@router.callback_query(F.data.startswith("size:select:"))
async def cb_size_select(call: CallbackQuery) -> None:
    size = call.data.split(":")[2]
    await repo.update_user_settings(call.from_user.id, preferred_size=size)
    await call.answer(f"✅ Size set to {size}", show_alert=False)
    await call.message.edit_reply_markup(reply_markup=size_keyboard(size))


# ── Watermark toggle ──────────────────────────────────────────────────────

@router.callback_query(F.data == "settings:toggle_wm")
async def cb_toggle_watermark(call: CallbackQuery) -> None:
    us      = await repo.get_user_settings(call.from_user.id)
    new_val = not us.get("watermark_enabled", True)
    await repo.update_user_settings(call.from_user.id, watermark_enabled=new_val)
    status = "✅ enabled" if new_val else "❌ disabled"
    await call.answer(f"Watermark {status}", show_alert=False)
    us = await repo.get_user_settings(call.from_user.id)
    await call.message.edit_reply_markup(reply_markup=settings_keyboard(us))


# ── Logo upload ───────────────────────────────────────────────────────────

@router.message(Command("setlogo"))
@router.callback_query(F.data == "settings:setlogo")
async def cmd_setlogo(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_logo)
    text = (
        "🖼️ <b>Upload Logo</b>\n\n"
        "Send a <b>PNG or JPG image</b> as your logo.\n\n"
        "It will be overlaid on the center of your QR codes.\n"
        "<i>Recommended: square PNG with transparent background, max 512×512</i>"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=back_keyboard("settings:main"))
    else:
        await event.message.edit_text(text, parse_mode="HTML",
                                      reply_markup=back_keyboard("settings:main"))
        await event.answer()


@router.message(SettingsStates.waiting_logo)
async def logo_received(message: Message, state: FSMContext) -> None:
    if not message.photo and not message.document:
        await message.answer("❌ Please send a photo or image file.")
        return

    if message.photo:
        file_id = message.photo[-1].file_id
    else:
        file_id = message.document.file_id

    await repo.set_user_logo(message.from_user.id, file_id)
    await state.clear()
    await message.answer(
        "✅ <b>Logo saved!</b>\n\nYour logo will appear on future QR codes.",
        parse_mode="HTML", reply_markup=home_button()
    )


@router.message(Command("dellogo"))
@router.callback_query(F.data == "settings:dellogo")
async def cmd_dellogo(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await repo.set_user_logo(event.from_user.id, None)
    text = "🗑️ <b>Logo removed.</b>\n\nYour QR codes will no longer have a logo overlay."
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=home_button())
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=home_button())
        await event.answer()


# ── Delete my account ─────────────────────────────────────────────────────

@router.message(Command("delete_me"))
@router.callback_query(F.data == "settings:delete_me")
async def cmd_delete_me(event: Message | CallbackQuery) -> None:
    text = (
        "⚠️ <b>Delete My Account</b>\n\n"
        "This will permanently delete:\n"
        "• Your profile and settings\n"
        "• All saved payees\n"
        "• All generation history\n\n"
        "<b>This action cannot be undone.</b>\n\nAre you sure?"
    )
    kb = confirm_keyboard("delete_me:confirm", "settings:main")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.callback_query(F.data == "delete_me:confirm")
async def cb_delete_me_confirm(call: CallbackQuery) -> None:
    user_id = call.from_user.id
    await repo.purge_user(user_id, user_id)
    await call.message.edit_text(
        "✅ <b>Your account has been deleted.</b>\n\n"
        "All your data has been removed. Send /start to create a new account.",
        parse_mode="HTML"
    )
    await call.answer()


# ── History ───────────────────────────────────────────────────────────────

@router.message(Command("history"))
@router.callback_query(F.data == "history:list")
async def cmd_history(event: Message | CallbackQuery) -> None:
    user_id = event.from_user.id
    records = await repo.get_history(user_id, limit=10)

    if not records:
        text = "🕘 <b>History</b>\n\nNo generation history yet. Use /upi or /qr to get started."
        kb = home_button()
    else:
        text = f"🕘 <b>History</b>  (last {len(records)})\n\nTap to regenerate:"
        from app.utils.keyboards import history_keyboard
        kb = history_keyboard(records)

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.callback_query(F.data.startswith("history:regen:"))
async def cb_history_regen(call: CallbackQuery) -> None:
    hist_id = int(call.data.split(":")[2])
    records = await repo.get_history(call.from_user.id, limit=50)
    record  = next((r for r in records if r["id"] == hist_id), None)

    if not record:
        await call.answer("❌ Record not found.", show_alert=True)
        return

    await call.answer("⏳ Regenerating…")
    from app.handlers.generate import _generate_and_send
    await _generate_and_send(
        call.message,
        record["payload"],
        record["qr_type"],
    )
