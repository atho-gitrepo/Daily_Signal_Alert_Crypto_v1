# main.py
import time
import logging
import pandas as pd
from typing import Dict
from datetime import datetime, time as dt_time

from settings import Config
from utils.indicators import Indicators
from utils.telegram_bot import send_telegram_message_sync as send_telegram_message
from binance.um_futures import UMFutures
from binance.exceptions import BinanceAPIException, BinanceRequestException
from strategy.consolidated_trend import ConsolidatedTrendStrategy


# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# -------------------- SAFE TELEGRAM WRAPPER --------------------
def safe_send_telegram_message(message: str):
    """
    Prevents Telegram failures from crashing the bot
    """
    try:
        send_telegram_message(message)
    except Exception as e:
        logger.error(f"❌ Telegram send failed: {e}")


# -------------------- BINANCE CLIENT --------------------
class BinanceDataClient:
    """Client for Binance Futures data."""

    def __init__(self):
        self.api_key = Config.BINANCE_API_KEY
        self.api_secret = Config.BINANCE_API_SECRET
        self.is_testnet = Config.BINANCE_TESTNET

        base_url = "https://testnet.binancefuture.com" if self.is_testnet else "https://fapi.binance.com"
        self.futures_client = UMFutures(
            key=self.api_key,
            secret=self.api_secret,
            base_url=base_url
        )

        self.price_precisions: Dict[str, int] = {}
        self._get_symbol_precisions()

        logger.info(f"✅ Binance Client initialized. Testnet: {self.is_testnet}")

    def _get_symbol_precisions(self):
        valid_symbols = [
            s for s in Config.SYMBOLS
            if s.endswith(Config.QUOTE_ASSET) and s != Config.QUOTE_ASSET
        ]

        if not valid_symbols:
            logger.error("❌ No valid symbols found! Check SYMBOLS config.")
            return

        try:
            info = self.futures_client.exchange_info()
            for symbol in valid_symbols:
                s_info = next((s for s in info["symbols"] if s["symbol"] == symbol), None)
                if not s_info:
                    continue

                price_filter = next(
                    (f for f in s_info["filters"] if f["filterType"] == "PRICE_FILTER"),
                    None
                )
                if price_filter:
                    tick_size = price_filter["tickSize"]
                    precision = len(tick_size.split(".")[-1].rstrip("0"))
                    self.price_precisions[symbol] = precision

        except Exception as e:
            logger.error(f"❌ Could not fetch symbol precisions: {e}")

    def _round_price(self, symbol: str, price: float) -> float:
        precision = self.price_precisions.get(symbol, 2)
        return round(price, precision)

    def get_historical_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        try:
            klines = self.futures_client.klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )

            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume", "ignore"
            ])

            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
            df.set_index("close_time", inplace=True)

            df[["open", "high", "low", "close", "volume"]] = df[
                ["open", "high", "low", "close", "volume"]
            ].apply(pd.to_numeric, errors="coerce")

            return df

        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"❌ Binance API error for {symbol}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching klines for {symbol}: {e}")
            return pd.DataFrame()

    def get_current_price(self, symbol: str) -> float | None:
        try:
            ticker = self.futures_client.ticker_price(symbol=symbol)
            return self._round_price(symbol, float(ticker["price"]))
        except Exception as e:
            logger.error(f"❌ Failed to fetch price for {symbol}: {e}")
            return None


# -------------------- SESSION DETECTION --------------------
def get_current_session() -> str:
    """Returns LONDON / NY / OTHER based on UTC time"""
    now = datetime.utcnow().time()

    london_start, london_end = dt_time(7, 0), dt_time(16, 0)
    ny_start, ny_end = dt_time(12, 0), dt_time(21, 0)

    if london_start <= now <= london_end:
        return "LONDON"
    elif ny_start <= now <= ny_end:
        return "NY"
    return "OTHER"


# -------------------- TELEGRAM MESSAGE FORMAT --------------------
def format_smart_money_message(symbol, signal_data, htf_trend, session, setup_id):
    return f"""
<b>🧠 SMART MONEY SETUP CONFIRMED</b>

<b>Pair:</b> {symbol}
<b>Direction:</b> {signal_data['signal_type']}

<b>📍 Entry:</b> {signal_data['entry_price']:.4f}
<b>🛑 Stop Loss:</b> {signal_data['stop_loss']:.4f}
<b>🎯 Take Profit:</b> {signal_data['take_profit']:.4f}

<b>HTF (1H)</b>
✔ Liquidity Sweep  
✔ Wick Rejection  
✔ EMA Trend: {htf_trend}

<b>LTF (5m / 15m)</b>
✔ MSS / CHoCH  
✔ FVG Pullback  
✔ Confirmation Close  

⚖️ R:R ≥ 1:2  
🚫 One trade per setup  

<b>💼 Session:</b> {session}
<b>🆔 Setup ID:</b> {setup_id}
"""

# -------------------- MAIN LOOP --------------------
def main():
    logger.info("🚀 Starting Binance Smart Money Client...")

    try:
        client = BinanceDataClient()
        strategy = ConsolidatedTrendStrategy()

        safe_send_telegram_message(
            f"✅ Bot started\nMonitoring: {', '.join(client.price_precisions.keys())}"
        )

        last_setups: Dict[str, str] = {}

        while True:
            session = get_current_session()

            for symbol in client.price_precisions.keys():
                try:
                    price = client.get_current_price(symbol)
                    df_5m = client.get_historical_klines(symbol, "5m", 100)
                    df_1h = client.get_historical_klines(symbol, "1h", 50)

                    if df_5m.empty or df_1h.empty or price is None:
                        continue

                    strategy.set_htf_trend(df_1h)
                    htf_trend = strategy.get_strategy_stats()["htf_trend"]

                    df_5m = strategy.analyze_data(df_5m)
                    signal_type, signal_data = strategy.generate_signal(df_5m)

                    if signal_type == "NO_TRADE":
                        continue

                    signal_data["signal_type"] = signal_type
                    setup_id = f"{symbol}_{signal_type}_{session}_{int(time.time() // 60)}"

                    if last_setups.get(symbol) == setup_id:
                        continue

                    message = format_smart_money_message(
                        symbol,
                        signal_data,
                        htf_trend,
                        session,
                        setup_id
                    )

                    safe_send_telegram_message(message)
                    last_setups[symbol] = setup_id

                except Exception as e:
                    logger.error(f"❌ Error processing {symbol}: {e}")

            time.sleep(Config.POLLING_INTERVAL_SECONDS)

    except Exception as e:
        logger.critical(f"🔥 Global critical error: {e}")


if __name__ == "__main__":
    main()