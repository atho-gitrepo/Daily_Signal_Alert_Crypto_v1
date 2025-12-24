import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Tuple
from utils.indicators import Indicators

logger = logging.getLogger(__name__)

# ================= CONFIG =================
HTF_EMA_PERIOD = 20
RRR_RATIO = 2.0

MIN_BB_WIDTH = 0.003
MAX_BB_WIDTH = 0.03

MIN_TDI_BUY = 30
MAX_TDI_SELL = 70

MIN_RISK_PCT = 0.0015   # 0.15%
MAX_RISK_PCT = 0.02     # 2%

# ================= STRATEGY =================
class ConsolidatedTrendStrategy:
    """
    Smart Money + TDI + BB + HTF Trend
    Safe, non-repainting, sniper-ready
    """

    def __init__(self):
        self.htf_trend = "NEUTRAL"
        self.last_signal = "NO_TRADE"

    # ================= HTF TREND =================
    def set_htf_trend(self, htf_df: pd.DataFrame):
        if htf_df.empty:
            self.htf_trend = "NEUTRAL"
            return

        htf_df = Indicators.calculate_ema(htf_df, "close", HTF_EMA_PERIOD)
        last = htf_df.iloc[-1]
        ema_col = f"close_ema_{HTF_EMA_PERIOD}"

        if last["close"] > last[ema_col]:
            self.htf_trend = "BULL"
        elif last["close"] < last[ema_col]:
            self.htf_trend = "BEAR"
        else:
            self.htf_trend = "NEUTRAL"

    def get_strategy_stats(self) -> Dict[str, Any]:
        return {"htf_trend": self.htf_trend}

    # ================= DATA =================
    def analyze_data(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        return Indicators.calculate_all_indicators(df)

    # ================= HELPERS =================
    def _bb_ok(self, width: float) -> bool:
        return MIN_BB_WIDTH <= width <= MAX_BB_WIDTH

    def _tdi_ok(self, slow: float, direction: str) -> bool:
        if direction == "BUY":
            return slow >= MIN_TDI_BUY
        if direction == "SELL":
            return slow <= MAX_TDI_SELL
        return False

    def _risk_ok(self, entry: float, sl: float) -> bool:
        risk = abs(entry - sl)
        return entry * MIN_RISK_PCT <= risk <= entry * MAX_RISK_PCT

    # ================= SIGNAL =================
    def generate_signal(self, df_5m: pd.DataFrame) -> Tuple[str, Dict[str, Any]]:
        if df_5m.empty or len(df_5m) < 40:
            return "NO_TRADE", {"reason": "Insufficient data"}

        last = df_5m.iloc[-1]

        tdi_slow = last.get("tdi_slow_ma", 0)
        bb_width = last.get("bb_width_percent", 0)
        atr = last.get("atr", last["close"] * 0.001)

        # -------- Volatility Filter --------
        if not self._bb_ok(bb_width):
            return "NO_TRADE", {"reason": "BB width filter"}

        # -------- Liquidity Sweep --------
        sweep = Indicators.detect_liquidity_sweep(df_5m)
        if not sweep:
            return "NO_TRADE", {"reason": "No liquidity sweep"}

        direction = sweep["direction"]

        # -------- HTF Alignment --------
        if direction == "BUY" and self.htf_trend != "BULL":
            return "NO_TRADE", {"reason": "HTF not BULL"}
        if direction == "SELL" and self.htf_trend != "BEAR":
            return "NO_TRADE", {"reason": "HTF not BEAR"}

        # -------- TDI Filter --------
        if not self._tdi_ok(tdi_slow, direction):
            return "NO_TRADE", {"reason": "Weak TDI zone"}

        # -------- MSS & FVG --------
        if not Indicators.detect_market_structure_shift(df_5m, direction):
            return "NO_TRADE", {"reason": "No MSS"}

        if not Indicators.detect_fvg(df_5m, direction):
            return "NO_TRADE", {"reason": "No FVG pullback"}

        # -------- ENTRY / SL / TP --------
        entry = last["close"]
        buffer = atr * 0.5

        if direction == "BUY":
            sl = sweep["sweep_level"] - buffer
            if not self._risk_ok(entry, sl):
                return "NO_TRADE", {"reason": "Invalid BUY risk"}
            tp = entry + (entry - sl) * RRR_RATIO

        else:
            sl = sweep["sweep_level"] + buffer
            if not self._risk_ok(entry, sl):
                return "NO_TRADE", {"reason": "Invalid SELL risk"}
            tp = entry - (sl - entry) * RRR_RATIO

        # -------- Debounce --------
        if self.last_signal == direction:
            return "NO_TRADE", {"reason": "Duplicate signal"}

        self.last_signal = direction

        return direction, {
            "entry_price": float(entry),
            "stop_loss": float(sl),
            "take_profit": float(tp),
            "signal_strength": "SOFT",
            "risk_factor": RRR_RATIO,
            "tdi_slow_ma": float(tdi_slow),
            "bb_width_percent": float(bb_width),
        }