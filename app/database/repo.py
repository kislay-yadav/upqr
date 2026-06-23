"""
repo.py — Repository layer: all DB reads/writes in one place.
Uses raw asyncpg for performance-critical paths.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)

# ── Connection helper ─────────────────────────────────────────────────────

async def _conn() -> asyncpg.Connection:
    raw_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return await asyncpg.connect(raw_url)


# ── Users ─────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: Optional[str], full_name: str, language_code: str = "en") -> None:
    conn = await _conn()
    try:
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name, language_code, last_seen_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (user_id) DO UPDATE
              SET username = EXCLUDED.username,
                  full_name = EXCLUDED.full_name,
                  last_seen_at = now()
        """, user_id, username, full_name, language_code)
        # Ensure settings row exists
        await conn.execute("""
            INSERT INTO user_settings (user_id) VALUES ($1) ON CONFLICT DO NOTHING
        """, user_id)
    finally:
        await conn.close()


async def get_user(user_id: int) -> Optional[dict]:
    conn = await _conn()
    try:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None
    finally:
        await conn.close()


async def is_banned(user_id: int) -> bool:
    conn = await _conn()
    try:
        val = await conn.fetchval("SELECT is_banned FROM users WHERE user_id = $1", user_id)
        return bool(val)
    finally:
        await conn.close()


async def ban_user(user_id: int, reason: str, actor_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("""
            UPDATE users SET is_banned = TRUE, ban_reason = $2 WHERE user_id = $1
        """, user_id, reason)
        await _audit(conn, actor_id, "ban_user", user_id, {"reason": reason})
    finally:
        await conn.close()


async def unban_user(user_id: int, actor_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("UPDATE users SET is_banned = FALSE, ban_reason = NULL WHERE user_id = $1", user_id)
        await _audit(conn, actor_id, "unban_user", user_id, {})
    finally:
        await conn.close()


async def purge_user(user_id: int, actor_id: int) -> None:
    """Hard-delete all user data (GDPR / /delete_me / owner /purge)."""
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)
        await _audit(conn, actor_id, "purge_user", user_id, {})
    finally:
        await conn.close()


async def get_all_users(limit: int = 10000, offset: int = 0) -> list[dict]:
    conn = await _conn()
    try:
        rows = await conn.fetch("SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2", limit, offset)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def increment_generated(user_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("UPDATE users SET total_generated = total_generated + 1 WHERE user_id = $1", user_id)
    finally:
        await conn.close()


# ── User settings ─────────────────────────────────────────────────────────

async def get_user_settings(user_id: int) -> dict:
    conn = await _conn()
    try:
        row = await conn.fetchrow("SELECT * FROM user_settings WHERE user_id = $1", user_id)
        if row:
            return dict(row)
        return {"user_id": user_id, "preferred_template": "minimal_pro",
                "preferred_size": "1080x1350", "watermark_enabled": True}
    finally:
        await conn.close()


async def update_user_settings(user_id: int, **kwargs: Any) -> None:
    if not kwargs:
        return
    conn = await _conn()
    try:
        sets = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
        vals = list(kwargs.values())
        await conn.execute(
            f"UPDATE user_settings SET {sets}, updated_at = now() WHERE user_id = $1",
            user_id, *vals
        )
    finally:
        await conn.close()


async def set_user_logo(user_id: int, file_id: Optional[str]) -> None:
    conn = await _conn()
    try:
        await conn.execute("UPDATE users SET logo_file_id = $2 WHERE user_id = $1", user_id, file_id)
    finally:
        await conn.close()


# ── Admins ────────────────────────────────────────────────────────────────

async def add_admin(user_id: int, granted_by: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("""
            INSERT INTO admins (user_id, granted_by) VALUES ($1, $2)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, granted_by)
        await _audit(conn, granted_by, "add_admin", user_id, {})
    finally:
        await conn.close()


async def remove_admin(user_id: int, actor_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM admins WHERE user_id = $1", user_id)
        await _audit(conn, actor_id, "remove_admin", user_id, {})
    finally:
        await conn.close()


async def is_admin(user_id: int) -> bool:
    conn = await _conn()
    try:
        row = await conn.fetchval("SELECT 1 FROM admins WHERE user_id = $1", user_id)
        return row is not None
    finally:
        await conn.close()


async def get_all_admins() -> list[dict]:
    conn = await _conn()
    try:
        rows = await conn.fetch("SELECT a.*, u.username, u.full_name FROM admins a JOIN users u USING (user_id)")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── Bot settings (global KV) ──────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    conn = await _conn()
    try:
        val = await conn.fetchval("SELECT value FROM bot_settings WHERE key = $1", key)
        return val if val is not None else default
    finally:
        await conn.close()


async def set_setting(key: str, value: str, actor_id: Optional[int] = None) -> None:
    conn = await _conn()
    try:
        await conn.execute("""
            INSERT INTO bot_settings (key, value, updated_by, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (key) DO UPDATE
              SET value = EXCLUDED.value,
                  updated_by = EXCLUDED.updated_by,
                  updated_at = now()
        """, key, value, actor_id)
    finally:
        await conn.close()


# ── ForceSub chats ────────────────────────────────────────────────────────

async def add_forcesub_chat(chat_id: int, username: Optional[str], invite_link: Optional[str],
                            title: str, added_by: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("""
            INSERT INTO forcesub_chats (chat_id, username, invite_link, title, added_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (chat_id) DO UPDATE
              SET username = EXCLUDED.username,
                  invite_link = EXCLUDED.invite_link,
                  title = EXCLUDED.title,
                  is_active = TRUE
        """, chat_id, username, invite_link, title, added_by)
        await _audit(conn, added_by, "forcesub_add", chat_id, {"title": title})
    finally:
        await conn.close()


async def remove_forcesub_chat(chat_id: int, actor_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM forcesub_chats WHERE chat_id = $1", chat_id)
        await _audit(conn, actor_id, "forcesub_del", chat_id, {})
    finally:
        await conn.close()


async def get_forcesub_chats() -> list[dict]:
    conn = await _conn()
    try:
        rows = await conn.fetch("SELECT * FROM forcesub_chats WHERE is_active = TRUE ORDER BY added_at")
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── Saved payees ──────────────────────────────────────────────────────────

async def add_payee(user_id: int, label: str, vpa: str, payee_name: str,
                    amount: Optional[float], note: Optional[str]) -> int:
    conn = await _conn()
    try:
        row = await conn.fetchrow("""
            INSERT INTO saved_payees (user_id, label, vpa, payee_name, amount, note)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, vpa, label) DO UPDATE
              SET payee_name = EXCLUDED.payee_name,
                  amount = EXCLUDED.amount,
                  note = EXCLUDED.note
            RETURNING id
        """, user_id, label, vpa, payee_name, amount, note)
        return row["id"]
    finally:
        await conn.close()


async def get_payees(user_id: int) -> list[dict]:
    conn = await _conn()
    try:
        rows = await conn.fetch("SELECT * FROM saved_payees WHERE user_id = $1 ORDER BY created_at DESC", user_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_payee(payee_id: int, user_id: int) -> Optional[dict]:
    conn = await _conn()
    try:
        row = await conn.fetchrow("SELECT * FROM saved_payees WHERE id = $1 AND user_id = $2", payee_id, user_id)
        return dict(row) if row else None
    finally:
        await conn.close()


async def delete_payee(payee_id: int, user_id: int) -> None:
    conn = await _conn()
    try:
        await conn.execute("DELETE FROM saved_payees WHERE id = $1 AND user_id = $2", payee_id, user_id)
    finally:
        await conn.close()


# ── History ───────────────────────────────────────────────────────────────

async def add_history(user_id: int, qr_type: str, payload: str, template: str,
                      size: str, file_id: Optional[str]) -> int:
    conn = await _conn()
    try:
        row = await conn.fetchrow("""
            INSERT INTO history (user_id, qr_type, payload, template, size, file_id)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
        """, user_id, qr_type, payload, template, size, file_id)
        # Prune old records beyond limit
        await conn.execute("""
            DELETE FROM history WHERE user_id = $1
            AND id NOT IN (
                SELECT id FROM history WHERE user_id = $1
                ORDER BY created_at DESC LIMIT $2
            )
        """, user_id, settings.max_history_per_user)
        return row["id"]
    finally:
        await conn.close()


async def get_history(user_id: int, limit: int = 10) -> list[dict]:
    conn = await _conn()
    try:
        rows = await conn.fetch("""
            SELECT * FROM history WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2
        """, user_id, limit)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def update_history_file_id(history_id: int, file_id: str) -> None:
    conn = await _conn()
    try:
        await conn.execute("UPDATE history SET file_id = $2 WHERE id = $1", history_id, file_id)
    finally:
        await conn.close()


# ── Audit ─────────────────────────────────────────────────────────────────

async def _audit(conn: asyncpg.Connection, actor_id: int, action: str,
                 target_id: Optional[int], details: dict) -> None:
    await conn.execute("""
        INSERT INTO audit_log (actor_id, action, target_id, details)
        VALUES ($1, $2, $3, $4)
    """, actor_id, action, target_id, json.dumps(details))


async def get_audit_log(limit: int = 50, offset: int = 0) -> list[dict]:
    conn = await _conn()
    try:
        rows = await conn.fetch("""
            SELECT al.*, u.username, u.full_name
            FROM audit_log al LEFT JOIN users u ON al.actor_id = u.user_id
            ORDER BY al.created_at DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── Stats ─────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    conn = await _conn()
    try:
        total_users  = await conn.fetchval("SELECT COUNT(*) FROM users")
        banned_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned")
        total_gen    = await conn.fetchval("SELECT COALESCE(SUM(total_generated), 0) FROM users")
        today_gen    = await conn.fetchval(
            "SELECT COUNT(*) FROM history WHERE created_at > now() - interval '1 day'"
        )
        return {
            "total_users": total_users,
            "banned_users": banned_users,
            "total_generated": total_gen,
            "today_generated": today_gen,
        }
    finally:
        await conn.close()
