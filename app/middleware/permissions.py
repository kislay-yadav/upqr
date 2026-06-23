"""
permissions.py — Permission check decorators for owner-only and admin-only handlers.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database import repo


def owner_only(handler: Callable) -> Callable:
    """Restrict handler to bot owner only."""
    @functools.wraps(handler)
    async def wrapper(event: Any, *args: Any, **kwargs: Any) -> Any:
        user_id = _get_user_id(event)
        if user_id != settings.owner_id:
            await _deny(event, "⛔ This command is for the bot owner only.")
            return
        return await handler(event, *args, **kwargs)
    return wrapper


def admin_only(handler: Callable) -> Callable:
    """Restrict handler to admins (and owner)."""
    @functools.wraps(handler)
    async def wrapper(event: Any, *args: Any, **kwargs: Any) -> Any:
        user_id = _get_user_id(event)
        if user_id == settings.owner_id:
            return await handler(event, *args, **kwargs)
        if not await repo.is_admin(user_id):
            await _deny(event, "⛔ This command requires admin privileges.")
            return
        return await handler(event, *args, **kwargs)
    return wrapper


def _get_user_id(event: Any) -> int:
    if isinstance(event, Message):
        return event.from_user.id
    if isinstance(event, CallbackQuery):
        return event.from_user.id
    return 0


async def _deny(event: Any, text: str) -> None:
    if isinstance(event, Message):
        await event.answer(text)
    elif isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
