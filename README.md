# @myqrro_bot — Production-Ready Telegram QR & Poster Bot

Premium UPI QR code and poster generator for Telegram, built with **aiogram v3**,
**PostgreSQL**, **segno**, and **Pillow**. Supports 12 visual themes, logo overlays,
saved payees, ForceSub gating, admin panel, and Railway ↔ Render failover via
Cloudflare Worker.

---

## ✨ Features

| Feature | Details |
|---|---|
| **UPI QR** | Correct `upi://pay` URI, URL-encoded, validated VPA format |
| **All QR types** | URL, Text, Wi-Fi, vCard, Email, SMS, Geo |
| **12 Poster Themes** | Minimal Pro, Dark Glass, Neon Gradient, Business Invoice, Matte Black, Pastel Clean, Titanium, Cyber Grid, Festival Pack, Creator Donate, Mono Ink, Aurora |
| **Output sizes** | 1080×1350 portrait, 1080×1080 square, 2048×2048 HD QR-only |
| **Logo overlay** | Max 15% QR coverage, rounded corners, shadow, error-correction H |
| **Saved Payees** | 1-tap UPI QR generation |
| **ForceSub** | Multiple channels, public + private, ALL mode |
| **Admin Panel** | Broadcast, ban/unban, watermark, ForceSub config, audit log |
| **Owner Panel** | Add/remove admins, export, maintenance mode, purge |
| **Rate limiting** | Redis-backed (in-memory fallback), per-minute + per-day |
| **High Availability** | Railway (primary) + Render (backup) + Cloudflare Worker router |

---

## 📁 Project Structure

```
myqrro_bot/
├── main.py                      # Bot entrypoint (webhook + polling)
├── requirements.txt
├── Dockerfile
├── railway.toml
├── render.yaml
├── .env.example
│
├── app/
│   ├── config.py                # Pydantic settings loader
│   ├── logger.py                # Structured JSON logging
│   │
│   ├── database/
│   │   ├── engine.py            # Async SQLAlchemy engine + migrations runner
│   │   └── repo.py              # All DB read/write functions
│   │
│   ├── handlers/
│   │   ├── common.py            # /start, /help, /profile, home card
│   │   ├── generate.py          # UPI + QR wizards (FSM)
│   │   ├── payees.py            # Saved payees
│   │   ├── settings.py          # Settings, templates, logo, history
│   │   ├── admin.py             # Admin panel
│   │   └── owner.py             # Owner-only commands
│   │
│   ├── middleware/
│   │   ├── forcesub.py          # ForceSub gate middleware
│   │   ├── permissions.py       # @owner_only / @admin_only decorators
│   │   └── rate_limit_middleware.py
│   │
│   ├── services/
│   │   ├── qr_service.py        # QR payload builders + segno rendering
│   │   ├── poster_renderer.py   # Pillow poster engine (all 12 themes)
│   │   └── rate_limiter.py      # Redis / in-memory rate limiter
│   │
│   └── utils/
│       ├── keyboards.py         # All InlineKeyboardMarkup builders
│       └── helpers.py           # Shared utility functions
│
├── assets/
│   └── templates/
│       └── themes.json          # 12 theme configs (add themes here, no code change)
│
├── fonts/                       # Bundle TTF fonts here (see fonts/README.md)
│   └── README.md
│
├── migrations/
│   └── 001_initial_schema.sql   # Full schema with all tables
│
├── cloudflare/
│   └── worker.js                # Cloudflare Worker failover router
│
├── scripts/
│   └── download_fonts.sh        # Auto-download OFL fonts
│
└── tests/
    └── test_qr_service.py       # Unit tests for pure functions
```

---

## 🚀 Quick Start (Local Dev)

### 1. Clone & install

```bash
git clone <your-repo>
cd myqrro_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Download fonts

```bash
bash scripts/download_fonts.sh
```

### 3. Set up PostgreSQL

```bash
# Local (Docker)
docker run -d --name myqrro-pg \
  -e POSTGRES_DB=myqrro \
  -e POSTGRES_USER=myqrro \
  -e POSTGRES_PASSWORD=secret \
  -p 5432:5432 postgres:16
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — set BOT_TOKEN, OWNER_ID, DATABASE_URL at minimum
```

### 5. Run in polling mode (local)

```bash
# Leave WEBHOOK_HOST empty in .env for polling mode
python main.py
```

---

## 🚂 Deploy on Railway (Primary)

### 1. Create Railway project

```bash
railway login
railway new
railway link
```

### 2. Add PostgreSQL plugin

In Railway dashboard: **New** → **Database** → **PostgreSQL**. Copy the `DATABASE_URL`.

### 3. Set environment variables

In Railway dashboard → Variables:

```
BOT_TOKEN=<your token>
WEBHOOK_SECRET=<random 32+ char string>
OWNER_ID=<your telegram user id>
DATABASE_URL=<from Railway PostgreSQL>
WEBHOOK_HOST=https://<your-app>.railway.app
ENVIRONMENT=production
```

### 4. Deploy

```bash
railway up
```

Railway auto-detects `railway.toml` and uses `Dockerfile`.

---

## 🖥️ Deploy on Render (Backup)

### 1. Create Render Web Service

- **Environment**: Docker
- **Dockerfile path**: `./Dockerfile`
- **Health Check Path**: `/health`

### 2. Set environment variables

Same as Railway, but set `WEBHOOK_HOST` to your **Render URL** (only used if
this instance is set as the primary — leave it as your Railway URL when using
Cloudflare failover).

### 3. Deploy

Push to GitHub (connect repo in Render dashboard) or use `render.yaml`:

```bash
# render.yaml is already configured
git push origin main
```

---

## ☁️ Cloudflare Worker (Failover Router)

### Why

Telegram allows only **one webhook URL**. To run Railway + Render in
active-passive HA, a single stable URL must route to the healthiest upstream.

### Setup

1. In Cloudflare dashboard → **Workers** → **Create Worker**
2. Paste contents of `cloudflare/worker.js`
3. Set these **Environment Variables** in the Worker:

| Variable | Value |
|---|---|
| `CF_PRIMARY_URL` | `https://your-app.railway.app` |
| `CF_BACKUP_URL`  | `https://your-app.onrender.com` |
| `CF_WEBHOOK_SECRET` | Same as `WEBHOOK_SECRET` in .env |
| `CF_HEALTH_TIMEOUT` | `3000` (ms) |

4. Deploy the Worker. Note its URL: `https://myqrro.<subdomain>.workers.dev`

5. Set Telegram webhook to the Worker:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://myqrro.<subdomain>.workers.dev/webhook/<WEBHOOK_SECRET>" \
  -d "secret_token=<WEBHOOK_SECRET>" \
  -d "allowed_updates=[\"message\",\"callback_query\"]"
```

**Both Railway and Render services should NOT set their own webhooks** — the
Worker does that. Set `WEBHOOK_HOST` on each service to its own URL so the
`/webhook/<secret>` endpoint is registered, but only the Worker's URL is given
to Telegram.

### Failover Logic

```
Telegram → Cloudflare Worker
                │
     ┌──────────┴──────────┐
     │ Health check PRIMARY │  (cached 15s)
     └──────────┬──────────┘
           healthy?
          /        \
        YES         NO
         │           │
    Railway       Render
   (primary)     (backup)
```

---

## 🤖 Bot Commands Reference

### User Commands

| Command | Description |
|---|---|
| `/start` | Home card (ForceSub gate → home menu) |
| `/help` | Command reference |
| `/upi` | UPI QR wizard |
| `/qr` | QR type selector |
| `/generate` | Quick generate menu |
| `/mypayees` | Saved payees — 1-tap generate |
| `/history` | View & regenerate past QRs |
| `/templates` | Browse all 12 themes |
| `/settings` | Template, size, watermark, logo |
| `/profile` | Your stats |
| `/setlogo` | Upload a logo image |
| `/dellogo` | Remove your logo |
| `/delete_me` | Delete all your data |
| `/qr_url` | Quick URL QR |
| `/qr_text` | Quick text QR |
| `/qr_wifi` | Quick Wi-Fi QR |
| `/qr_vcard` | Quick vCard QR |
| `/qr_email` | Quick email QR |
| `/qr_sms` | Quick SMS QR |
| `/qr_geo` | Quick geo QR |

### Admin Commands

| Command | Description |
|---|---|
| `/admin` | Admin panel |
| `/ban <id> [reason]` | Ban a user |
| `/unban <id>` | Unban a user |
| `/broadcast` | Broadcast wizard |
| `/setwatermark on\|off` | Toggle global watermark |
| `/setwatermarktext <text>` | Set watermark text |
| `/setlimits <pm> <pd>` | Set rate limits |
| `/audit` | View audit log |
| `/health` | System health |
| `/forcesub_on` | Enable ForceSub |
| `/forcesub_off` | Disable ForceSub |
| `/forcesub_add @username` | Add public channel |
| `/forcesub_add <id> <link>` | Add private channel |
| `/forcesub_list` | List configured channels |
| `/forcesub_del <chat_id>` | Remove a channel |

### Owner-Only Commands

| Command | Description |
|---|---|
| `/owner` | Owner panel |
| `/addadmin <user_id>` | Grant admin |
| `/deladmin <user_id>` | Revoke admin |
| `/export users\|stats\|audit` | Export data as CSV/JSON |
| `/maintenance on\|off [msg]` | Maintenance mode |
| `/purge <user_id>` | Hard-delete all user data |

---

## 🎨 Adding New Themes

Edit `assets/templates/themes.json` — **no code changes required**:

```json
{
  "id": "my_custom_theme",
  "name": "My Custom Theme",
  "enabled": true,
  "bg_type": "gradient",
  "bg_gradient": ["#FF6B6B", "#4ECDC4"],
  "bg_gradient_angle": 135,
  "qr_dark": "#2C3E50",
  "qr_light": "#FFFFFF",
  "text_color": "#FFFFFF",
  "accent_color": "#F7DC6F",
  "secondary_text": "#BDC3C7",
  "font_title": "Poppins-SemiBold",
  "font_body": "Inter-Regular",
  "border_radius": 24,
  "padding": 60,
  "qr_size_ratio": 0.58,
  "watermark_color": "#7F8C8D",
  "sizes": ["1080x1350", "1080x1080"]
}
```

Restart the bot to pick up the new theme.

---

## 🔐 First-Run: Add a ForceSub Channel

```
/forcesub_add @yourchannel          # public channel
/forcesub_add -1001234567890 https://t.me/+xxxxx  # private channel
/forcesub_on                        # enable the gate
/forcesub_list                      # verify
```

---

## 🧪 Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## 🛡️ Security Notes

- Secrets are **only** loaded from environment variables — never hardcoded.
- Webhook secret is validated on every request.
- Owner ID is checked against `settings.owner_id` (env var), not the database.
- All admin DB writes are logged to `audit_log`.
- VPA validation is **format-only** — no claim of bank verification is made.
- Rate limiting applies to generation commands only; admin/owner are exempt.

---

## 📊 Health Endpoint

`GET /health` returns:

```json
{
  "status": "ok",
  "uptime_s": 3600.5,
  "memory_mb": 128.4,
  "db": {
    "status": "ok",
    "latency_ms": 2.3
  }
}
```

Returns HTTP 503 if DB is down (Cloudflare Worker uses this to trigger failover).

---

## 📄 License

MIT — see LICENSE file.

---

*Built with ❤️ using aiogram v3, segno, Pillow, PostgreSQL, and Cloudflare Workers.*
