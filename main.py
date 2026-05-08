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


async def main():
    from database import init_db
    from bot import build_app
    from ai_manager import build_scheduler
    from webhook_server import app as web_app

    init_db()

    bot_app = build_app()
    scheduler = build_scheduler(bot_app.bot)

    config = uvicorn.Config(web_app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)

    async with bot_app:
        scheduler.start()
        logger.info("AI scheduler started")

        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot started on port %d", PORT)

        await server.serve()

        scheduler.shutdown(wait=False)
        await bot_app.updater.stop()
        await bot_app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
