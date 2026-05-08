import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    from database import init_db
    from bot import build_app
    from ai_manager import build_scheduler

    init_db()

    app = build_app()
    scheduler = build_scheduler(app.bot)

    async with app:
        scheduler.start()
        logger.info("AI scheduler started (sync every 1h, analyze every 6h)")

        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot started. Press Ctrl+C to stop.")

        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("Shutting down...")
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped.")
