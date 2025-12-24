# utils/telegram_bot.py
import asyncio
import logging
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from settings import Config  # ✅ must come AFTER standard libs to avoid circular import

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Telegram Bot
_bot: Bot | None = None
if getattr(Config, "TELEGRAM_BOT_TOKEN", None) and getattr(Config, "TELEGRAM_CHAT_ID", None):
    try:
        _bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        logger.info("✅ Telegram bot initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram bot: {e}")
        _bot = None
else:
    logger.warning("⚠️ Telegram bot token or chat ID missing. Notifications disabled.")


# =============== ASYNC SENDER ===============
async def send_telegram_message_async(message: str):
    """Send Telegram message asynchronously."""
    if not _bot:
        logger.warning("⚠️ Telegram bot not initialized. Message skipped.")
        return

    try:
        await _bot.send_message(
            chat_id=Config.TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info("📩 Telegram message sent successfully.")
    except TelegramError as e:
        logger.error(f"⚠️ Telegram API error: {e}. Message: {message}")
    except Exception as e:
        logger.error(f"❌ Unexpected error sending Telegram message: {e}")


# =============== SYNC WRAPPER ===============
def send_telegram_message_sync(message: str):
    """Send Telegram message synchronously (from non-async context)."""
    if not _bot:
        logger.warning("⚠️ Telegram bot not initialized. Message skipped.")
        return

    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # For environments like FastAPI or Jupyter notebooks
            loop.create_task(send_telegram_message_async(message))
        else:
            loop.run_until_complete(send_telegram_message_async(message))

    except Exception as e:
        logger.error(f"❌ Failed to send Telegram message synchronously: {e}")