# utils/telegram_bot.py
import asyncio
import logging
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from settings import Config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_bot = None
if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID:
    try:
        _bot = Bot(token=Config.TELEGRAM_BOT_TOKEN)
        logger.info("✅ Telegram bot initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Telegram bot: {e}")
        _bot = None
else:
    logger.warning("⚠️ Telegram bot token or chat ID missing.")


async def send_telegram_message_async(message: str):
    if not _bot:
        return
    try:
        await _bot.send_message(
            chat_id=Config.TELEGRAM_CHAT_ID,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except TelegramError as e:
        logger.error(f"⚠️ Telegram API error: {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected Telegram error: {e}")


def send_telegram_message_sync(message: str):
    if not _bot:
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(send_telegram_message_async(message))
        else:
            loop.run_until_complete(send_telegram_message_async(message))
    except RuntimeError:
        asyncio.run(send_telegram_message_async(message))