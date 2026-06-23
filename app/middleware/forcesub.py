"""
forcesub.py — Middleware that gates all updates behind ForceSub verification.
Checks that the user is a member of ALL configured required chats.
Lets admin/owner commands through unconditionally.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.database import repo
from app.config import settings
from app.logger import get_logger
from app.utils.keyboards import build_forcesub_keyboard

log = get_logger(__name__)

_ADMIN_COMMANDS = frozenset([
    "/admin", "/ban", "/unban", "/broadcast", "/setwatermark",
    "/setwatermarktext", "/setlimits", "/audit", "/health",
    "/forcesub_on", "/forcesub_off", "/forcesub_add",
    "/forcesub_list", "/forcesub_del",
    "/owner", "/addadmin", "/deladmin", "/export",
    "/maintenance", "/purge",
])


class ForceSub(BaseMiddleware):
    """
    Applied to all incoming updates.
    If ForceSub is enabled and user has not joined all required chats,
    sends a "please join" message and stops propagation.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract user from update
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        user_id = user.id

        # Always allow owner through
        if user_id == settings.owner_id:
            return await handler(event, data)

        # Allow admins through
        if await repo.is_admin(user_id):
            return await handler(event, data)

        # Check if command is admin-only (let it through to get proper permission error)
        if isinstance(event, (Message, Update)):
            msg = event if isinstance(event, Message) else getattr(event, "message", None)
            if msg and msg.text:
                cmd = msg.text.split()[0].split("@")[0].lower()
                if cmd in _ADMIN_COMMANDS:
                    return await handler(event, data)

        # Check ForceSub enabled
        fs_enabled = await repo.get_setting("forcesub_enabled", "false")
        if fs_enabled.lower() != "true":
            return await handler(event, data)

        # Verify membership
        bot: Bot = data["bot"]
        chats = await repo.get_forcesub_chats()
        if not chats:
            return await handler(event, data)

        not_joined = []
        for chat in chats:
            joined = await _check_membership(bot, user_id, chat["chat_id"])
            if not joined:
                not_joined.append(chat)

        if not not_joined:
            return await handler(event, data)

        # Build response message
        keyboard = build_forcesub_keyboard(not_joined)
        text = (
            "🔐 <b>Access Required</b>\n\n"
            "To use this bot, you must join the following channel(s):\n\n"
            + "\n".join(
                f"• <b>{c.get('title', 'Channel')}</b>"
                for c in not_joined
            )
            + "\n\n<i>Tap the buttons below to join, then press ✅ Verify.</i>"
        )

        # Respond depending on event type
        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("Please join all required channels first.", show_alert=True)

        return None  # Stop propagation


async def _check_membership(bot: Bot, user_id: int, chat_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("member", "administrator", "creator", "restricted")
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.warning("forcesub_check_failed", chat_id=chat_id, user_id=user_id, error=str(exc))
        return True  # Fail open if bot can't check (avoids locking out users)
    except Exception as exc:
        log.error("forcesub_check_error", error=str(exc))
        return True
