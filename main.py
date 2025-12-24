# main.py
import time
import logging
import pandas as pd
from typing import Dict, Any
from datetime import datetime, time as dt_time
from settings import Config
from utils.indicators import Indicators
from utils.telegram_bot import send_telegram_message_sync as send_telegram_message
from binance.um_futures import UMFutures
from binance.exceptions import BinanceAPIException, BinanceRequestException

from strategy.consolidated_trend import ConsolidatedTrendStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# -------------------- BINANCE CLIENT --------------------
class BinanceDataClient:
    """Client for Binance Futures data."""

    def __init__(self):
        self.api_key = Config.BINANCE_API_KEY
        self.api_secret = Config.BINANCE_API_SECRET
        self.is_testnet = Config.BINANCE_TESTNET

        base_url = "https://testnet.binancefuture.com" if self.is_testnet else "https://fapi.binance.com"
        self.futures_client = UMFutures(key=self.api_key, secret=self.api_secret, base_url=base_url)
        self.price_precisions: Dict[str, int] = {}
        self._get_symbol_precisions()
        logger.info(f"✅ Binance Client initialized. Testnet: {self.is_testnet}")

    def _get_symbol_precisions(self):
        valid_symbols = [s for s in Config.SYMBOLS if s.endswith(Config.QUOTE_ASSET) and s != Config.QUOTE_ASSET]
        if not valid_symbols:
            logger.error("❌ No valid symbols found! Check SYMBOLS config.")
            return
        try:
            info = self.futures_client.exchange_info()
            for symbol in valid_symbols:
                s_info = next((s for s in info['symbols'] if s['symbol'] == symbol), None)
                if s_info:
                    price_filter = next((f for f in s_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
                    if price_filter:
                        step_size = price_filter['tickSize']
                        precision = len(step_size.split('.')[-1].rstrip('0'))
                        self.price_precisions[symbol] = precision
        except Exception as e:
            logger.error(f"❌ Could not fetch symbol precisions: {e}")

    def _round_price(self, symbol: str, price: float) -> float:
        precision = self.price_precisions.get(symbol, 2)
        return round(price, precision) if price else 0.0

    def get_historical_klines(self, symbol: str, interval: str = None, limit: int = 500) -> pd.DataFrame:
        interval = interval or Config.TIMEFRAME
        try:
            klines = self.futures_client.klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            df.set_index('close_time', inplace=True)
            df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].apply(pd.to_numeric, errors='coerce')
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
            return self._round_price(symbol, float(ticker['price']))
        except Exception as e:
            logger.error(f"❌ Failed to fetch price for {symbol}: {e}")
            return None


# -------------------- SESSION DETECTION --------------------
def get_current_session() -> str:
    """Returns 'LONDON', 'NY', or 'OTHER' based on UTC time."""
    now = datetime.utcnow().time()
    london_start, london_end = dt_time(7, 0), dt_time(16, 0)
    ny_start, ny_end = dt_time(12, 0), dt_time(21, 0)
    if london_start <= now <= london_end:
        return "LONDON"
    elif ny_start <= now <= ny_end:
        return "NY"
    else:
        return "OTHER"


# -------------------- TELEGRAM MESSAGE --------------------
def format_smart_money_message(symbol: str, signal_data: dict, htf_trend: str, session: str, setup_id: str) -> str:
    entry = signal_data.get('entry_price', 0)
    sl = signal_data.get('stop_loss', 0)
    tp = signal_data.get('take_profit', 0)
    direction = signal_data.get('signal_type', 'BUY').upper()

    return (
        f"🧠 SMART MONEY SETUP CONFIRMED\n\n"
        f"Pair: {symbol}\n"
        f"Direction: {direction}\n\n"
        f"📍 Entry: {entry:.4f}\n"
        f"🛑 Stop Loss: {sl:.4f}\n"
        f"🎯 Take Profit: {tp:.4f}\n\n"
        f"HTF (1H):\n"
        f"✔ Liquidity Sweep\n"
        f"✔ Wick Rejection\n"
        f"✔ EMA Trend: {htf_trend}\n\n"
        f"LTF (5m/15m):\n"
        f"✔ MSS / CHoCH\n"
        f"✔ FVG Pullback\n"
        f"✔ Confirmation Close\n\n"
        f"⚖️ R:R ≥ 1:2\n"
        f"🚫 One trade per setup\n"
        f"💼 Session: {session}\n"
        f"🆔 Setup ID: {setup_id}"
    )


# -------------------- MAIN --------------------
def main():
    logger.info("🚀 Starting Binance Smart Money Client...")

    try:
        client = BinanceDataClient()
        strategy = ConsolidatedTrendStrategy()
        safe_send_telegram_message(f"✅ Client & Strategy started. Monitoring: {', '.join(client.price_precisions.keys())}")

        # Track last setup per symbol/session to prevent duplicate alerts
        last_setups: Dict[str, str] = {}

        while True:
            session = get_current_session()
            for symbol in client.price_precisions.keys():
                try:
                    price = client.get_current_price(symbol)
                    df_5m = client.get_historical_klines(symbol, interval="5m", limit=100)
                    df_1h = client.get_historical_klines(symbol, interval="1h", limit=50)

                    if df_5m.empty or df_1h.empty or price is None:
                        continue

                    # HTF Trend
                    strategy.set_htf_trend(df_1h)
                    htf_trend = strategy.get_strategy_stats()['htf_trend']

                    # Analyze 5m data
                    df_5m_analyzed = strategy.analyze_data(df_5m)

                    # Generate signal
                    signal_type, signal_data = strategy.generate_signal(df_5m_analyzed)
                    signal_data['signal_type'] = signal_type
                    setup_id = f"{symbol}_{signal_type}_{session}_{int(time.time()//60)}"

                    # Prevent duplicate alerts
                    if last_setups.get(symbol) == setup_id:
                        continue
                    if signal_type != "NO_TRADE":
                        message = format_smart_money_message(symbol, signal_data, htf_trend, session, setup_id)
                        send_telegram_message(message)
                        last_setups[symbol] = setup_id

                except Exception as e:
                    logger.error(f"❌ Error processing {symbol}: {e}")
                    continue

            time.sleep(Config.POLLING_INTERVAL_SECONDS)

    except Exception as e:
        logger.critical(f"🔥 Global critical error: {e}")


if __name__ == "__main__":
    main()