-- migrations/001_initial_schema.sql
-- Run in order; each file is idempotent via IF NOT EXISTS / OR REPLACE.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Users ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id         BIGINT PRIMARY KEY,
    username        TEXT,
    full_name       TEXT NOT NULL DEFAULT '',
    language_code   TEXT NOT NULL DEFAULT 'en',
    is_banned       BOOLEAN NOT NULL DEFAULT FALSE,
    ban_reason      TEXT,
    logo_file_id    TEXT,                           -- Telegram file_id for logo
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_generated INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_banned   ON users(is_banned) WHERE is_banned = TRUE;

-- ── User settings ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_settings (
    user_id             BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    preferred_template  TEXT NOT NULL DEFAULT 'minimal_pro',
    preferred_size      TEXT NOT NULL DEFAULT '1080x1350',   -- 1080x1350 | 1080x1080 | 2048x2048
    watermark_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    notify_updates      BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Admins ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
    user_id     BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    granted_by  BIGINT NOT NULL,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── ForceSub required chats ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forcesub_chats (
    chat_id     BIGINT PRIMARY KEY,
    username    TEXT,                               -- @handle if public
    invite_link TEXT,                               -- invite link if private
    title       TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    added_by    BIGINT NOT NULL,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Global settings (key-value) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_by  BIGINT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO bot_settings (key, value) VALUES
    ('forcesub_enabled',   'false'),
    ('watermark_enabled',  'true'),
    ('watermark_text',     '@myqrro_bot'),
    ('maintenance_mode',   'false'),
    ('maintenance_msg',    'Bot is under maintenance. Please try again later.'),
    ('rate_per_minute',    '10'),
    ('rate_per_day',       '200')
ON CONFLICT (key) DO NOTHING;

-- ── Saved payees ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS saved_payees (
    id          SERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    label       TEXT NOT NULL,
    vpa         TEXT NOT NULL,
    payee_name  TEXT NOT NULL,
    amount      NUMERIC(12,2),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, vpa, label)
);

CREATE INDEX IF NOT EXISTS idx_payees_user ON saved_payees(user_id);

-- ── Generation history ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS history (
    id              SERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    qr_type         TEXT NOT NULL,                 -- upi | url | wifi | vcard | ...
    payload         TEXT NOT NULL,
    template        TEXT NOT NULL,
    size            TEXT NOT NULL,
    file_id         TEXT,                          -- Telegram file_id of sent image
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_history_user_created ON history(user_id, created_at DESC);

-- ── Audit log ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor_id    BIGINT NOT NULL,
    action      TEXT NOT NULL,
    target_id   BIGINT,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_actor   ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

INSERT INTO schema_migrations (version) VALUES (1) ON CONFLICT DO NOTHING;
