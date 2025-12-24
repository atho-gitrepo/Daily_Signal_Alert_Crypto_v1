# strategy/consolidated_trend.py
import pandas as pd
import logging
from typing import Dict, Any, Tuple
from utils.indicators import Indicators

logger = logging.getLogger(__name__)

class ConsolidatedTrendStrategy:
    """Smart Money + TDI + BB + HTF trend strategy."""

    def __init__(self):
        self.htf_trend = "NEUTRAL"
        self.last_signal = "NO_TRADE"

    # ------------------- HTF TREND -------------------
    def set_htf_trend(self, htf_df: pd.DataFrame):
        """Calculate 1H EMA trend."""
        htf_df = Indicators.calculate_ema(htf_df, 'close', 20)
        last = htf_df.iloc[-1]
        ema_col = 'close_ema_20'
        if last['close'] > last.get(ema_col, last['close']):
            self.htf_trend = "BULL"
        elif last['close'] < last.get(ema_col, last['close']):
            self.htf_trend = "BEAR"
        else:
            self.htf_trend = "NEUTRAL"

    def get_strategy_stats(self) -> Dict[str, Any]:
        return {"htf_trend": self.htf_trend}

    # ------------------- 5M DATA -------------------
    def analyze_data(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = Indicators.calculate_all_indicators(df)
        return df

    # ------------------- SIGNAL GENERATION -------------------
    def generate_signal(self, df_5m: pd.DataFrame) -> Tuple[str, Dict[str, Any]]:
        if df_5m.empty or len(df_5m) < 30:
            return "NO_TRADE", {"reason": "Insufficient data"}

        last = df_5m.iloc[-1]

        # TDI / BB
        tdi_slow = last.get("tdi_slow_ma", 0)
        bb_width = last.get("bb_width_percent", 0)

        # 🔥 SMART MONEY FILTERS
        sweep = Indicators.detect_liquidity_sweep(df_5m)
        if not sweep:
            return "NO_TRADE", {"reason": "No liquidity sweep"}

        direction = sweep["direction"]

        # HTF Alignment
        if (direction == "BUY" and self.htf_trend != "BULL") or \
           (direction == "SELL" and self.htf_trend != "BEAR"):
            return "NO_TRADE", {"reason": "HTF misaligned"}

        # MSS / FVG
        if not Indicators.detect_market_structure_shift(df_5m, direction):
            return "NO_TRADE", {"reason": "No MSS"}
        if not Indicators.detect_fvg(df_5m, direction):
            return "NO_TRADE", {"reason": "No FVG pullback"}

        # ENTRY / SL / TP
        entry = last['close']
        sl = sweep["sweep_level"]
        risk = (entry - sl) if direction == "BUY" else (sl - entry)
        tp = entry + (risk * 2) if direction == "BUY" else entry - (risk * 2)
        signal = direction

        if risk <= 0:
            return "NO_TRADE", {"reason": "Invalid risk"}

        # Debounce to avoid duplicate alerts
        if self.last_signal == signal:
            return "NO_TRADE", {"reason": "Duplicate signal"}

        self.last_signal = signal

        return signal, {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "risk_factor": 2.0,
            "signal_strength": "SOFT",
            "tdi_slow_ma": float(tdi_slow),
            "bb_width_percent": float(bb_width)
        }