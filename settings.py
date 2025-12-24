# settings.py
import os
from typing import List

# ------------------- Helper Functions -------------------
def safe_float_env(key: str, default: float) -> float:
    """Safely gets an environment variable as a float."""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default

def safe_int_env(key: str, default: int) -> int:
    """Safely gets an environment variable as an integer."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

# ------------------- Config Class -------------------
class Config:
    """
    Configuration settings for Binance data client, strategy, and Telegram alerts.
    """

    # ------------------- Binance API -------------------
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "False").lower() in ("true", "1", "t")
    RUN_MODE: str = os.getenv("RUN_MODE", "PRODUCTION").upper()

    # ------------------- Market Data -------------------
    QUOTE_ASSET: str = os.getenv("QUOTE_ASSET", "USDT")
    MAX_SYMBOLS: int = safe_int_env("MAX_SYMBOLS", 30)

    SYMBOLS: List[str] = os.getenv(
        "SYMBOLS",
        (
            "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,"
            "DOTUSDT,TRXUSDT,BCHUSDT,LTCUSDT,UNIUSDT,NEARUSDT,"
            "ETCUSDT,XLMUSDT,APTUSDT,SUIUSDT,IMXUSDT,"
            "FILUSDT,ATOMUSDT,VETUSDT"
        )
    ).upper().split(',')

    TIMEFRAME: str = os.getenv("TIMEFRAME", "5m")

    # ------------------- Polling / API -------------------
    POLLING_INTERVAL_SECONDS: int = safe_int_env("POLLING_INTERVAL_SECONDS", 5)
    API_TIMEOUT_SECONDS: int = safe_int_env("API_TIMEOUT_SECONDS", 5)

    # ------------------- Strategy Parameters -------------------
    TDI_RSI_PERIOD: int = 14
    TDI_BB_LENGTH: int = 20
    TDI_FAST_MA_PERIOD: int = 1
    TDI_SLOW_MA_PERIOD: int = 7

    BB_PERIOD: int = 20
    BB_DEV: float = 2.0
    BB_TREND_PERIOD: int = 9

    TDI_CENTER_LINE: float = 50.0
    TDI_SOFT_BUY_LEVEL: float = 35.0
    TDI_HARD_BUY_LEVEL: float = 25.0
    TDI_SOFT_SELL_LEVEL: float = 65.0
    TDI_HARD_SELL_LEVEL: float = 75.0

    # ------------------- Risk Management -------------------
    MAX_TOTAL_RISK_CAPITAL_PERCENT: float = safe_float_env("MAX_TOTAL_RISK_CAPITAL_PERCENT", 10.0)
    RISK_PER_TRADE_PERCENT: float = safe_float_env("RISK_PER_TRADE_PERCENT", 0.5)

    # ------------------- Telegram Bot -------------------
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ------------------- Session Detection -------------------
    # Times in UTC (24h format)
    LONDON_SESSION_START: int = 7   # 7:00 UTC
    LONDON_SESSION_END: int = 16    # 16:00 UTC
    NY_SESSION_START: int = 12      # 12:00 UTC
    NY_SESSION_END: int = 21        # 21:00 UTC

    # ------------------- Setup ID / Duplicate Prevention -------------------
    ALERT_DUPLICATE_COOLDOWN_MINUTES: int = 10  # Prevent duplicate alert for same setup