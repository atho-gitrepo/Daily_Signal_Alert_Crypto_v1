import time
import logging
import pandas as pd
from typing import Dict
from datetime import datetime, time as dt_time

from settings import Config
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
    """Prevent Telegram failure from crashing bot"""
    try:
        send_telegram_message(message)
    except Exception as e:
        logger.error(f"❌ Telegram send failed: {e}")


# -------------------- BINANCE CLIENT --------------------
class BinanceDataClient:
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

        logger.info(f"✅ Binance Client initialized | Testnet={self.is_testnet}")

    def _get_symbol_precisions(self):
        try:
            info = self.futures_client.exchange_info()
            for symbol in Config.SYMBOLS:
                s_info = next((s for s in info["symbols"] if s["symbol"] == symbol), None)
                if not s_info:
                    continue

                price_filter = next(
                    (f for f in s_info["filters"] if f["filterType"] == "PRICE_FILTER"), None
                )
                if price_filter:
                    tick = price_filter["tickSize"]
                    self.price_precisions[symbol] = len(tick.split(".")[-1].rstrip("0"))
        except Exception as e:
            logger.error(f"❌ Failed to load symbol precision: {e}")

    def get_historical_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        try:
            klines = self.futures_client.klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=[
                "open_time","open","high","low","close","volume",
                "close_time","qav","trades","tb_base","tb_quote","ignore"
            ])

            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
            df.set_index("close_time", inplace=True)
            df[["open","high","low","close","volume"]] = df[
                ["open","high","low","close","volume"]
            ].astype(float)
            return df
        except Exception as e:
            logger.error(f"❌ Klines error {symbol}: {e}")
            return pd.DataFrame()


# -------------------- SESSION DETECTION --------------------
def get_current_session() -> str:
    now = datetime.utcnow().time()
    if dt_time(7, 0) <= now <= dt_time(16, 0):
        return "LONDON"
    if dt_time(12, 0) <= now <= dt_time(21, 0):
        return "NY"
    return "OTHER"


# -------------------- TELEGRAM FORMAT --------------------
def format_smart_money_message(symbol, signal_data, htf_trend, session, setup_id):
    tdi = float(signal_data.get("tdi_slow_ma", 0))
    slope = float(signal_data.get("tdi_slope", 0))
    atr = float(signal_data.get("atr", 0))
    strength = signal_data.get("signal_strength", "SOFT")

    strength_emoji = "🟢" if strength == "HARD" else "🟡"
    slope_text = "↗ Strong" if slope > 1 else "→ Weak" if slope > 0 else "↘ Weak"

    return (
        f"<b>🧠 SMART MONEY SETUP CONFIRMED {strength_emoji}</b>\n\n"
        f"<b>Pair:</b> {symbol}\n"
        f"<b>Direction:</b> {signal_data['signal_type']}\n\n"

        f"<b>📍 Entry:</b> {signal_data['entry_price']:.4f}\n"
        f"<b>🛑 Stop Loss:</b> {signal_data['stop_loss']:.4f}\n"
        f"<b>🎯 Take Profit:</b> {signal_data['take_profit']:.4f}\n\n"

        f"<b>HTF (1H)</b>\n"
        f"✔ Liquidity Sweep\n"
        f"✔ Wick Rejection\n"
        f"✔ EMA Trend: {htf_trend}\n\n"

        f"<b>LTF (5m / 15m)</b>\n"
        f"✔ MSS / CHoCH\n"
        f"✔ FVG Pullback\n"
        f"✔ Confirmation Close\n\n"

        f"<b>📊 TDI Analysis</b>\n"
        f"• Slow MA: {tdi:.2f}\n"
        f"• Slope: {slope_text}\n"
        f"• Strength: {strength}\n\n"

        f"<b>📐 ATR:</b> {atr:.4f}\n\n"

        f"⚖️ R:R ≥ 1:2\n"
        f"🚫 One trade per setup\n\n"

        f"<b>💼 Session:</b> {session}\n"
        f"<b>🆔 Setup ID:</b> {setup_id}"
    )


# -------------------- MAIN LOOP --------------------
def main():
    logger.info("🚀 Smart Money Bot Started")

    client = BinanceDataClient()
    strategy = ConsolidatedTrendStrategy()
    last_setups: Dict[str, str] = {}

    safe_send_telegram_message(
        f"✅ Bot online\nSymbols: {', '.join(client.price_precisions.keys())}"
    )

    while True:
        session = get_current_session()

        for symbol in client.price_precisions.keys():
            try:
                df_5m = client.get_historical_klines(symbol, "5m", 120)
                df_1h = client.get_historical_klines(symbol, "1h", 60)

                if df_5m.empty or df_1h.empty:
                    continue

                strategy.set_htf_trend(df_1h)
                htf_trend = strategy.get_strategy_stats().get("htf_trend", "UNKNOWN")

                df_5m = strategy.analyze_data(df_5m)
                signal_type, signal_data = strategy.generate_signal(df_5m)

                if signal_type == "NO_TRADE":
                    continue

                signal_data["signal_type"] = signal_type
                setup_id = f"{symbol}_{signal_type}_{session}_{int(time.time() // 60)}"

                if last_setups.get(symbol) == setup_id:
                    continue

                msg = format_smart_money_message(
                    symbol, signal_data, htf_trend, session, setup_id
                )
                safe_send_telegram_message(msg)
                last_setups[symbol] = setup_id

            except Exception as e:
                logger.error(f"❌ {symbol} processing error: {e}")

        time.sleep(Config.POLLING_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()