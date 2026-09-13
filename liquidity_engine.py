"""GoldAI Ultra — Liquidity Analysis Engine"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class LiquidityResult:
    signal: str          # BUY | SELL | NEUTRAL
    confidence: float    # 0–100
    key_level: float
    level_type: str      # support | resistance | poc | sweep
    description: str


class LiquidityEngine:
    """
    Liquidity tahlili:
    1. Volume Profile — POC, VAH, VAL
    2. Support/Resistance clustering
    3. Liquidity sweep detection
    4. Order flow imbalance
    """

    def analyze(self, df: pd.DataFrame) -> LiquidityResult:
        try:
            return self._run(df)
        except Exception:
            return LiquidityResult("NEUTRAL", 0.0, 0.0, "unknown", "Tahlil xatosi")

    def _run(self, df: pd.DataFrame) -> LiquidityResult:
        current = df["close"].iloc[-1]
        atr = df["atr"].iloc[-1] if "atr" in df.columns else current * 0.01

        poc, vah, val = self._volume_profile(df)
        poc_sig, poc_conf = self._poc_signal(current, poc, vah, val, atr, df)
        sr_sig, sr_conf, sr_level = self._support_resistance(df)
        sw_sig, sw_conf = self._liquidity_sweep(df)

        signals = []
        total_conf = 0.0
        key_level = poc
        level_type = "poc"

        if poc_conf > 0:
            signals.append(poc_sig)
            total_conf += poc_conf * 0.35

        if sr_conf > 0:
            signals.append(sr_sig)
            total_conf += sr_conf * 0.35
            if sr_conf > poc_conf:
                key_level = sr_level
                level_type = "sr"

        if sw_conf > 0:
            signals.append(sw_sig)
            total_conf += sw_conf * 0.30
            if sw_conf > max(poc_conf, sr_conf):
                level_type = "sweep"

        if not signals:
            return LiquidityResult("NEUTRAL", 0.0, poc, "poc", f"POC:{poc:.4f}")

        buy_n = signals.count("BUY")
        sell_n = signals.count("SELL")
        if buy_n > sell_n:
            final = "BUY"
        elif sell_n > buy_n:
            final = "SELL"
        else:
            final = "NEUTRAL"

        conf = min(90.0, total_conf)
        return LiquidityResult(
            signal=final,
            confidence=round(conf, 1),
            key_level=round(key_level, 5),
            level_type=level_type,
            description=f"POC:{poc:.4f} VAH:{vah:.4f} VAL:{val:.4f}"
        )

    # ─── Volume Profile ────────────────────────────────────────────

    def _volume_profile(self, df: pd.DataFrame):
        close = df["close"]
        volume = df["volume"]
        n_bins = 30
        price_min, price_max = close.min(), close.max()
        rang = price_max - price_min + 1e-10
        bins = np.linspace(price_min, price_max, n_bins + 1)

        vol_profile = np.zeros(n_bins)
        idxs = ((close.values - price_min) / rang * (n_bins - 1)).astype(int)
        idxs = np.clip(idxs, 0, n_bins - 1)
        for i, v in zip(idxs, volume.values):
            vol_profile[i] += v

        poc_bin = int(np.argmax(vol_profile))
        poc = (bins[poc_bin] + bins[poc_bin + 1]) / 2

        total = vol_profile.sum()
        target = total * 0.70
        order = np.argsort(vol_profile)[::-1]
        cum = 0.0
        va_bins = []
        for b in order:
            cum += vol_profile[b]
            va_bins.append(b)
            if cum >= target:
                break

        if va_bins:
            b_max = min(max(va_bins) + 1, n_bins)
            b_min = min(min(va_bins) + 1, n_bins)
            vah = (bins[max(va_bins)] + bins[b_max]) / 2
            val = (bins[min(va_bins)] + bins[b_min]) / 2
        else:
            vah = val = poc

        return poc, vah, val

    def _poc_signal(self, current, poc, vah, val, atr, df):
        if current < val - atr * 0.3:
            dist = (val - current) / current * 100
            return "BUY", min(80.0, 40 + dist * 5)
        if current > vah + atr * 0.3:
            dist = (current - vah) / current * 100
            return "SELL", min(80.0, 40 + dist * 5)
        if abs(current - poc) < atr * 0.5 and "ema20" in df.columns and "ema50" in df.columns:
            if df["ema20"].iloc[-1] > df["ema50"].iloc[-1]:
                return "BUY", 45.0
            return "SELL", 45.0
        return "NEUTRAL", 0.0

    # ─── Support / Resistance ──────────────────────────────────────

    def _support_resistance(self, df: pd.DataFrame):
        current = df["close"].iloc[-1]
        atr = df["atr"].iloc[-1] if "atr" in df.columns else current * 0.01
        lookback = min(50, len(df))
        h = df["high"].tail(lookback).values
        l = df["low"].tail(lookback).values

        pivot_h, pivot_l = [], []
        for i in range(2, len(h) - 2):
            if h[i] > h[i-1] and h[i] > h[i-2] and h[i] >= h[i+1] and h[i] >= h[i+2]:
                pivot_h.append(h[i])
            if l[i] < l[i-1] and l[i] < l[i-2] and l[i] <= l[i+1] and l[i] <= l[i+2]:
                pivot_l.append(l[i])

        supports = [p for p in pivot_l if p < current]
        resistances = [p for p in pivot_h if p > current]

        if supports and resistances:
            sup = max(supports)
            res = min(resistances)
            d_sup = (current - sup) / atr
            d_res = (res - current) / atr
            if d_sup < 1.5 and d_sup < d_res:
                return "BUY", min(75.0, max(0.0, 60 - d_sup * 10)), sup
            if d_res < 1.5 and d_res < d_sup:
                return "SELL", min(75.0, max(0.0, 60 - d_res * 10)), res

        return "NEUTRAL", 0.0, current

    # ─── Liquidity Sweep ───────────────────────────────────────────

    def _liquidity_sweep(self, df: pd.DataFrame):
        if len(df) < 20:
            return "NEUTRAL", 0.0

        close = df["close"]
        high = df["high"]
        low = df["low"]
        lookback = min(40, len(df) - 5)
        atr = df["atr"].iloc[-1] if "atr" in df.columns else close.iloc[-1] * 0.01

        prev_high = high.iloc[-lookback:-5].max()
        prev_low = low.iloc[-lookback:-5].min()
        recent_high = high.iloc[-5:].max()
        recent_low = low.iloc[-5:].min()
        current = close.iloc[-1]

        # Bearish sweep
        if recent_high > prev_high and current < prev_high - atr * 0.3:
            excess = (recent_high - prev_high) / atr
            if excess < 2:
                return "SELL", min(80.0, 50 + excess * 10)

        # Bullish sweep
        if recent_low < prev_low and current > prev_low + atr * 0.3:
            excess = (prev_low - recent_low) / atr
            if excess < 2:
                return "BUY", min(80.0, 50 + excess * 10)

        return "NEUTRAL", 0.0
