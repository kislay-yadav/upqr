"""
qr_service.py — Pure-function QR payload builders and segno-based QR generation.
All payload functions are side-effect-free and fully testable.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import quote, urlencode

import segno
from PIL import Image

from app.logger import get_logger

log = get_logger(__name__)


# ── QR Types ──────────────────────────────────────────────────────────────

class QRType(str, Enum):
    UPI     = "upi"
    URL     = "url"
    TEXT    = "text"
    WIFI    = "wifi"
    VCARD   = "vcard"
    EMAIL   = "email"
    SMS     = "sms"
    GEO     = "geo"


# ── Payload builders (pure functions) ─────────────────────────────────────

@dataclass
class UPIPayload:
    vpa: str
    payee_name: str
    amount: Optional[float] = None
    note: Optional[str] = None
    transaction_ref: Optional[str] = None
    currency: str = "INR"


def validate_vpa(vpa: str) -> bool:
    """Format-only VPA validation. Does NOT claim bank-level verification."""
    pattern = r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$"
    return bool(re.match(pattern, vpa.strip()))


def build_upi_payload(p: UPIPayload) -> str:
    """
    Build a standards-compliant UPI URI.
    Format: upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR&tn=<note>&tr=<ref>
    """
    params: dict[str, str] = {
        "pa": p.vpa.strip(),
        "pn": p.payee_name.strip(),
        "cu": p.currency,
    }
    if p.amount is not None and p.amount > 0:
        params["am"] = f"{p.amount:.2f}"
    if p.note:
        params["tn"] = p.note.strip()[:50]
    if p.transaction_ref:
        params["tr"] = p.transaction_ref.strip()[:35]

    # URL-encode values per UPI spec (quote_via=quote for space→%20)
    encoded = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    return f"upi://pay?{encoded}"


def build_wifi_payload(ssid: str, password: str, auth_type: str = "WPA",
                       hidden: bool = False) -> str:
    """Build Wi-Fi QR payload (MECARD format)."""
    h = "true" if hidden else "false"
    pw = password.replace("\\", "\\\\").replace(";", "\\;").replace('"', '\\"').replace(",", "\\,")
    ss = ssid.replace("\\", "\\\\").replace(";", "\\;").replace('"', '\\"').replace(",", "\\,")
    return f"WIFI:T:{auth_type};S:{ss};P:{pw};H:{h};;"


def build_vcard_payload(name: str, phone: str, email: str = "",
                        org: str = "", url: str = "") -> str:
    """Build vCard 3.0 QR payload."""
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{name}",
        f"FN:{name}",
    ]
    if phone:
        lines.append(f"TEL:{phone}")
    if email:
        lines.append(f"EMAIL:{email}")
    if org:
        lines.append(f"ORG:{org}")
    if url:
        lines.append(f"URL:{url}")
    lines.append("END:VCARD")
    return "\n".join(lines)


def build_email_payload(to: str, subject: str = "", body: str = "") -> str:
    params = {}
    if subject:
        params["subject"] = subject
    if body:
        params["body"] = body
    qs = urlencode(params) if params else ""
    return f"mailto:{to}{'?' + qs if qs else ''}"


def build_sms_payload(phone: str, message: str = "") -> str:
    msg_enc = quote(message, safe="")
    return f"sms:{phone}{'?body=' + msg_enc if message else ''}"


def build_geo_payload(lat: float, lon: float, query: str = "") -> str:
    base = f"geo:{lat},{lon}"
    if query:
        base += f"?q={quote(query, safe='')}"
    return base


# ── QR rendering ─────────────────────────────────────────────────────────

ERROR_CORRECTION_MAP = {
    "L": segno.QRErrorCorrection.L,
    "M": segno.QRErrorCorrection.M,
    "Q": segno.QRErrorCorrection.Q,
    "H": segno.QRErrorCorrection.H,
}


def generate_qr_image(
    payload: str,
    size_px: int = 2048,
    error_correction: str = "Q",
    dark: str = "#000000",
    light: str = "#FFFFFF",
    logo_image: Optional[Image.Image] = None,
) -> Image.Image:
    """
    Generate a high-resolution QR code image using segno.
    Applies logo overlay if provided (forces H error correction for reliability).
    Returns a PIL Image.
    """
    ec = "H" if logo_image else error_correction
    ec_val = ERROR_CORRECTION_MAP.get(ec.upper(), segno.QRErrorCorrection.Q)

    qr = segno.make_qr(payload, error=ec_val)

    # Calculate scale to hit target size with quiet zone
    quiet_zone = 4
    module_count = qr.symbol_size()[0]
    total_modules = module_count + 2 * quiet_zone
    scale = max(1, size_px // total_modules)

    buf = io.BytesIO()
    qr.save(
        buf,
        kind="PNG",
        scale=scale,
        border=quiet_zone,
        dark=dark,
        light=light,
    )
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")

    # Resize to exact size
    img = img.resize((size_px, size_px), Image.LANCZOS)

    if logo_image:
        img = _overlay_logo(img, logo_image)

    return img


def _overlay_logo(qr_img: Image.Image, logo: Image.Image,
                  max_coverage: float = 0.15) -> Image.Image:
    """
    Overlay logo centred on QR code.
    Resizes logo so it covers at most max_coverage of QR area.
    Applies rounded corners and a subtle shadow.
    """
    qr_size = qr_img.size[0]
    max_logo_px = int(qr_size * (max_coverage ** 0.5))

    logo = logo.convert("RGBA")
    logo.thumbnail((max_logo_px, max_logo_px), Image.LANCZOS)

    # Rounded corners mask
    from PIL import ImageDraw, ImageFilter
    w, h = logo.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    radius = min(w, h) // 6
    draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    logo.putalpha(mask)

    # Shadow layer
    shadow_offset = max(2, qr_size // 200)
    shadow = Image.new("RGBA", qr_img.size, (0, 0, 0, 0))
    sx = (qr_size - w) // 2 + shadow_offset
    sy = (qr_size - h) // 2 + shadow_offset
    shadow_logo = Image.new("RGBA", (w, h), (0, 0, 0, 80))
    shadow_logo.putalpha(mask)
    shadow.paste(shadow_logo, (sx, sy), shadow_logo)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_offset * 2))
    qr_img = Image.alpha_composite(qr_img, shadow)

    # White padding behind logo
    pad = max(4, qr_size // 100)
    pad_size = (w + pad * 2, h + pad * 2)
    pad_img = Image.new("RGBA", pad_size, (255, 255, 255, 255))
    pad_mask = Image.new("L", pad_size, 0)
    pd = ImageDraw.Draw(pad_mask)
    pd.rounded_rectangle([0, 0, pad_size[0] - 1, pad_size[1] - 1],
                         radius=radius + pad, fill=255)
    pad_img.putalpha(pad_mask)
    px = (qr_size - pad_size[0]) // 2
    py = (qr_size - pad_size[1]) // 2
    qr_img.paste(pad_img, (px, py), pad_img)

    # Logo itself
    lx = (qr_size - w) // 2
    ly = (qr_size - h) // 2
    qr_img.paste(logo, (lx, ly), logo)
    return qr_img


def qr_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt, optimize=True)
    return buf.getvalue()
