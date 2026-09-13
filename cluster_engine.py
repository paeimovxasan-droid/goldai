"""
GoldAI Ultra — V3 Cluster & Volume Profile Engine
Professional-grade volume analysis: POC, VAH, VAL, Delta, CVD
Paid tool equivalent — free implementation from OHLC + aggTrades data
"""

import asyncio
import aiohttp
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from core.logger import logger


@dataclass
class ClusterResult:
    cluster_score: float       # -30 to +30 (positive = bullish cluster alignment)
    poc: float                 # Point of Control (highest volume price)
    vah: float                 # Value Area High (70% volume upper bound)
    val: float                 # Value Area Low (70% volume lower bound)
    delta_score: float         # -20 to +20 (CVD bias)
    nearest_support: float     # Nearest cluster support below price
    nearest_resistance: float  # Nearest cluster resistance above price
    cluster_type: str          # "SUPPORT" | "RESISTANCE" | "NEUTRAL"
    cvd_trend: str             # "BULLISH" | "BEARISH" | "NEUTRAL"
    imbalance_pct: float       # Buy vs sell imbalance %
    reason: str                # Human-readable reason


class ClusterEngine:
    """
    V3 Volume Cluster Analysis — professional order flow equivalent.

    Algorithm:
    1. Volume Profile: distribute OHLC volume across price buckets
    2. Find POC (max volume level), VAH/VAL (70% value area)
    3. Delta estimation from candle body/wick structure
    4. CVD (Cumulative Volume Delta) trend
    5. Cluster support/resistance detection
    6. Entry score based on price location vs clusters
    """

    BINANCE_FUTURES = "https://fapi.binance.com"
    BINANCE_SPOT    = "https://api.binance.com"

    SYMBOL_MAP = {
        "BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT",
        "BNBUSD": "BNBUSDT", "SOLUSD": "SOLUSDT",
        "XRPUSD": "XRPUSDT", "ADAUSD": "ADAUSDT",
        "DOTUSD": "DOTUSDT", "AVAXUSD": "AVAXUSDT",
    }

    def __init__(self):
        self._cache: dict = {}      # symbol -> (timestamp, ClusterResult)
        self._cache_ttl = 300       # 5 daqiqa kesh

    def analyze_ohlc(self, df: pd.DataFrame, current_price: float, signal: str) -> ClusterResult:
        """
        OHLC + volume dan cluster tahlil — Binance API siz ham ishlaydi.
        Volume Profile, Delta, CVD ni OHLC dan hisoblaydi.
        """
        try:
            if len(df) < 20:
                return self._neutral_result(current_price)

            # ── 1. Volume Profile hisoblash ──────────────────────────
            vap, price_levels = self._volume_at_price(df)

            # ── 2. POC, VAH, VAL ─────────────────────────────────────
            poc, vah, val = self._calc_value_area(vap, price_levels)

            # ── 3. Delta estimation from candle structure ─────────────
            delta_arr = self._estimate_delta(df)
            cvd = np.cumsum(delta_arr)

            # ── 4. CVD trend (so'nggi 20 sham) ───────────────────────
            cvd_recent = cvd[-20:]
            cvd_slope = cvd_recent[-1] - cvd_recent[0]
            cvd_trend = "BULLISH" if cvd_slope > 0 else "BEARISH" if cvd_slope < 0 else "NEUTRAL"
            delta_score = min(20.0, max(-20.0, cvd_slope / max(abs(cvd).max(), 1e-10) * 20))

            # ── 5. Cluster zonal analiz ───────────────────────────────
            support, resistance = self._find_cluster_zones(vap, price_levels, current_price)

            # ── 6. Buy/Sell imbalance (so'nggi 10 sham) ───────────────
            recent_delta = delta_arr[-10:]
            buy_vol  = recent_delta[recent_delta > 0].sum()
            sell_vol = abs(recent_delta[recent_delta < 0].sum())
            total_vol = buy_vol + sell_vol
            imbalance_pct = ((buy_vol - sell_vol) / max(total_vol, 1e-10)) * 100

            # ── 7. Cluster score: narxning cluster ga nisbati ─────────
            cluster_score, cluster_type, reason = self._score_cluster_alignment(
                current_price, signal, poc, vah, val, support, resistance, imbalance_pct
            )

            # Delta bonus: CVD signal yo'nalishi bilan mos kelsa
            if signal == "BUY" and cvd_trend == "BULLISH":
                cluster_score += 5
                reason += " | CVD↑"
            elif signal == "SELL" and cvd_trend == "BEARISH":
                cluster_score += 5
                reason += " | CVD↓"
            elif (signal == "BUY" and cvd_trend == "BEARISH") or (signal == "SELL" and cvd_trend == "BULLISH"):
                cluster_score -= 5
                reason += f" | CVD diverge"

            cluster_score = min(30.0, max(-30.0, cluster_score))

            return ClusterResult(
                cluster_score=cluster_score,
                poc=poc, vah=vah, val=val,
                delta_score=delta_score,
                nearest_support=support,
                nearest_resistance=resistance,
                cluster_type=cluster_type,
                cvd_trend=cvd_trend,
                imbalance_pct=imbalance_pct,
                reason=reason
            )

        except Exception as e:
            logger.debug(f"Cluster analiz xato: {e}")
            return self._neutral_result(current_price)

    def _volume_at_price(self, df: pd.DataFrame, n_buckets: int = 40):
        """
        OHLC dan Volume at Price (VAP) histogram hisoblash.
        Har bir sham uchun hajmni narx diapazoni bo'ylab taqsimlaydi.
        """
        price_min = df["low"].min()
        price_max = df["high"].max()
        if price_max <= price_min:
            mid = (price_max + price_min) / 2
            return np.array([1.0]), np.array([mid])

        bucket_size = (price_max - price_min) / n_buckets
        vap = np.zeros(n_buckets)
        price_levels = np.linspace(price_min + bucket_size / 2, price_max - bucket_size / 2, n_buckets)

        for _, row in df.iterrows():
            h, l, vol = row["high"], row["low"], row.get("volume", 1.0)
            if h <= l or vol <= 0:
                continue

            # Bu sham qaysi bucketlarga tegadi?
            lo_idx = max(0, int((l - price_min) / bucket_size))
            hi_idx = min(n_buckets - 1, int((h - price_min) / bucket_size))
            span = hi_idx - lo_idx + 1

            if span <= 0:
                vap[lo_idx] += vol
            else:
                # Triangular weighting: close ga yaqin bucketlarga ko'proq hajm
                close = row["close"]
                close_idx = int((close - price_min) / bucket_size)
                close_idx = max(lo_idx, min(hi_idx, close_idx))
                for b in range(lo_idx, hi_idx + 1):
                    dist = abs(b - close_idx)
                    weight = max(0.1, 1.0 - dist * 0.15)
                    vap[b] += vol * weight / span

        return vap, price_levels

    def _calc_value_area(self, vap: np.ndarray, price_levels: np.ndarray):
        """
        POC, VAH, VAL hisoblash.
        VAH/VAL — jami hajmning 70% ni o'z ichiga olgan narx diapazoni.
        """
        if len(vap) == 0 or vap.sum() == 0:
            mid = price_levels[len(price_levels) // 2] if len(price_levels) > 0 else 0
            return mid, mid * 1.002, mid * 0.998

        poc_idx = np.argmax(vap)
        poc = price_levels[poc_idx]

        # 70% value area
        total = vap.sum()
        target = total * 0.70
        accumulated = vap[poc_idx]
        lo_idx = hi_idx = poc_idx

        while accumulated < target:
            # Ko'p hajm tarafga kengay
            lo_vol = vap[lo_idx - 1] if lo_idx > 0 else 0
            hi_vol = vap[hi_idx + 1] if hi_idx < len(vap) - 1 else 0
            if lo_vol == 0 and hi_vol == 0:
                break
            if hi_vol >= lo_vol:
                hi_idx = min(hi_idx + 1, len(vap) - 1)
                accumulated += vap[hi_idx]
            else:
                lo_idx = max(lo_idx - 1, 0)
                accumulated += vap[lo_idx]

        return poc, price_levels[hi_idx], price_levels[lo_idx]

    def _estimate_delta(self, df: pd.DataFrame) -> np.ndarray:
        """
        Har bir sham uchun delta (buy-sell volume) baholash.
        Professional footprint chart ekvivalenti.

        Methodology:
        - Bullish candle (close>open): buy_vol = 70%×vol, sell_vol = 30%
        - Bearish candle (close<open): buy_vol = 30%×vol, sell_vol = 70%
        - Lower wick: ko'proq buy pressure → delta ga +
        - Upper wick: ko'proq sell pressure → delta ga -
        """
        delta = np.zeros(len(df))
        for i, (_, row) in enumerate(df.iterrows()):
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            vol = row.get("volume", 1.0)
            if vol <= 0:
                continue

            body = abs(c - o)
            candle_range = max(h - l, 1e-10)

            # Sham yo'nalishi
            if c >= o:
                # Bullish
                base_ratio = 0.65
            else:
                # Bearish
                base_ratio = 0.35

            # Wick korreksiyasi
            lower_wick = min(o, c) - l
            upper_wick = h - max(o, c)
            wick_adj = (lower_wick - upper_wick) / candle_range * 0.15

            buy_ratio = min(0.9, max(0.1, base_ratio + wick_adj))
            buy_vol  = vol * buy_ratio
            sell_vol = vol * (1 - buy_ratio)
            delta[i] = buy_vol - sell_vol

        return delta

    def _find_cluster_zones(self, vap: np.ndarray, price_levels: np.ndarray,
                             current_price: float):
        """
        Yuqori hajmli narx zonalarini topish (support/resistance clusters).
        Returns: (nearest_support, nearest_resistance)
        """
        if len(vap) == 0:
            return current_price * 0.99, current_price * 1.01

        # Eng yuqori 20% hajmli zonalar
        threshold = np.percentile(vap[vap > 0], 70) if (vap > 0).any() else 0

        supports = []
        resistances = []
        for i, (price, vol) in enumerate(zip(price_levels, vap)):
            if vol >= threshold:
                if price < current_price:
                    supports.append(price)
                elif price > current_price:
                    resistances.append(price)

        support = max(supports) if supports else current_price * 0.99
        resistance = min(resistances) if resistances else current_price * 1.01
        return support, resistance

    def _score_cluster_alignment(self, current_price: float, signal: str,
                                   poc: float, vah: float, val: float,
                                   support: float, resistance: float,
                                   imbalance_pct: float) -> tuple[float, str, str]:
        """
        Signal yo'nalishi va cluster zonasi mos kelishini baholash.

        BUY signali uchun ideal:
        - Narx VAL yaqinida (value area quyi chegarada) → kuchli support
        - Narx POC dan pasqari → diskont zona
        - Imbalance > 0 (buy pressure)
        - Narx cluster support ga yaqin

        SELL signali uchun ideal:
        - Narx VAH yaqinida (value area yuqori chegarada) → kuchli resistance
        - Narx POC dan yuqori → premium zona
        - Imbalance < 0 (sell pressure)
        - Narx cluster resistance ga yaqin
        """
        score = 0.0
        cluster_type = "NEUTRAL"
        reasons = []

        poc_dist_pct = abs(current_price - poc) / max(poc, 1e-10) * 100
        val_dist_pct = abs(current_price - val) / max(val, 1e-10) * 100
        vah_dist_pct = abs(current_price - vah) / max(vah, 1e-10) * 100
        sup_dist_pct = abs(current_price - support) / max(support, 1e-10) * 100
        res_dist_pct = abs(current_price - resistance) / max(resistance, 1e-10) * 100

        if signal == "BUY":
            # Narx VAL yaqin → kuchli buy zone
            if current_price <= val * 1.005:
                score += 20
                cluster_type = "SUPPORT"
                reasons.append(f"VAL sup({val:.4f})")
            elif current_price <= val * 1.015:
                score += 10
                cluster_type = "SUPPORT"
                reasons.append(f"near VAL")

            # Narx POC dan past → diskont
            if current_price < poc:
                score += 8
                reasons.append(f"below POC({poc:.4f})")
            elif current_price > vah:
                score -= 10
                reasons.append("above VAH")

            # Cluster support yaqin → yana kuchli
            if sup_dist_pct < 0.3:
                score += 12
                reasons.append(f"cluster sup")
            elif sup_dist_pct < 0.8:
                score += 6

            # Resistance yaqin → risk
            if res_dist_pct < 0.3:
                score -= 8
                reasons.append("near resist")

            # Imbalance: buy > sell
            if imbalance_pct > 15:
                score += 8
                reasons.append(f"buy imbal {imbalance_pct:.0f}%")
            elif imbalance_pct < -15:
                score -= 8

        else:  # SELL
            # Narx VAH yaqin → kuchli sell zone
            if current_price >= vah * 0.995:
                score += 20
                cluster_type = "RESISTANCE"
                reasons.append(f"VAH res({vah:.4f})")
            elif current_price >= vah * 0.985:
                score += 10
                cluster_type = "RESISTANCE"
                reasons.append(f"near VAH")

            # Narx POC dan yuqori → premium
            if current_price > poc:
                score += 8
                reasons.append(f"above POC({poc:.4f})")
            elif current_price < val:
                score -= 10
                reasons.append("below VAL")

            # Cluster resistance yaqin
            if res_dist_pct < 0.3:
                score += 12
                reasons.append(f"cluster res")
            elif res_dist_pct < 0.8:
                score += 6

            # Support yaqin → risk
            if sup_dist_pct < 0.3:
                score -= 8
                reasons.append("near support")

            # Imbalance: sell > buy
            if imbalance_pct < -15:
                score += 8
                reasons.append(f"sell imbal {abs(imbalance_pct):.0f}%")
            elif imbalance_pct > 15:
                score -= 8

        return score, cluster_type, " | ".join(reasons) if reasons else "NEUTRAL"

    def _neutral_result(self, price: float) -> ClusterResult:
        return ClusterResult(
            cluster_score=0.0, poc=price, vah=price * 1.01, val=price * 0.99,
            delta_score=0.0, nearest_support=price * 0.99, nearest_resistance=price * 1.01,
            cluster_type="NEUTRAL", cvd_trend="NEUTRAL", imbalance_pct=0.0, reason="insufficient data"
        )

    async def analyze_with_m5(self, symbol: str, df_m15: pd.DataFrame,
                                current_price: float, signal: str) -> ClusterResult:
        """
        M5 OHLC — Libertex rejimida M15 dan foydalanadi (MT5 M5 ham mavjud bo'lsa MT5 dan).
        Binance faqat ENABLE_BINANCE=true bo'lsa.
        """
        # Libertex rejimida — M15 dan to'g'ridan cluster (MT5 da M5 ham bor, lekin tezlik uchun M15 yetarli)
        from core.config import config
        if not config.enable_binance:
            # Libertex: MT5 dagi M15 ma'lumot yetarli, qo'shimcha Binance so'rovi kerak emas
            return self.analyze_ohlc(df_m15, current_price, signal)

        bn_sym = self.SYMBOL_MAP.get(symbol)
        if not bn_sym:
            return self.analyze_ohlc(df_m15, current_price, signal)

        # Kesh tekshiruvi
        import time
        cache_key = f"{symbol}_{signal}"
        if cache_key in self._cache:
            ts, result = self._cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return result

        try:
            url = f"{self.BINANCE_FUTURES}/fapi/v1/klines"
            params = {"symbol": bn_sym, "interval": "5m", "limit": 100}
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        return self.analyze_ohlc(df_m15, current_price, signal)
                    raw = await r.json()

            if not raw or len(raw) < 20:
                return self.analyze_ohlc(df_m15, current_price, signal)

            df_m5 = pd.DataFrame(raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_vol", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore"
            ])
            for col in ["open", "high", "low", "close", "volume"]:
                df_m5[col] = pd.to_numeric(df_m5[col])

            result = self.analyze_ohlc(df_m5, current_price, signal)
            self._cache[cache_key] = (time.time(), result)
            return result

        except Exception as e:
            logger.debug(f"Cluster M5 xato ({symbol}): {e}")
            return self.analyze_ohlc(df_m15, current_price, signal)
