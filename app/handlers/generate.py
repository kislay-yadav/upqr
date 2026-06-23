"""
generate.py — UPI and QR code generation handlers.
Uses FSM (finite-state machine) for multi-step wizard flows.
"""
from __future__ import annotations

import io
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, Message,
)

from app.config import settings
from app.database import repo
from app.logger import get_logger
from app.services.poster_renderer import render_poster
from app.services.qr_service import (
    UPIPayload, QRType,
    build_upi_payload, build_wifi_payload, build_vcard_payload,
    build_email_payload, build_sms_payload, build_geo_payload,
    validate_vpa,
)
from app.utils.helpers import bytes_to_io, parse_amount, validate_vpa_simple
from app.utils.keyboards import (
    home_button, qr_type_keyboard,
    back_keyboard,
)

log = get_logger(__name__)
router = Router(name="generate")


# ── FSM States ────────────────────────────────────────────────────────────

class UPIStates(StatesGroup):
    waiting_vpa         = State()
    waiting_name        = State()
    waiting_amount      = State()
    waiting_note        = State()


class QRStates(StatesGroup):
    waiting_url         = State()
    waiting_text        = State()
    # Wi-Fi
    waiting_wifi_ssid   = State()
    waiting_wifi_pass   = State()
    waiting_wifi_auth   = State()
    # vCard
    waiting_vc_name     = State()
    waiting_vc_phone    = State()
    waiting_vc_email    = State()
    waiting_vc_org      = State()
    # Email
    waiting_email_to    = State()
    waiting_email_subj  = State()
    waiting_email_body  = State()
    # SMS
    waiting_sms_phone   = State()
    waiting_sms_msg     = State()
    # Geo
    waiting_geo_lat     = State()
    waiting_geo_lon     = State()


# ── /generate entry ───────────────────────────────────────────────────────

@router.message(Command("generate"))
@router.callback_query(F.data == "gen:other")
async def cmd_generate(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = "🔗 <b>Choose QR Type</b>\n\nSelect the type of QR code to generate:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=qr_type_keyboard(), parse_mode="HTML")
    else:
        await event.message.edit_text(text, reply_markup=qr_type_keyboard(), parse_mode="HTML")
        await event.answer()


# ── UPI wizard ────────────────────────────────────────────────────────────

@router.message(Command("upi"))
@router.callback_query(F.data == "gen:upi")
async def cmd_upi_start(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(UPIStates.waiting_vpa)
    text = (
        "💳 <b>UPI QR Generator</b>\n\n"
        "Step 1/4 — Enter the <b>UPI ID / VPA</b>:\n\n"
        "<i>Example: name@upi, mobile@paytm, handle@okaxis</i>"
    )
    kb = back_keyboard("home")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()


@router.message(UPIStates.waiting_vpa)
async def upi_got_vpa(message: Message, state: FSMContext) -> None:
    vpa = message.text.strip()
    if not validate_vpa_simple(vpa):
        await message.answer(
            "❌ <b>Invalid UPI ID format.</b>\n\n"
            "Please enter a valid VPA like <code>name@upi</code> or <code>mobile@paytm</code>.",
            parse_mode="HTML"
        )
        return
    await state.update_data(vpa=vpa)
    await state.set_state(UPIStates.waiting_name)
    await message.answer(
        f"✅ VPA: <code>{vpa}</code>\n\n"
        "Step 2/4 — Enter the <b>Payee Name</b>:\n\n"
        "<i>This name appears on the payment screen.</i>",
        parse_mode="HTML", reply_markup=back_keyboard("gen:upi")
    )


@router.message(UPIStates.waiting_name)
async def upi_got_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:50]
    await state.update_data(payee_name=name)
    await state.set_state(UPIStates.waiting_amount)
    await message.answer(
        f"✅ Name: <b>{name}</b>\n\n"
        "Step 3/4 — Enter <b>Amount</b> (₹) or send <b>0</b> to skip:",
        parse_mode="HTML", reply_markup=back_keyboard("gen:upi")
    )


@router.message(UPIStates.waiting_amount)
async def upi_got_amount(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text.strip())
    if amount is None:
        await message.answer("❌ Invalid amount. Please enter a number (e.g. 100 or 0 to skip).")
        return
    await state.update_data(amount=amount if amount > 0 else None)
    await state.set_state(UPIStates.waiting_note)
    await message.answer(
        "Step 4/4 — Enter a <b>payment note</b> or send <b>skip</b>:",
        parse_mode="HTML", reply_markup=back_keyboard("gen:upi")
    )


@router.message(UPIStates.waiting_note)
async def upi_got_note(message: Message, state: FSMContext) -> None:
    note_text = message.text.strip()
    note = None if note_text.lower() == "skip" else note_text[:50]
    data = await state.get_data()
    await state.clear()

    payload_obj = UPIPayload(
        vpa=data["vpa"],
        payee_name=data["payee_name"],
        amount=data.get("amount"),
        note=note,
    )
    payload = build_upi_payload(payload_obj)
    await _generate_and_send(
        message, payload, "upi",
        payee_name=data["payee_name"],
        amount=data.get("amount"),
        vpa=data["vpa"],
    )


# ── QR type router ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("qrtype:"))
async def cb_qr_type(call: CallbackQuery, state: FSMContext) -> None:
    qr_type = call.data.split(":")[1]
    await _start_qr_wizard(call, state, qr_type)
    await call.answer()


@router.message(Command("qr"))
async def cmd_qr(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🔗 Choose QR type:", reply_markup=qr_type_keyboard())


# ── QR shortcut commands ──────────────────────────────────────────────────

@router.message(Command("qr_url"))
async def cmd_qr_url(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "url")

@router.message(Command("qr_text"))
async def cmd_qr_text(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "text")

@router.message(Command("qr_wifi"))
async def cmd_qr_wifi(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "wifi")

@router.message(Command("qr_vcard"))
async def cmd_qr_vcard(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "vcard")

@router.message(Command("qr_email"))
async def cmd_qr_email(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "email")

@router.message(Command("qr_sms"))
async def cmd_qr_sms(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "sms")

@router.message(Command("qr_geo"))
async def cmd_qr_geo(message: Message, state: FSMContext) -> None:
    await _start_qr_wizard(message, state, "geo")


async def _start_qr_wizard(event: Message | CallbackQuery, state: FSMContext, qr_type: str) -> None:
    await state.clear()
    prompts = {
        "url":   ("🌐 URL QR", "Enter the URL to encode:", QRStates.waiting_url),
        "text":  ("📝 Text QR", "Enter the text to encode:", QRStates.waiting_text),
        "wifi":  ("📶 Wi-Fi QR", "Enter the Wi-Fi network name (SSID):", QRStates.waiting_wifi_ssid),
        "vcard": ("👤 vCard QR", "Enter the contact's full name:", QRStates.waiting_vc_name),
        "email": ("✉️ Email QR", "Enter the recipient email address:", QRStates.waiting_email_to),
        "sms":   ("💬 SMS QR",  "Enter the phone number (with country code):", QRStates.waiting_sms_phone),
        "geo":   ("📍 Location QR", "Enter latitude (e.g. 28.6139):", QRStates.waiting_geo_lat),
    }
    title, prompt, next_state = prompts.get(qr_type, ("QR", "Enter value:", QRStates.waiting_text))
    await state.set_state(next_state)
    await state.update_data(qr_type=qr_type)

    text = f"<b>{title}</b>\n\n{prompt}"
    kb   = back_keyboard("home")
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ── URL ───────────────────────────────────────────────────────────────────

@router.message(QRStates.waiting_url)
async def qr_got_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip()
    if not url.startswith(("http://", "https://", "ftp://")):
        url = "https://" + url
    await state.clear()
    await _generate_and_send(message, url, "url")


@router.message(QRStates.waiting_text)
async def qr_got_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _generate_and_send(message, message.text.strip(), "text")


# ── Wi-Fi ─────────────────────────────────────────────────────────────────

@router.message(QRStates.waiting_wifi_ssid)
async def qr_wifi_ssid(message: Message, state: FSMContext) -> None:
    await state.update_data(ssid=message.text.strip())
    await state.set_state(QRStates.waiting_wifi_pass)
    await message.answer("Enter the Wi-Fi <b>password</b> (or send <i>open</i> if no password):",
                         parse_mode="HTML")


@router.message(QRStates.waiting_wifi_pass)
async def qr_wifi_pass(message: Message, state: FSMContext) -> None:
    pw = message.text.strip()
    data = await state.get_data()
    auth = "nopass" if pw.lower() == "open" else "WPA"
    password = "" if pw.lower() == "open" else pw
    await state.clear()
    payload = build_wifi_payload(data["ssid"], password, auth)
    await _generate_and_send(message, payload, "wifi", label=f"Wi-Fi: {data['ssid']}")


# ── vCard ─────────────────────────────────────────────────────────────────

@router.message(QRStates.waiting_vc_name)
async def qr_vc_name(message: Message, state: FSMContext) -> None:
    await state.update_data(vc_name=message.text.strip())
    await state.set_state(QRStates.waiting_vc_phone)
    await message.answer("Enter the phone number (or send <i>skip</i>):", parse_mode="HTML")


@router.message(QRStates.waiting_vc_phone)
async def qr_vc_phone(message: Message, state: FSMContext) -> None:
    phone = "" if message.text.strip().lower() == "skip" else message.text.strip()
    await state.update_data(vc_phone=phone)
    await state.set_state(QRStates.waiting_vc_email)
    await message.answer("Enter the email address (or send <i>skip</i>):", parse_mode="HTML")


@router.message(QRStates.waiting_vc_email)
async def qr_vc_email(message: Message, state: FSMContext) -> None:
    email = "" if message.text.strip().lower() == "skip" else message.text.strip()
    await state.update_data(vc_email=email)
    await state.set_state(QRStates.waiting_vc_org)
    await message.answer("Enter the organisation / company (or send <i>skip</i>):", parse_mode="HTML")


@router.message(QRStates.waiting_vc_org)
async def qr_vc_org(message: Message, state: FSMContext) -> None:
    org = "" if message.text.strip().lower() == "skip" else message.text.strip()
    data = await state.get_data()
    await state.clear()
    payload = build_vcard_payload(data["vc_name"], data.get("vc_phone", ""),
                                  data.get("vc_email", ""), org)
    await _generate_and_send(message, payload, "vcard", label=data["vc_name"])


# ── Email ─────────────────────────────────────────────────────────────────

@router.message(QRStates.waiting_email_to)
async def qr_email_to(message: Message, state: FSMContext) -> None:
    await state.update_data(email_to=message.text.strip())
    await state.set_state(QRStates.waiting_email_subj)
    await message.answer("Enter subject (or <i>skip</i>):", parse_mode="HTML")


@router.message(QRStates.waiting_email_subj)
async def qr_email_subj(message: Message, state: FSMContext) -> None:
    subj = "" if message.text.strip().lower() == "skip" else message.text.strip()
    await state.update_data(email_subj=subj)
    await state.set_state(QRStates.waiting_email_body)
    await message.answer("Enter body message (or <i>skip</i>):", parse_mode="HTML")


@router.message(QRStates.waiting_email_body)
async def qr_email_body(message: Message, state: FSMContext) -> None:
    body = "" if message.text.strip().lower() == "skip" else message.text.strip()
    data = await state.get_data()
    await state.clear()
    payload = build_email_payload(data["email_to"], data.get("email_subj", ""), body)
    await _generate_and_send(message, payload, "email", label=data["email_to"])


# ── SMS ───────────────────────────────────────────────────────────────────

@router.message(QRStates.waiting_sms_phone)
async def qr_sms_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(sms_phone=message.text.strip())
    await state.set_state(QRStates.waiting_sms_msg)
    await message.answer("Enter the SMS message (or <i>skip</i>):", parse_mode="HTML")


@router.message(QRStates.waiting_sms_msg)
async def qr_sms_msg(message: Message, state: FSMContext) -> None:
    msg = "" if message.text.strip().lower() == "skip" else message.text.strip()
    data = await state.get_data()
    await state.clear()
    payload = build_sms_payload(data["sms_phone"], msg)
    await _generate_and_send(message, payload, "sms", label=data["sms_phone"])


# ── Geo ───────────────────────────────────────────────────────────────────

@router.message(QRStates.waiting_geo_lat)
async def qr_geo_lat(message: Message, state: FSMContext) -> None:
    try:
        lat = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid latitude. Enter a decimal number like 28.6139.")
        return
    await state.update_data(geo_lat=lat)
    await state.set_state(QRStates.waiting_geo_lon)
    await message.answer("Enter <b>longitude</b> (e.g. 77.2090):", parse_mode="HTML")


@router.message(QRStates.waiting_geo_lon)
async def qr_geo_lon(message: Message, state: FSMContext) -> None:
    try:
        lon = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid longitude.")
        return
    data = await state.get_data()
    await state.clear()
    payload = build_geo_payload(data["geo_lat"], lon)
    await _generate_and_send(message, payload, "geo",
                              label=f"Lat {data['geo_lat']:.4f}, Lon {lon:.4f}")


# ── Core render + send ────────────────────────────────────────────────────

async def _generate_and_send(
    message: Message,
    payload: str,
    qr_type: str,
    label: str = "",
    payee_name: str = "",
    amount: Optional[float] = None,
    vpa: str = "",
) -> None:
    """Render poster and send to user."""
    user_id = message.from_user.id
    us = await repo.get_user_settings(user_id)
    user = await repo.get_user(user_id)

    wm_enabled = us.get("watermark_enabled", True)
    wm_text    = await repo.get_setting("watermark_text", settings.default_watermark_text)
    global_wm  = await repo.get_setting("watermark_enabled", "true") == "true"

    # Load logo if set
    logo_img = None
    if user and user.get("logo_file_id"):
        try:
            logo_img = await _fetch_logo(message.bot, user["logo_file_id"])
        except Exception as exc:
            log.warning("logo_fetch_failed", user_id=user_id, error=str(exc))

    thinking = await message.answer("⏳ Generating your QR poster…")

    try:
        image_bytes = render_poster(
            payload=payload,
            qr_type=qr_type,
            theme_id=us.get("preferred_template", "minimal_pro"),
            size=us.get("preferred_size", "1080x1350"),
            label=label,
            payee_name=payee_name,
            amount=amount,
            vpa=vpa,
            watermark_text=wm_text if (wm_enabled and global_wm) else None,
            watermark_enabled=wm_enabled and global_wm,
            logo_image=logo_img,
        )
    except Exception as exc:
        log.error("render_error", user_id=user_id, error=str(exc), exc_info=True)
        await thinking.delete()
        await message.answer("❌ Generation failed. Please try again.")
        return

    await thinking.delete()

    caption = _build_caption(qr_type, payload, payee_name, amount, vpa)
    file    = BufferedInputFile(image_bytes, filename="qr_poster.png")
    sent    = await message.answer_photo(file, caption=caption, parse_mode="HTML",
                                        reply_markup=home_button())

    # Persist
    file_id = sent.photo[-1].file_id if sent.photo else None
    hist_id = await repo.add_history(user_id, qr_type, payload,
                                     us.get("preferred_template", "minimal_pro"),
                                     us.get("preferred_size", "1080x1350"), file_id)
    await repo.increment_generated(user_id)


def _build_caption(qr_type: str, payload: str, payee_name: str,
                   amount: Optional[float], vpa: str) -> str:
    if qr_type == "upi":
        lines = ["💳 <b>UPI Payment QR</b>"]
        if payee_name:
            lines.append(f"👤 {payee_name}")
        if vpa:
            lines.append(f"🔗 <code>{vpa}</code>")
        if amount:
            lines.append(f"💰 ₹{amount:,.2f}")
        lines.append("\n<i>Scan with any UPI app to pay.</i>")
        return "\n".join(lines)
    return f"✅ <b>{qr_type.upper()} QR Code</b>\n<i>Scan with your camera or a QR reader.</i>"


async def _fetch_logo(bot, file_id: str):
    from PIL import Image
    file = await bot.get_file(file_id)
    buf  = io.BytesIO()
    await bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")
