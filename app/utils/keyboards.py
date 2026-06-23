"""
keyboards.py — All InlineKeyboardMarkup builders in one place.
"""
from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── Home card ─────────────────────────────────────────────────────────────

def home_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 UPI QR",    callback_data="gen:upi"),
        InlineKeyboardButton(text="🔗 Other QR",  callback_data="gen:other"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 My Payees", callback_data="payees:list"),
        InlineKeyboardButton(text="🕘 History",   callback_data="history:list"),
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Templates", callback_data="templates:list"),
        InlineKeyboardButton(text="⚙️ Settings",  callback_data="settings:main"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 My Profile", callback_data="profile:view"),
        InlineKeyboardButton(text="❓ Help",        callback_data="help:main"),
    )
    builder.row(
        InlineKeyboardButton(text="⭐ Donate Stars", callback_data="donate:stars"),
    )
    return builder.as_markup()


# ── QR type selector ──────────────────────────────────────────────────────

def qr_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌐 URL",    callback_data="qrtype:url"),
        InlineKeyboardButton(text="📝 Text",   callback_data="qrtype:text"),
    )
    builder.row(
        InlineKeyboardButton(text="📶 Wi-Fi",  callback_data="qrtype:wifi"),
        InlineKeyboardButton(text="👤 vCard",  callback_data="qrtype:vcard"),
    )
    builder.row(
        InlineKeyboardButton(text="✉️ Email",  callback_data="qrtype:email"),
        InlineKeyboardButton(text="💬 SMS",    callback_data="qrtype:sms"),
    )
    builder.row(
        InlineKeyboardButton(text="📍 Geo",    callback_data="qrtype:geo"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Home",   callback_data="home"),
    )
    return builder.as_markup()


# ── Template browser ──────────────────────────────────────────────────────

def templates_keyboard(themes: list[dict], current: str, page: int = 0,
                       per_page: int = 6) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    chunk = themes[start:start + per_page]
    for t in chunk:
        mark = "✅ " if t["id"] == current else ""
        builder.row(InlineKeyboardButton(
            text=f"{mark}{t['name']}",
            callback_data=f"template:select:{t['id']}",
        ))
    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"template:page:{page-1}"))
    if start + per_page < len(themes):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"template:page:{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()


# ── Size selector ─────────────────────────────────────────────────────────

def size_keyboard(current: str = "1080x1350") -> InlineKeyboardMarkup:
    sizes = [("📱 Portrait (1080×1350)", "1080x1350"),
             ("⬛ Square (1080×1080)",   "1080x1080"),
             ("🔲 HD QR (2048×2048)",    "2048x2048")]
    builder = InlineKeyboardBuilder()
    for label, val in sizes:
        mark = "✅ " if val == current else ""
        builder.row(InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"size:select:{val}",
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="settings:main"))
    return builder.as_markup()


# ── My Payees ─────────────────────────────────────────────────────────────

def payees_keyboard(payees: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in payees:
        amount_str = f" · ₹{p['amount']:.0f}" if p.get("amount") else ""
        builder.row(InlineKeyboardButton(
            text=f"💳 {p['label']}{amount_str}",
            callback_data=f"payee:gen:{p['id']}",
        ))
    builder.row(
        InlineKeyboardButton(text="➕ Add Payee", callback_data="payee:add"),
        InlineKeyboardButton(text="🗑️ Manage",   callback_data="payee:manage"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()


def payee_manage_keyboard(payees: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in payees:
        builder.row(InlineKeyboardButton(
            text=f"🗑️ Delete: {p['label']}",
            callback_data=f"payee:del:{p['id']}",
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="payees:list"))
    return builder.as_markup()


# ── History ───────────────────────────────────────────────────────────────

def history_keyboard(records: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in records:
        label = f"{r['qr_type'].upper()} · {str(r['created_at'])[:10]}"
        builder.row(InlineKeyboardButton(
            text=f"🔄 {label}",
            callback_data=f"history:regen:{r['id']}",
        ))
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()


# ── Settings ──────────────────────────────────────────────────────────────

def settings_keyboard(us: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    wm_status = "✅ On" if us.get("watermark_enabled") else "❌ Off"
    builder.row(
        InlineKeyboardButton(text=f"💧 Watermark: {wm_status}", callback_data="settings:toggle_wm"),
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Change Template",  callback_data="templates:list"),
        InlineKeyboardButton(text="📐 Change Size",      callback_data="settings:size"),
    )
    builder.row(
        InlineKeyboardButton(text="🖼️ Set Logo",  callback_data="settings:setlogo"),
        InlineKeyboardButton(text="🗑️ Del Logo",  callback_data="settings:dellogo"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Delete My Account", callback_data="settings:delete_me"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()


# ── Admin panel ───────────────────────────────────────────────────────────

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 Broadcast",     callback_data="admin:broadcast"),
        InlineKeyboardButton(text="📊 Stats",         callback_data="admin:stats"),
    )
    builder.row(
        InlineKeyboardButton(text="💧 Watermark",     callback_data="admin:watermark"),
        InlineKeyboardButton(text="🔐 ForceSub",      callback_data="admin:forcesub"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Audit Log",     callback_data="admin:audit"),
        InlineKeyboardButton(text="🏥 Health",        callback_data="admin:health"),
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Ban User",      callback_data="admin:ban"),
        InlineKeyboardButton(text="✅ Unban User",    callback_data="admin:unban"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()


def owner_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Add Admin",  callback_data="owner:addadmin"),
        InlineKeyboardButton(text="➖ Del Admin",  callback_data="owner:deladmin"),
    )
    builder.row(
        InlineKeyboardButton(text="📤 Export Users",  callback_data="owner:export:users"),
        InlineKeyboardButton(text="📤 Export Stats",  callback_data="owner:export:stats"),
        InlineKeyboardButton(text="📤 Export Audit",  callback_data="owner:export:audit"),
    )
    builder.row(
        InlineKeyboardButton(text="🔧 Maintenance On",  callback_data="owner:maintenance:on"),
        InlineKeyboardButton(text="✅ Maintenance Off", callback_data="owner:maintenance:off"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()


# ── ForceSub join buttons ─────────────────────────────────────────────────

def build_forcesub_keyboard(chats: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for chat in chats:
        title = chat.get("title") or "Join Channel"
        if chat.get("username"):
            url = f"https://t.me/{chat['username'].lstrip('@')}"
        else:
            url = chat.get("invite_link", "")
        if url:
            builder.row(InlineKeyboardButton(text=f"📢 {title}", url=url))
    builder.row(InlineKeyboardButton(text="✅ Verify Membership", callback_data="forcesub:verify"))
    return builder.as_markup()


# ── Confirm dialog ────────────────────────────────────────────────────────

def confirm_keyboard(yes_cb: str, no_cb: str = "home") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Confirm", callback_data=yes_cb),
        InlineKeyboardButton(text="❌ Cancel",  callback_data=no_cb),
    )
    return builder.as_markup()


# ── Simple back button ────────────────────────────────────────────────────

def back_keyboard(cb: str = "home") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data=cb))
    return builder.as_markup()


def home_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Home", callback_data="home"))
    return builder.as_markup()
