import pandas as pd
import numpy as np
import logging
from settings import Config

logger = logging.getLogger(__name__)


class Indicators:

    # ==================================================
    # CORE INDICATORS
    # ==================================================
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = Config.TDI_RSI_PERIOD) -> pd.DataFrame:
        try:
            if len(df) < period:
                df["rsi"] = np.nan
                return df

            close = df["close"].ffill().replace(0, np.finfo(float).eps)
            delta = close.diff()

            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)

            avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
            avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

            rs = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
            df["rsi"] = 100 - (100 / (1 + rs))
            return df

        except Exception as e:
            logger.error(f"❌ RSI error: {e}")
            df["rsi"] = np.nan
            return df

    @staticmethod
    def calculate_sma(df: pd.DataFrame, column: str, period: int):
        col = f"{column}_sma_{period}"
        df[col] = df[column].rolling(period).mean()
        return df, col

    @staticmethod
    def calculate_ema(df: pd.DataFrame, column: str, period: int):
        col = f"{column}_ema_{period}"
        df[col] = df[column].ewm(span=period, adjust=False).mean()
        return df


    # ==================================================
    # TDI
    # ==================================================
    @staticmethod
    def calculate_super_tdi(df: pd.DataFrame) -> pd.DataFrame:
        df = Indicators.calculate_rsi(df)

        df, fast = Indicators.calculate_sma(df, "rsi", Config.TDI_FAST_MA_PERIOD)
        df, slow = Indicators.calculate_sma(df, "rsi", Config.TDI_SLOW_MA_PERIOD)

        df["tdi_fast_ma"] = df[fast]
        df["tdi_slow_ma"] = df[slow]

        return df


    # ==================================================
    # BOLLINGER BANDS
    # ==================================================
    @staticmethod
    def calculate_super_bollinger_bands(df: pd.DataFrame) -> pd.DataFrame:
        period = Config.BB_PERIOD
        dev = Config.BB_DEV

        df["bb_middle"] = df["close"].rolling(period).mean()
        df["bb_std"] = df["close"].rolling(period).std()

        df["bb_upper"] = df["bb_middle"] + (df["bb_std"] * dev)
        df["bb_lower"] = df["bb_middle"] - (df["bb_std"] * dev)

        df["bb_width_percent"] = (
            (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        )

        df["bb_rejection_buy"] = (
            (df["low"] < df["bb_lower"]) & (df["close"] > df["bb_lower"])
        )

        df["bb_rejection_sell"] = (
            (df["high"] > df["bb_upper"]) & (df["close"] < df["bb_upper"])
        )

        return df


    # ==================================================
    # ATR (CRITICAL FOR SL BUFFER)
    # ==================================================
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        try:
            high = df["high"]
            low = df["low"]
            close = df["close"]

            tr1 = high - low
            tr2 = (high - close.shift()).abs()
            tr3 = (low - close.shift()).abs()

            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr"] = tr.rolling(period).mean()

            return df

        except Exception as e:
            logger.error(f"❌ ATR error: {e}")
            df["atr"] = df["close"] * 0.001
            return df


    # ==================================================
    # ALL INDICATORS
    # ==================================================
    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]

        df = Indicators.calculate_super_tdi(df)
        df = Indicators.calculate_super_bollinger_bands(df)
        df = Indicators.calculate_atr(df)

        return df


    # ==================================================
    # SMART MONEY LOGIC
    # ==================================================
    @staticmethod
    def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> dict:
        if len(df) < lookback + 2:
            return {}

        prev = df.iloc[-lookback:-1]
        last = df.iloc[-1]

        prev_high = prev["high"].max()
        prev_low = prev["low"].min()

        body_high = max(last["open"], last["close"])
        body_low = min(last["open"], last["close"])

        # Sweep highs → BUY
        if last["high"] > prev_high and body_high <= prev_high:
            return {
                "direction": "BUY",
                "sweep_level": float(last["low"])
            }

        # Sweep lows → SELL
        if last["low"] < prev_low and body_low >= prev_low:
            return {
                "direction": "SELL",
                "sweep_level": float(last["high"])
            }

        return {}

    @staticmethod
    def detect_market_structure_shift(df: pd.DataFrame, direction: str) -> bool:
        if len(df) < 6:
            return False

        if direction == "BUY":
            return df["high"].iloc[-1] > df["high"].iloc[-3]
        else:
            return df["low"].iloc[-1] < df["low"].iloc[-3]

    @staticmethod
    def detect_fvg(df: pd.DataFrame, direction: str) -> bool:
        if len(df) < 3:
            return False

        c1 = df.iloc[-3]
        c3 = df.iloc[-1]

        if direction == "BUY":
            return c3["low"] > c1["high"]
        else:
            return c3["high"] < c1["low"]