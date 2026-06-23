"""
poster_renderer.py — Premium poster generation using Pillow.
Loads theme configs from themes.json; new themes require no code changes.
Supports 1080×1350, 1080×1080, and QR-only 2048×2048 outputs.
"""
from __future__ import annotations

import io
import json
import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.logger import get_logger
from app.services.qr_service import generate_qr_image

log = get_logger(__name__)

# ── Asset paths ───────────────────────────────────────────────────────────

ASSETS_DIR   = Path(__file__).parent.parent.parent / "assets"
FONTS_DIR    = Path(__file__).parent.parent.parent / "fonts"
THEMES_FILE  = ASSETS_DIR / "templates" / "themes.json"

# Font cache
_font_cache: dict[tuple, ImageFont.FreeTypeFont] = {}


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key in _font_cache:
        return _font_cache[key]

    # Try bundled font directory first
    for ext in (".ttf", ".otf"):
        p = FONTS_DIR / f"{name}{ext}"
        if p.exists():
            f = ImageFont.truetype(str(p), size)
            _font_cache[key] = f
            return f

    # Fallback: Poppins → default font (ensures it never crashes)
    try:
        fallback = FONTS_DIR / "Poppins-Regular.ttf"
        if fallback.exists():
            f = ImageFont.truetype(str(fallback), size)
        else:
            f = ImageFont.load_default()
        _font_cache[key] = f
        return f
    except Exception:
        return ImageFont.load_default()


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ── Theme loader ──────────────────────────────────────────────────────────

_themes_cache: Optional[dict] = None


def load_themes() -> dict:
    global _themes_cache
    if _themes_cache is None:
        with open(THEMES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _themes_cache = {t["id"]: t for t in data["themes"] if t.get("enabled", True)}
    return _themes_cache


def get_theme(theme_id: str) -> dict:
    themes = load_themes()
    return themes.get(theme_id, themes.get("minimal_pro", next(iter(themes.values()))))


def list_themes() -> list[dict]:
    return list(load_themes().values())


# ── Background builders ───────────────────────────────────────────────────

def _make_background(theme: dict, width: int, height: int) -> Image.Image:
    bg_type = theme.get("bg_type", "solid")

    if bg_type == "solid":
        color = _hex_to_rgb(theme.get("bg_color", "#FFFFFF"))
        return Image.new("RGBA", (width, height), (*color, 255))

    elif bg_type == "gradient":
        stops = theme.get("bg_gradient", ["#FFFFFF", "#EEEEEE"])
        angle = theme.get("bg_gradient_angle", 135)
        return _render_gradient(width, height, stops, angle)

    return Image.new("RGBA", (width, height), (255, 255, 255, 255))


def _render_gradient(width: int, height: int, stops: list[str], angle: int) -> Image.Image:
    """Render a multi-stop linear gradient at the given angle."""
    img = Image.new("RGBA", (width, height))
    pixels = img.load()

    rad = math.radians(angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)

    # Project each pixel onto the gradient axis
    diag = math.sqrt(width ** 2 + height ** 2)
    cx, cy = width / 2, height / 2

    stop_colors = [_hex_to_rgb(s) for s in stops]
    n = len(stop_colors) - 1

    for y in range(height):
        for x in range(width):
            proj = (x - cx) * cos_a + (y - cy) * sin_a
            t = (proj + diag / 2) / diag
            t = max(0.0, min(1.0, t))
            seg = min(int(t * n), n - 1)
            local_t = t * n - seg
            c1, c2 = stop_colors[seg], stop_colors[min(seg + 1, n)]
            r = int(c1[0] + (c2[0] - c1[0]) * local_t)
            g = int(c1[1] + (c2[1] - c1[1]) * local_t)
            b = int(c1[2] + (c2[2] - c1[2]) * local_t)
            pixels[x, y] = (r, g, b, 255)

    return img


# ── Card / glass overlay ──────────────────────────────────────────────────

def _draw_glass_card(img: Image.Image, rect: tuple, radius: int, alpha: int = 40) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    d = ImageDraw.Draw(overlay)
    x1, y1, x2, y2 = rect
    d.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=(255, 255, 255, alpha))
    return Image.alpha_composite(img, overlay)


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, rect: tuple, radius: int,
                       fill: tuple, outline: Optional[tuple] = None, width: int = 2) -> None:
    draw.rounded_rectangle(rect, radius=radius, fill=fill,
                           outline=outline, width=width if outline else 0)


# ── Text helpers ──────────────────────────────────────────────────────────

def _draw_text_centered(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                        y: int, width: int, color: tuple) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (width - w) // 2
    draw.text((x, y), text, font=font, fill=color)


def _text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


# ── Main poster renderer ──────────────────────────────────────────────────

def render_poster(
    payload: str,
    qr_type: str,
    theme_id: str,
    size: str,
    label: str = "",
    payee_name: str = "",
    amount: Optional[float] = None,
    vpa: str = "",
    watermark_text: Optional[str] = None,
    watermark_enabled: bool = True,
    logo_image: Optional[Image.Image] = None,
) -> bytes:
    """
    Render a full poster image and return PNG bytes.

    Args:
        payload:           The QR payload string.
        qr_type:           E.g. 'upi', 'url', 'wifi', etc.
        theme_id:          Theme identifier from themes.json.
        size:              '1080x1350' | '1080x1080' | '2048x2048'
        label:             Short label shown above QR (e.g. payee label).
        payee_name:        Full payee name.
        amount:            Amount (UPI).
        vpa:               VPA string.
        watermark_text:    Watermark string or None.
        watermark_enabled: Whether to render watermark.
        logo_image:        PIL Image for logo overlay on QR.
    """
    theme = get_theme(theme_id)
    w_str, h_str = size.split("x")
    W, H = int(w_str), int(h_str)

    # QR-only mode (2048x2048)
    if size == "2048x2048":
        qr_img = generate_qr_image(
            payload, size_px=2048,
            dark=theme.get("qr_dark", "#000000"),
            light=theme.get("qr_light", "#FFFFFF"),
            logo_image=logo_image,
        )
        if watermark_enabled and watermark_text:
            qr_img = _add_qr_watermark(qr_img, watermark_text, theme)
        return _to_bytes(qr_img)

    padding = theme.get("padding", 60)
    bg = _make_background(theme, W, H)

    # Glass card overlay
    if theme.get("glass_overlay"):
        card_margin = padding // 2
        bg = _draw_glass_card(
            bg,
            (card_margin, card_margin, W - card_margin, H - card_margin),
            radius=theme.get("border_radius", 24),
            alpha=theme.get("glass_alpha", 40),
        )

    draw = ImageDraw.Draw(bg)
    text_color   = _hex_to_rgba(theme.get("text_color", "#000000"))
    accent_color = _hex_to_rgba(theme.get("accent_color", "#4F46E5"))
    sec_color    = _hex_to_rgba(theme.get("secondary_text", "#6B7280"))
    wm_color     = _hex_to_rgba(theme.get("watermark_color", "#AAAAAA"))

    # Font sizes (relative to canvas width)
    title_size   = max(28, W // 22)
    body_size    = max(22, W // 28)
    label_size   = max(18, W // 34)
    amount_size  = max(36, W // 16)
    wm_size      = max(16, W // 42)

    font_title  = _load_font(theme.get("font_title",  "Poppins-SemiBold"), title_size)
    font_body   = _load_font(theme.get("font_body",   "Inter-Regular"),    body_size)
    font_label  = _load_font(theme.get("font_body",   "Inter-Regular"),    label_size)
    font_amount = _load_font(theme.get("font_title",  "Poppins-SemiBold"), amount_size)
    font_wm     = _load_font(theme.get("font_body",   "Inter-Regular"),    wm_size)

    qr_ratio   = theme.get("qr_size_ratio", 0.60)
    qr_px      = int(min(W, H) * qr_ratio)
    qr_img     = generate_qr_image(
        payload, size_px=qr_px,
        dark=theme.get("qr_dark", "#000000"),
        light=theme.get("qr_light", "#FFFFFF"),
        logo_image=logo_image,
    )
    qr_img_rgb = qr_img.convert("RGBA")

    # Layout: portrait 1080×1350
    if H > W:  # portrait
        header_y = padding
        # ── Header: bot name / label ───────────────────────────────
        header_text = label or ("UPI Payment" if qr_type == "upi" else qr_type.upper() + " Code")
        _draw_text_centered(draw, header_text, font_title, header_y, W, accent_color)
        cur_y = header_y + _text_height(draw, header_text, font_title) + padding // 2

        # ── Payee name ────────────────────────────────────────────
        if payee_name:
            _draw_text_centered(draw, payee_name, font_body, cur_y, W, text_color)
            cur_y += _text_height(draw, payee_name, font_body) + padding // 3

        # ── VPA ───────────────────────────────────────────────────
        if vpa:
            _draw_text_centered(draw, vpa, font_label, cur_y, W, sec_color)
            cur_y += _text_height(draw, vpa, font_label) + padding // 2

        # ── QR code ───────────────────────────────────────────────
        qr_x = (W - qr_px) // 2
        # White card behind QR
        card_pad = padding // 3
        card_radius = theme.get("border_radius", 24)
        _draw_rounded_rect(
            draw,
            (qr_x - card_pad, cur_y - card_pad, qr_x + qr_px + card_pad, cur_y + qr_px + card_pad),
            radius=card_radius,
            fill=_hex_to_rgba(theme.get("qr_light", "#FFFFFF"), 255),
        )
        bg.paste(qr_img_rgb, (qr_x, cur_y), qr_img_rgb)
        cur_y += qr_px + card_pad + padding // 2

        # ── Amount ────────────────────────────────────────────────
        if amount and amount > 0:
            amount_str = f"₹ {amount:,.2f}"
            _draw_text_centered(draw, amount_str, font_amount, cur_y, W, accent_color)
            cur_y += _text_height(draw, amount_str, font_amount) + padding // 3

        # ── Scan label ────────────────────────────────────────────
        scan_text = "Scan & Pay" if qr_type == "upi" else "Scan QR Code"
        _draw_text_centered(draw, scan_text, font_label, cur_y, W, sec_color)

    else:  # square 1080×1080
        # Left: QR | Right: text info
        qr_px_sq = int(H * qr_ratio)
        qr_img = generate_qr_image(
            payload, size_px=qr_px_sq,
            dark=theme.get("qr_dark", "#000000"),
            light=theme.get("qr_light", "#FFFFFF"),
            logo_image=logo_image,
        )
        qr_img_rgb = qr_img.convert("RGBA")
        qr_x = padding
        qr_y = (H - qr_px_sq) // 2
        card_pad = padding // 3
        _draw_rounded_rect(
            draw,
            (qr_x - card_pad, qr_y - card_pad, qr_x + qr_px_sq + card_pad, qr_y + qr_px_sq + card_pad),
            radius=theme.get("border_radius", 24),
            fill=_hex_to_rgba(theme.get("qr_light", "#FFFFFF"), 255),
        )
        bg.paste(qr_img_rgb, (qr_x, qr_y), qr_img_rgb)

        # Right side text
        text_x = qr_x + qr_px_sq + padding
        text_y = H // 3
        header_text = label or ("UPI Payment" if qr_type == "upi" else qr_type.upper())
        draw.text((text_x, text_y), header_text, font=font_title, fill=accent_color)
        text_y += _text_height(draw, header_text, font_title) + padding // 2
        if payee_name:
            draw.text((text_x, text_y), payee_name, font=font_body, fill=text_color)
            text_y += _text_height(draw, payee_name, font_body) + padding // 3
        if vpa:
            draw.text((text_x, text_y), vpa, font=font_label, fill=sec_color)
            text_y += _text_height(draw, vpa, font_label) + padding // 2
        if amount and amount > 0:
            draw.text((text_x, text_y), f"₹ {amount:,.2f}", font=font_amount, fill=accent_color)

    # ── Watermark ─────────────────────────────────────────────────────
    if watermark_enabled and watermark_text:
        wm_bbox = draw.textbbox((0, 0), watermark_text, font=font_wm)
        wm_w    = wm_bbox[2] - wm_bbox[0]
        draw.text(
            (W - wm_w - padding // 2, H - padding // 2 - wm_size),
            watermark_text,
            font=font_wm,
            fill=wm_color,
        )

    # ── Neon border / hairline / grid overlays ────────────────────────
    if theme.get("neon_border"):
        _draw_neon_border(bg, theme)
    if theme.get("border_style") == "hairline":
        _draw_hairline_border(draw, W, H, text_color, padding)
    if theme.get("grid_overlay"):
        _draw_grid_overlay(bg, theme, W, H)

    return _to_bytes(bg)


def _add_qr_watermark(img: Image.Image, text: str, theme: dict) -> Image.Image:
    draw  = ImageDraw.Draw(img)
    font  = _load_font("Inter-Regular", max(24, img.width // 60))
    color = _hex_to_rgba(theme.get("watermark_color", "#AAAAAA"))
    bbox  = draw.textbbox((0, 0), text, font=font)
    w     = bbox[2] - bbox[0]
    draw.text((img.width - w - 20, img.height - 40), text, font=font, fill=color)
    return img


def _draw_neon_border(img: Image.Image, theme: dict) -> None:
    glow = theme.get("glow_color", theme.get("accent_color", "#FF00FF"))
    color = _hex_to_rgba(glow, 180)
    d = ImageDraw.Draw(img)
    W, H = img.size
    for i in range(3):
        d.rectangle([i, i, W - 1 - i, H - 1 - i], outline=(*_hex_to_rgb(glow), 100 - i * 30), width=1)


def _draw_hairline_border(draw: ImageDraw.ImageDraw, W: int, H: int,
                          color: tuple, padding: int) -> None:
    p = padding // 2
    draw.rectangle([p, p, W - p, H - p], outline=(*color[:3], 80), width=1)


def _draw_grid_overlay(img: Image.Image, theme: dict, W: int, H: int) -> None:
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    step = W // 20
    accent = _hex_to_rgb(theme.get("accent_color", "#00FFCC"))
    for x in range(0, W, step):
        d.line([(x, 0), (x, H)], fill=(*accent, 15), width=1)
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=(*accent, 15), width=1)
    img.alpha_composite(overlay)


def _to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
