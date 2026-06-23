"""
rate_limit_middleware.py — Aiogram middleware for per-user rate limiting.
Only applied to generation commands; admin/owner are exempt.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.config import settings
from app.database import repo
from app.services.rate_limiter import check_rate_limit

# Commands that count toward rate limits
_RATE_LIMITED_COMMANDS = frozenset([
    "/generate", "/upi", "/qr",
    "/qr_url", "/qr_text", "/qr_wifi", "/qr_vcard",
    "/qr_email", "/qr_sms", "/qr_geo",
])


class RateLimitMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        user_id = user.id

        # Exempt owner and admins
        if user_id == settings.owner_id or await repo.is_admin(user_id):
            return await handler(event, data)

        # Only rate-limit generation commands
        if event.text:
            cmd = event.text.split()[0].split("@")[0].lower()
            if cmd not in _RATE_LIMITED_COMMANDS:
                return await handler(event, data)

        per_min = int(await repo.get_setting("rate_per_minute", str(settings.rate_limit_per_minute)))
        per_day = int(await repo.get_setting("rate_per_day",    str(settings.rate_limit_per_day)))

        allowed, window = await check_rate_limit(user_id, per_min, per_day)
        if not allowed:
            if window == "minute":
                msg = f"⚡ You're generating too fast! Please wait a moment.\n_Limit: {per_min} per minute._"
            else:
                msg = f"📊 Daily limit reached ({per_day} QR codes).\nLimit resets at midnight."
            await event.answer(msg, parse_mode="Markdown")
            return None

        return await handler(event, data)
