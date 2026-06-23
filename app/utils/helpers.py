"""
helpers.py — Shared utility / formatting helpers.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Optional

from aiogram.types import User


def mention(user: User) -> str:
    """Telegram mention string."""
    name = user.full_name or user.username or str(user.id)
    return f"<a href='tg://user?id={user.id}'>{name}</a>"


def format_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d %b %Y, %H:%M UTC")


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def human_size(size_str: str) -> str:
    """'1080x1350' → '1080 × 1350'"""
    parts = size_str.split("x")
    if len(parts) == 2:
        return f"{parts[0]} × {parts[1]}"
    return size_str


def validate_vpa_simple(vpa: str) -> bool:
    pattern = r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$"
    return bool(re.match(pattern, vpa.strip()))


def parse_amount(text: str) -> Optional[float]:
    """Parse a user-provided amount string; returns None if invalid."""
    try:
        text = text.replace(",", "").replace("₹", "").strip()
        val = float(text)
        if val < 0 or val > 1_00_00_000:  # 1 crore max
            return None
        return round(val, 2)
    except ValueError:
        return None


def chunk_list(lst: list, n: int) -> list[list]:
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def qr_type_label(qr_type: str) -> str:
    labels = {
        "upi":   "💳 UPI Payment",
        "url":   "🌐 URL",
        "text":  "📝 Text",
        "wifi":  "📶 Wi-Fi",
        "vcard": "👤 vCard",
        "email": "✉️ Email",
        "sms":   "💬 SMS",
        "geo":   "📍 Location",
    }
    return labels.get(qr_type, qr_type.upper())


def bytes_to_io(data: bytes, filename: str = "qr.png") -> io.BufferedIOBase:
    buf = io.BytesIO(data)
    buf.name = filename
    buf.seek(0)
    return buf
