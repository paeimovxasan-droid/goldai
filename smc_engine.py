"""GoldAI Ultra — Smart Money Concepts (SMC/ICT) Engine"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class SMCResult:
    signal: str        # BUY | SELL | NEUTRAL
    confidence: float  # 0–100
    trend: str         # BULLISH | BEARISH | NEUTRAL
    structure: str     # BOS | CHOCH | CONTINUATION | CONSOLIDATION
    description: str


class SMCEngine:
    """
    Smart Money Concepts tahlili:
    1. Market Structure — BOS / CHoCH
    2. Order Blocks
    3. Fair Value Gaps (FVG / Imbalance)
    4. Premium / Discount zones
    """

    def analyze(self, df: pd.DataFrame) -> SMCResult:
        try:
            return self._run(df)
        except Exception:
            return SMCResult("NEUTRAL", 0.0, "NEUTRAL", "CONSOLIDATION", "Tahlil xatosi")

    def _run(self, df: pd.DataFrame) -> SMCResult:
        trend, structure, ms_score = self._market_structure(df)
        ob_sig, ob_score = self._order_blocks(df)
        fvg_sig, fvg_score = self._fair_value_gaps(df)
        pd_sig, pd_score = self._premium_discount(df)

        scores = [ms_score, ob_score, fvg_score, pd_score]
        sigs = []
        if ms_score > 0:
            sigs.append("BUY")
        elif ms_score < 0:
            sigs.append("SELL")
        for sig, sc in [(ob_sig, ob_score), (fvg_sig, fvg_score), (pd_sig, pd_score)]:
            if sc != 0:
                sigs.append(sig)

        net = sum(scores)
        total = sum(abs(s) for s in scores)

        if total == 0:
            return SMCResult("NEUTRAL", 0.0, trend, structure, "Signal yo'q")

        raw_conf = abs(net) / total * 60 + abs(net) * 0.4
        confidence = min(92.0, raw_conf)

        buy_n = sigs.count("BUY")
        sell_n = sigs.count("SELL")

        if buy_n > sell_n and net > 8:
            final = "BUY"
        elif sell_n > buy_n and net < -8:
            final = "SELL"
        else:
            final = "NEUTRAL"

        desc = f"Structure:{structure} | OB:{ob_sig} | FVG:{fvg_sig} | PD:{pd_sig}"
        return SMCResult(
            signal=final,
            confidence=round(confidence, 1),
            trend=trend,
            structure=structure,
            description=desc
        )

    # ─── 1. Market Structure ──────────────────────────────────────

    def _market_structure(self, df: pd.DataFrame):
        if len(df) < 30:
            return "NEUTRAL", "CONSOLIDATION", 0

        n = min(40, len(df))
        h = df["high"].values[-n:]
        l = df["low"].values[-n:]
        c = df["close"].values[-n:]

        sh, sl = [], []
        for i in range(2, len(h) - 2):
            if h[i] >= h[i-1] and h[i] >= h[i-2] and h[i] >= h[i+1] and h[i] >= h[i+2]:
                sh.append(h[i])
            if l[i] <= l[i-1] and l[i] <= l[i-2] and l[i] <= l[i+1] and l[i] <= l[i+2]:
                sl.append(l[i])

        if len(sh) < 2 or len(sl) < 2:
            ema_trend = self._ema_trend(df)
            return ema_trend, "CONSOLIDATION", 0

        hh = sh[-1] > sh[-2]   # Higher High
        hl = sl[-1] > sl[-2]   # Higher Low
        lh = sh[-1] < sh[-2]   # Lower High
        ll = sl[-1] < sl[-2]   # Lower Low

        current = c[-1]
        ema_trend = self._ema_trend(df)

        if hh and hl:
            trend = "BULLISH"
            structure = "BOS" if current > sh[-1] else "CONTINUATION"
            score = 40 if structure == "BOS" else 25
        elif lh and ll:
            trend = "BEARISH"
            structure = "BOS" if current < sl[-1] else "CONTINUATION"
            score = -40 if structure == "BOS" else -25
        elif hh and ll:
            trend = "BEARISH" if ema_trend == "BEARISH" else "NEUTRAL"
            structure = "CHOCH"
            score = -20
        elif lh and hl:
            trend = "BULLISH" if ema_trend == "BULLISH" else "NEUTRAL"
            structure = "CHOCH"
            score = 20
        else:
            trend = ema_trend
            structure = "CONSOLIDATION"
            score = 0

        # EMA trend bonus
        if ema_trend == trend and trend != "NEUTRAL":
            score = int(score * 1.3)

        return trend, structure, score

    def _ema_trend(self, df: pd.DataFrame) -> str:
        if "ema20" in df.columns and "ema50" in df.columns and "ema200" in df.columns:
            e20 = df["ema20"].iloc[-1]
            e50 = df["ema50"].iloc[-1]
            e200 = df["ema200"].iloc[-1]
            if e20 > e50 > e200:
                return "BULLISH"
            if e20 < e50 < e200:
                return "BEARISH"
        return "NEUTRAL"

    # ─── 2. Order Blocks ──────────────────────────────────────────

    def _order_blocks(self, df: pd.DataFrame):
        if len(df) < 15:
            return "NEUTRAL", 0

        current = df["close"].iloc[-1]
        atr = df["atr"].iloc[-1] if "atr" in df.columns else current * 0.01
        n = min(25, len(df) - 5)
        recent = df.iloc[-n - 5: -5]
        avg_vol = recent["volume"].mean()

        bull_obs, bear_obs = [], []
        for i in range(len(recent) - 1):
            o = recent["open"].iloc[i]
            c = recent["close"].iloc[i]
            h = recent["high"].iloc[i]
            l = recent["low"].iloc[i]
            v = recent["volume"].iloc[i]
            if v < avg_vol * 1.3:
                continue
            next_c = recent["close"].iloc[i + 1]
            if c < o and next_c > c:         # Bearish OB => bullish reversal
                bull_obs.append((l, h))
            elif c > o and next_c < c:       # Bullish OB => bearish reversal
                bear_obs.append((l, h))

        for lo, hi in bull_obs[-3:]:
            if lo - atr * 0.5 <= current <= hi + atr * 0.5:
                return "BUY", 35

        for lo, hi in bear_obs[-3:]:
            if lo - atr * 0.5 <= current <= hi + atr * 0.5:
                return "SELL", 35

        return "NEUTRAL", 0

    # ─── 3. Fair Value Gaps ───────────────────────────────────────

    def _fair_value_gaps(self, df: pd.DataFrame):
        if len(df) < 10:
            return "NEUTRAL", 0

        current = df["close"].iloc[-1]
        atr = df["atr"].iloc[-1] if "atr" in df.columns else current * 0.01
        h = df["high"].values
        l = df["low"].values

        start = max(0, len(df) - 30)
        for i in range(start, len(df) - 2):
            # Bullish FVG: gap[i].high < gap[i+2].low
            if h[i] < l[i + 2]:
                fvg_lo, fvg_hi = h[i], l[i + 2]
                if fvg_lo - atr * 0.2 <= current <= fvg_hi + atr * 0.2:
                    return "BUY", 30

            # Bearish FVG: gap[i].low > gap[i+2].high
            if i + 2 < len(l) and l[i] > h[i + 2]:
                fvg_lo, fvg_hi = h[i + 2], l[i]
                if fvg_lo - atr * 0.2 <= current <= fvg_hi + atr * 0.2:
                    return "SELL", 30

        return "NEUTRAL", 0

    # ─── 4. Premium / Discount ────────────────────────────────────

    def _premium_discount(self, df: pd.DataFrame):
        if len(df) < 20:
            return "NEUTRAL", 0

        n = min(60, len(df))
        period_high = df["high"].tail(n).max()
        period_low = df["low"].tail(n).min()
        rang = period_high - period_low
        if rang < 1e-10:
            return "NEUTRAL", 0

        current = df["close"].iloc[-1]
        pos = (current - period_low) / rang  # 0.0 = bottom, 1.0 = top

        if pos < 0.35:
            conf = (0.35 - pos) / 0.35 * 50
            return "BUY", min(50.0, conf)
        if pos > 0.65:
            conf = (pos - 0.65) / 0.35 * 50
            return "SELL", min(50.0, conf)

        return "NEUTRAL", 0
