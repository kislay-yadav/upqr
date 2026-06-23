"""
payees.py — Saved payees: list, add, generate from payee, delete.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import repo
from app.logger import get_logger
from app.services.qr_service import UPIPayload, build_upi_payload
from app.utils.helpers import parse_amount, validate_vpa_simple
from app.utils.keyboards import (
    home_button, payees_keyboard, payee_manage_keyboard,
    back_keyboard, confirm_keyboard,
)

log = get_logger(__name__)
router = Router(name="payees")


class PayeeStates(StatesGroup):
    waiting_label      = State()
    waiting_vpa        = State()
    waiting_name       = State()
    waiting_amount     = State()
    waiting_note       = State()


# ── /mypayees ─────────────────────────────────────────────────────────────

@router.message(Command("mypayees"))
@router.callback_query(F.data == "payees:list")
async def cmd_mypayees(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = event.from_user.id
    payees  = await repo.get_payees(user_id)

    if not payees:
        text = (
            "💳 <b>My Payees</b>\n\n"
            "You have no saved payees yet.\n\n"
            "Tap <b>Add Payee</b> to save a UPI ID for instant 1-tap QR generation."
        )
    else:
        text = (
            f"💳 <b>My Payees</b>  ({len(payees)} saved)\n\n"
            "Tap any payee to instantly generate their QR poster."
        )

    kb = payees_keyboard(payees)
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


# ── Add payee wizard ──────────────────────────────────────────────────────

@router.callback_query(F.data == "payee:add")
async def cb_payee_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PayeeStates.waiting_label)
    await call.message.edit_text(
        "➕ <b>Add New Payee</b>\n\nStep 1/5 — Enter a <b>label</b> for this payee:\n"
        "<i>Example: Home Rent, Mom, Pizza Place</i>",
        parse_mode="HTML", reply_markup=back_keyboard("payees:list")
    )
    await call.answer()


@router.message(PayeeStates.waiting_label)
async def payee_got_label(message: Message, state: FSMContext) -> None:
    label = message.text.strip()[:40]
    await state.update_data(label=label)
    await state.set_state(PayeeStates.waiting_vpa)
    await message.answer(
        f"✅ Label: <b>{label}</b>\n\nStep 2/5 — Enter the <b>UPI ID / VPA</b>:",
        parse_mode="HTML"
    )


@router.message(PayeeStates.waiting_vpa)
async def payee_got_vpa(message: Message, state: FSMContext) -> None:
    vpa = message.text.strip()
    if not validate_vpa_simple(vpa):
        await message.answer("❌ Invalid VPA format. Try again (e.g. name@upi):")
        return
    await state.update_data(vpa=vpa)
    await state.set_state(PayeeStates.waiting_name)
    await message.answer(
        f"✅ VPA: <code>{vpa}</code>\n\nStep 3/5 — Enter the <b>Payee Name</b>:",
        parse_mode="HTML"
    )


@router.message(PayeeStates.waiting_name)
async def payee_got_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:50]
    await state.update_data(payee_name=name)
    await state.set_state(PayeeStates.waiting_amount)
    await message.answer(
        f"✅ Name: <b>{name}</b>\n\nStep 4/5 — Enter default <b>amount</b> in ₹ (or 0 to skip):",
        parse_mode="HTML"
    )


@router.message(PayeeStates.waiting_amount)
async def payee_got_amount(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text.strip())
    if amount is None:
        await message.answer("❌ Invalid amount. Enter a number or 0:")
        return
    await state.update_data(amount=amount if amount > 0 else None)
    await state.set_state(PayeeStates.waiting_note)
    await message.answer("Step 5/5 — Enter a default <b>note</b> (or send <i>skip</i>):",
                         parse_mode="HTML")


@router.message(PayeeStates.waiting_note)
async def payee_got_note(message: Message, state: FSMContext) -> None:
    note_text = message.text.strip()
    note = None if note_text.lower() == "skip" else note_text[:50]
    data = await state.get_data()
    await state.clear()

    payee_id = await repo.add_payee(
        message.from_user.id,
        data["label"], data["vpa"], data["payee_name"],
        data.get("amount"), note
    )
    await message.answer(
        f"✅ <b>Payee saved!</b>\n\n"
        f"💳 <b>{data['label']}</b>\n"
        f"🔗 <code>{data['vpa']}</code>\n"
        f"👤 {data['payee_name']}\n\n"
        f"Tap it in /mypayees for instant QR generation.",
        parse_mode="HTML", reply_markup=home_button()
    )


# ── 1-tap generate from payee ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("payee:gen:"))
async def cb_payee_generate(call: CallbackQuery, state: FSMContext) -> None:
    payee_id = int(call.data.split(":")[2])
    payee = await repo.get_payee(payee_id, call.from_user.id)
    if not payee:
        await call.answer("❌ Payee not found.", show_alert=True)
        return

    from app.handlers.generate import _generate_and_send
    payload = build_upi_payload(UPIPayload(
        vpa=payee["vpa"],
        payee_name=payee["payee_name"],
        amount=float(payee["amount"]) if payee.get("amount") else None,
        note=payee.get("note"),
    ))
    await call.answer("⏳ Generating…")
    await _generate_and_send(
        call.message, payload, "upi",
        label=payee["label"],
        payee_name=payee["payee_name"],
        amount=float(payee["amount"]) if payee.get("amount") else None,
        vpa=payee["vpa"],
    )


# ── Manage / delete payees ────────────────────────────────────────────────

@router.callback_query(F.data == "payee:manage")
async def cb_payee_manage(call: CallbackQuery) -> None:
    payees = await repo.get_payees(call.from_user.id)
    if not payees:
        await call.answer("No payees to manage.", show_alert=True)
        return
    await call.message.edit_text(
        "🗑️ <b>Manage Payees</b>\n\nTap a payee to delete it:",
        parse_mode="HTML", reply_markup=payee_manage_keyboard(payees)
    )
    await call.answer()


@router.callback_query(F.data.startswith("payee:del:"))
async def cb_payee_delete(call: CallbackQuery) -> None:
    payee_id = int(call.data.split(":")[2])
    payee = await repo.get_payee(payee_id, call.from_user.id)
    if not payee:
        await call.answer("❌ Not found.", show_alert=True)
        return
    await call.message.edit_text(
        f"🗑️ Delete payee <b>{payee['label']}</b>?",
        parse_mode="HTML",
        reply_markup=confirm_keyboard(f"payee:confirm_del:{payee_id}", "payee:manage")
    )
    await call.answer()


@router.callback_query(F.data.startswith("payee:confirm_del:"))
async def cb_payee_confirm_delete(call: CallbackQuery) -> None:
    payee_id = int(call.data.split(":")[2])
    await repo.delete_payee(payee_id, call.from_user.id)
    await call.answer("✅ Payee deleted.", show_alert=True)
    payees = await repo.get_payees(call.from_user.id)
    await call.message.edit_text(
        "💳 <b>My Payees</b>\n\nPayee deleted successfully.",
        parse_mode="HTML", reply_markup=payees_keyboard(payees)
    )
