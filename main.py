import asyncio
import logging
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", 8000))
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")


async def main():
    from database import init_db
    from bot import build_app
    from ai_manager import build_scheduler
    from webhook_server import app as web_app, set_bot_app

    init_db()

    bot_app = build_app()
    set_bot_app(bot_app)

    scheduler = build_scheduler(bot_app.bot)

    config = uvicorn.Config(web_app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)

    async with bot_app:
        scheduler.start()
        logger.info("AI scheduler started")

        await bot_app.start()

        webhook_url = f"{BASE_URL}/webhook"
        await bot_app.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "inline_query"],
        )
        logger.info("Webhook registered: %s", webhook_url)

        await server.serve()

        scheduler.shutdown(wait=False)
        await bot_app.updater.stop() if bot_app.updater else None
        await bot_app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
