import logging
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

PORT = int(os.getenv("PORT", 8000))

if __name__ == "__main__":
    from webhook_server import app
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
