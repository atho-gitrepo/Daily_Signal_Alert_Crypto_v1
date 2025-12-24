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

MIN_TDI_SLOPE = 0.15        # reject flat TDI
DIVERGENCE_LOOKBACK = 6

MIN_RISK_PCT = 0.0015       # 0.15%
MAX_RISK_PCT = 0.02         # 2%

ATR_SL_MULTIPLIER = 0.6     # prevents tight SL

# ================= STRATEGY =================
class ConsolidatedTrendStrategy:
    """
    Smart Money + HTF EMA + TDI + ATR
    Liquidity Sweep Sniper Strategy
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

    def _tdi_zone_ok(self, slow: float, direction: str) -> bool:
        if direction == "BUY":
            return slow >= MIN_TDI_BUY
        if direction == "SELL":
            return slow <= MAX_TDI_SELL
        return False

    def _tdi_slope(self, df: pd.DataFrame) -> float:
        """
        Calculates slope of TDI slow MA
        """
        if len(df) < 4:
            return 0.0

        y = df["tdi_slow_ma"].iloc[-4:].values
        x = np.arange(len(y))
        slope = np.polyfit(x, y, 1)[0]
        return float(slope)

    def _tdi_divergence(self, df: pd.DataFrame, direction: str) -> bool:
        """
        Rejects signal if TDI diverges against price
        """
        if len(df) < DIVERGENCE_LOOKBACK:
            return False

        price = df["close"].iloc[-DIVERGENCE_LOOKBACK:]
        tdi = df["tdi_slow_ma"].iloc[-DIVERGENCE_LOOKBACK:]

        price_slope = np.polyfit(range(len(price)), price.values, 1)[0]
        tdi_slope = np.polyfit(range(len(tdi)), tdi.values, 1)[0]

        # BUY but price up while TDI down = bearish divergence
        if direction == "BUY" and price_slope > 0 and tdi_slope < 0:
            return True

        # SELL but price down while TDI up = bullish divergence
        if direction == "SELL" and price_slope < 0 and tdi_slope > 0:
            return True

        return False

    def _risk_ok(self, entry: float, sl: float) -> bool:
        risk = abs(entry - sl)
        return entry * MIN_RISK_PCT <= risk <= entry * MAX_RISK_PCT

    # ================= SIGNAL =================
    def generate_signal(self, df_5m: pd.DataFrame) -> Tuple[str, Dict[str, Any]]:
        if df_5m.empty or len(df_5m) < 50:
            return "NO_TRADE", {"reason": "Insufficient data"}

        last = df_5m.iloc[-1]

        tdi_slow = float(last.get("tdi_slow_ma", 0))
        bb_width = float(last.get("bb_width_percent", 0))
        atr = float(last.get("atr", last["close"] * 0.001))

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

        # -------- TDI Zone --------
        if not self._tdi_zone_ok(tdi_slow, direction):
            return "NO_TRADE", {"reason": "Weak TDI zone"}

        # -------- TDI Slope --------
        tdi_slope = self._tdi_slope(df_5m)
        if abs(tdi_slope) < MIN_TDI_SLOPE:
            return "NO_TRADE", {"reason": "Flat TDI"}

        # -------- TDI Divergence --------
        if self._tdi_divergence(df_5m, direction):
            return "NO_TRADE", {"reason": "TDI divergence"}

        # -------- MSS & FVG --------
        if not Indicators.detect_market_structure_shift(df_5m, direction):
            return "NO_TRADE", {"reason": "No MSS"}

        if not Indicators.detect_fvg(df_5m, direction):
            return "NO_TRADE", {"reason": "No FVG"}

        # -------- ENTRY / SL / TP --------
        entry = float(last["close"])
        sl_buffer = atr * ATR_SL_MULTIPLIER

        if direction == "BUY":
            sl = sweep["sweep_level"] - sl_buffer
            if not self._risk_ok(entry, sl):
                return "NO_TRADE", {"reason": "Invalid BUY risk"}
            tp = entry + (entry - sl) * RRR_RATIO
        else:
            sl = sweep["sweep_level"] + sl_buffer
            if not self._risk_ok(entry, sl):
                return "NO_TRADE", {"reason": "Invalid SELL risk"}
            tp = entry - (sl - entry) * RRR_RATIO

        # -------- Debounce --------
        if self.last_signal == direction:
            return "NO_TRADE", {"reason": "Duplicate signal"}

        self.last_signal = direction

        return direction, {
            "entry_price": entry,
            "stop_loss": float(sl),
            "take_profit": float(tp),
            "signal_strength": "HARD" if abs(tdi_slope) > 0.35 else "SOFT",
            "risk_factor": RRR_RATIO,
            "tdi_slow_ma": tdi_slow,
            "tdi_slope": tdi_slope,
            "bb_width_percent": bb_width,
            "atr": atr,
        }