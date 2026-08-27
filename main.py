import asyncio
import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", 8000))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

_bot_app_global = None
_scheduler_global = None


@asynccontextmanager
async def lifespan(app):
    global _bot_app_global, _scheduler_global

    from database import init_db
    from bot import build_app
    from ai_manager import build_scheduler
    from webhook_server import set_bot_app

    init_db()
    logger.info("DB initialized")

    try:
        bot_app = build_app()
        set_bot_app(bot_app)
        _bot_app_global = bot_app

        await bot_app.initialize()
        await bot_app.start()
        logger.info("Bot started")

        scheduler = build_scheduler(bot_app.bot)
        scheduler.start()
        _scheduler_global = scheduler
        logger.info("Scheduler started")

        if BASE_URL:
            await bot_app.bot.set_webhook(
                f"{BASE_URL}/webhook",
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "inline_query"],
            )
            logger.info("Webhook: %s/webhook", BASE_URL)

    except Exception as e:
        logger.error("Bot startup error: %s", e, exc_info=True)

    yield  # server runs here

    logger.info("Shutting down...")
    if _scheduler_global:
        try:
            _scheduler_global.shutdown(wait=False)
        except Exception:
            pass
    if _bot_app_global:
        try:
            await _bot_app_global.bot.delete_webhook()
            await _bot_app_global.stop()
            await _bot_app_global.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    from webhook_server import app
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
