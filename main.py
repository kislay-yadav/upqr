"""
main.py — Bot entrypoint.

Supports two modes:
  - Webhook (production on Railway / Render): WEBHOOK_HOST must be set.
  - Polling (local dev): runs without webhook.

FastAPI serves:
  POST /webhook/<secret>   — Telegram webhook endpoint
  GET  /health             — Health check for Cloudflare failover
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

import psutil
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.database.engine import run_migrations, check_db_health
from app.handlers import ALL_ROUTERS
from app.logger import configure_logging, get_logger
from app.middleware import ForceSub, RateLimitMiddleware

configure_logging()
log = get_logger("main")

_START_TIME = time.time()

# ── Bot + Dispatcher ──────────────────────────────────────────────────────

def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware (order matters: outer → inner)
    dp.update.outer_middleware(ForceSub())
    dp.message.middleware(RateLimitMiddleware())

    # Routers
    for router in ALL_ROUTERS:
        dp.include_router(router)

    return dp


bot = create_bot()
dp  = create_dispatcher()


# ── FastAPI app ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup_begin")
    await run_migrations()

    if settings.webhook_host:
        webhook_url = settings.webhook_url
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"],
        )
        log.info("webhook_set", url=webhook_url)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("webhook_deleted_polling_mode")

    yield

    log.info("shutdown_begin")
    await bot.session.close()


app = FastAPI(title="myqrro_bot", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.post(f"/webhook/{{secret}}")
async def webhook_handler(secret: str, request: Request) -> Response:
    if secret != settings.webhook_secret:
        log.warning("invalid_webhook_secret", received=secret[:8])
        return Response(status_code=403)

    body = await request.body()
    update = Update.model_validate_json(body)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)


@app.get("/health")
async def health() -> JSONResponse:
    db     = await check_db_health()
    proc   = psutil.Process()
    mem_mb = round(proc.memory_info().rss / 1024 ** 2, 2)
    uptime = round(time.time() - _START_TIME, 1)

    status_code = 200 if db["status"] == "ok" else 503
    return JSONResponse(
        {
            "status":    "ok" if db["status"] == "ok" else "degraded",
            "uptime_s":  uptime,
            "memory_mb": mem_mb,
            "db":        db,
        },
        status_code=status_code,
    )


# ── Polling fallback (local dev) ──────────────────────────────────────────

async def run_polling() -> None:
    configure_logging()
    await run_migrations()
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("polling_started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    if settings.webhook_host:
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            log_config=None,  # structlog handles logging
        )
    else:
        asyncio.run(run_polling())
