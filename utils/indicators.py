# strategy/indicators.py
import pandas as pd
import numpy as np
import logging
from settings import Config

logger = logging.getLogger(__name__)

class Indicators:

    # ------------------- CORE -------------------
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = Config.TDI_RSI_PERIOD) -> pd.DataFrame:
        try:
            if len(df) < period:
                df['rsi'] = np.nan
                return df
            df['close'] = df['close'].ffill().replace(0, np.finfo(float).eps)
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
            avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
            rs = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
            df['rsi'] = 100 - (100 / (1 + rs))
            return df
        except Exception as e:
            logger.error(f"RSI error: {e}")
            df['rsi'] = np.nan
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

    # ------------------- TDI / BB -------------------
    @staticmethod
    def calculate_super_tdi(df: pd.DataFrame) -> pd.DataFrame:
        df = Indicators.calculate_rsi(df)
        df, fast = Indicators.calculate_sma(df, 'rsi', Config.TDI_FAST_MA_PERIOD)
        df, slow = Indicators.calculate_sma(df, 'rsi', Config.TDI_SLOW_MA_PERIOD)
        df['tdi_fast_ma'] = df[fast]
        df['tdi_slow_ma'] = df[slow]
        return df

    @staticmethod
    def calculate_super_bollinger_bands(df: pd.DataFrame) -> pd.DataFrame:
        period, dev = Config.BB_PERIOD, Config.BB_DEV
        df['bb_middle'] = df['close'].rolling(period).mean()
        df['bb_std'] = df['close'].rolling(period).std()
        df['bb_upper'] = df['bb_middle'] + df['bb_std'] * dev
        df['bb_lower'] = df['bb_middle'] - df['bb_std'] * dev
        df['bb_width_percent'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        df['bb_rejection_buy'] = (df['low'] < df['bb_lower']) & (df['close'] > df['bb_lower'])
        df['bb_rejection_sell'] = (df['high'] > df['bb_upper']) & (df['close'] < df['bb_upper'])
        return df

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [c.lower() for c in df.columns]
        df = Indicators.calculate_super_tdi(df)
        df = Indicators.calculate_super_bollinger_bands(df)
        return df

    # ------------------- SMART MONEY -------------------
    @staticmethod
    def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> dict:
        if len(df) < lookback + 2:
            return {}
        prev = df.iloc[-lookback:-1]
        last = df.iloc[-1]
        prev_high, prev_low = prev['high'].max(), prev['low'].min()
        body_high, body_low = max(last['open'], last['close']), min(last['open'], last['close'])

        if last['high'] > prev_high and body_high <= prev_high:
            return {"direction": "BUY", "sweep_level": last['low']}
        if last['low'] < prev_low and body_low >= prev_low:
            return {"direction": "SELL", "sweep_level": last['high']}
        return {}

    @staticmethod
    def detect_market_structure_shift(df: pd.DataFrame, direction: str) -> bool:
        if len(df) < 6:
            return False
        return df['high'].iloc[-1] > df['high'].iloc[-3] if direction == "BUY" else df['low'].iloc[-1] < df['low'].iloc[-3]

    @staticmethod
    def detect_fvg(df: pd.DataFrame, direction: str) -> bool:
        if len(df) < 3:
            return False
        c1, c3 = df.iloc[-3], df.iloc[-1]
        return c3['low'] > c1['high'] if direction == "BUY" else c3['high'] < c1['low']

    # ------------------- ALERT HEADER -------------------
    @staticmethod
    def get_alert_message_header(signal: str, strength: str, symbol: str):
        signal = signal.upper()
        strength = strength.upper()
        if signal == 'BUY':
            return f"🟢 {strength} BUY | LONG *{symbol}*", "LONG"
        elif signal == 'SELL':
            return f"🔴 {strength} SELL | SHORT *{symbol}*", "SHORT"
        else:
            return f"ℹ️ NO TRADE | *{symbol}*", "NO_TRADE"