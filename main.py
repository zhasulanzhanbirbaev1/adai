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

    await bot_app.initialize()
    await bot_app.start()
    scheduler.start()
    logger.info("Bot and scheduler started")

    if BASE_URL:
        try:
            await bot_app.bot.set_webhook(
                f"{BASE_URL}/webhook",
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "inline_query"],
            )
            logger.info("Webhook registered: %s/webhook", BASE_URL)
        except Exception as e:
            logger.error("Webhook registration failed: %s", e)

    config = uvicorn.Config(web_app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)
        try:
            await bot_app.bot.delete_webhook()
        except Exception:
            pass
        await bot_app.stop()
        await bot_app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
