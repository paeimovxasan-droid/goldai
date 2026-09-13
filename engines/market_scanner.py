"""
GoldAI Ultra — Multi-Market Signal Scanner v2
H1 trend filter + Swing-point SL + Multi-component scoring
Matematik analiz | Yangiliklar | Stakan | Whale | SMC | Liquidity
"""

import asyncio
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from core.config import config, MARKETS
from core.logger import logger
from engines.liquidity_engine import LiquidityEngine
from engines.smc_engine import SMCEngine
from engines.whale_monitor import WhaleMonitor
from engines.cluster_engine import ClusterEngine


@dataclass
class MarketSignal:
    symbol: str
    market_type: str
    signal: str           # BUY | SELL | NEUTRAL
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    rr_ratio: float
    liquidity_score: float
    smc_score: float
    whale_score: float
    technical_score: float
    total_score: float
    trend: str
    volatility: str
    timeframe: str
    reason: str
    timestamp: str = ""
    whale_activity: Optional[dict] = None
    h1_trend: str = "NEUTRAL"     # H1 yo'nalishi
    funding_score: float = 0.0    # Funding rate bonus
    ob_score: float = 0.0         # Order book imbalance score
    cluster_score: float = 0.0    # V3 cluster analiz balli
    poc: float = 0.0              # Volume Point of Control
    vah: float = 0.0              # Value Area High
    val: float = 0.0              # Value Area Low
    cluster_type: str = "NEUTRAL" # Cluster zona turi
    cvd_trend: str = "NEUTRAL"    # Cumulative Volume Delta trend


@dataclass
class ScanResult:
    best_signals: list[MarketSignal]
    total_scanned: int
    total_signals: int
    scan_time_ms: float
    market_overview: dict


class MultiMarketScanner:
    """Barcha bozorlarni parallel skanerlash — v2 kuchaytirilgan"""

    def __init__(self, market_data_engine=None):
        self.liquidity = LiquidityEngine()
        self.smc = SMCEngine()
        self.whale = WhaleMonitor()
        self.cluster = ClusterEngine()
        # H1 ma'lumotlarini aynan orchestratorning ulangan MT5 sessionidan olamiz.
        # Oldin bu yerda ikkinchi, ulanmagan engine yaratilgan edi.
        if market_data_engine is not None:
            self._mde = market_data_engine
        else:
            from engines.market_data import MultiMarketDataEngine
            self._mde = MultiMarketDataEngine()

    async def scan_all(self, market_data: dict, balance: float) -> ScanResult:
        """Barcha bozorlarni parallel tahlil qilish"""
        start_time = datetime.utcnow()
        signals = []

        tasks = [
            self._scan_symbol(symbol, df, balance)
            for symbol, df in market_data.items()
            if df is not None and len(df) > 50
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, MarketSignal) and result.signal != "NEUTRAL":
                signals.append(result)

        signals.sort(key=lambda x: x.confidence * x.rr_ratio, reverse=True)

        elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
        overview = self._market_overview(market_data, signals)

        logger.info(
            f"🔍 Skanerlash tugadi: "
            f"{len(market_data)} symbol | "
            f"{len(signals)} signal | "
            f"{elapsed:.0f}ms"
        )

        return ScanResult(
            best_signals=signals[:5],
            total_scanned=len(market_data),
            total_signals=len(signals),
            scan_time_ms=elapsed,
            market_overview=overview
        )

    async def _scan_symbol(self, symbol: str, df: pd.DataFrame, balance: float) -> Optional[MarketSignal]:
        """Bitta symbolni to'liq tahlil qilish"""
        try:
            market = MARKETS.get(symbol, {})
            market_type = market.get("type", "forex")

            current_price = df["close"].iloc[-1]
            atr = df["atr"].iloc[-1] if "atr" in df.columns else current_price * 0.01

            # ── 1. Texnik ko'rsatkichlar ──────────────────────────
            tech = self._technical_analysis(df)

            # ── 2. Liquidity tahlili ──────────────────────────────
            liq = self.liquidity.analyze(df)

            # ── 3. SMC tahlili ────────────────────────────────────
            smc = self.smc.analyze(df)

            # ── 4. Whale faolligi ─────────────────────────────────
            whale = await self.whale.analyze_whale_activity(symbol, df)

            # ── 5. Volatillik ─────────────────────────────────────
            volatility = self._classify_volatility(df)
            if volatility == "extreme":
                return None

            # ── 6. Volume divergence (matematik) ──────────────────
            vol_div = self._volume_divergence(df)

            # ── 7. Momentum (matematik) ───────────────────────────
            momentum = self._momentum_score(df)

            # ── 8. Order-book imbalance (stakan) ──────────────────
            ob_score = await self._orderbook_imbalance(symbol, current_price, market_type)

            # ── 8b. V3 Cluster analysis (volume profile + delta) ──
            # Avval yo'nalishni taxmin qilamiz (keyinroq cluster yo'nalish filtri)
            pre_signal = "BUY" if (
                tech.get("score", 0) + momentum + vol_div > 0
            ) else "SELL"
            cluster_res = await self.cluster.analyze_with_m5(symbol, df, current_price, pre_signal)
            cluster_sc = cluster_res.cluster_score  # -30 to +30

            # ── 9. H1 trend filter ────────────────────────────────
            h1_trend, h1_score = await self._h1_trend(symbol, market_type)

            # ── 10. Funding rate score ─────────────────────────────
            # (signal yo'nalishi keyin aniqlanadi — avval yo'nalishni bilmasak 0)
            # funding score keyinroq qo'shiladi

            # ── 11. Ballar birlashtirish ──────────────────────────
            tech_score   = tech.get("score", 0)
            liq_score    = liq.confidence  if liq.signal  != "NEUTRAL" else 0
            smc_score_v  = smc.confidence  if smc.signal  != "NEUTRAL" else 0
            whale_v      = whale.confidence if whale.direction != "NEUTRAL" else 0

            if liq.signal   == "SELL": liq_score  = -liq_score
            if smc.signal   == "SELL": smc_score_v= -smc_score_v
            if whale.direction == "SELL": whale_v = -whale_v

            # Og'irliklar (jami 100%):
            # Texnik 18% | Liquidity 12% | SMC 20% | Whale 12% | Momentum 8% | VolDiv 5% | OB 5% | H1 5% | Cluster 15%
            total = (
                tech_score   * 0.18 +
                liq_score    * 0.12 +
                smc_score_v  * 0.20 +
                whale_v      * 0.12 +
                momentum     * 0.08 +
                vol_div      * 0.05 +
                ob_score     * 0.05 +
                h1_score     * 0.05 +
                cluster_sc   * 0.15
            )

            confidence = min(95, abs(total) * 2.2)

            # Signal yo'nalishi — kuchliroq filtr (14 → kichik bozor shovqunindan tozaroq)
            if total >= 14:     signal = "BUY"
            elif total <= -14:  signal = "SELL"
            else:              return None

            # ── Cluster filter: kuchli qarama-qarshi signal → blok ─
            if signal == "BUY" and cluster_sc < -15:
                logger.debug(f"Cluster filter: {symbol} BUY blok (cluster={cluster_sc:.0f}, {cluster_res.reason})")
                return None
            if signal == "SELL" and cluster_sc > 15:
                logger.debug(f"Cluster filter: {symbol} SELL blok (cluster={cluster_sc:.0f}, {cluster_res.reason})")
                return None

            # ── H1 trend filter: qarama-qarshi signalni blok ──────
            if h1_trend != "NEUTRAL":
                if signal == "BUY"  and h1_trend == "DOWN":
                    logger.debug(f"H1 filter: {symbol} BUY blok (H1 DOWN)")
                    return None
                if signal == "SELL" and h1_trend == "UP":
                    logger.debug(f"H1 filter: {symbol} SELL blok (H1 UP)")
                    return None
                # H1 mos kelsa → qo'shimcha ishonch
                confidence = min(95, confidence * 1.10)

            # Min confidence tekshiruvi (oshirildi: 22%)
            if confidence < config.risk.min_confidence:
                return None

            # ── 12. Funding score (yo'nalish ma'lum bo'lgach) ─────
            funding_sc = 0.0
            if market_type == "crypto":
                funding_sc = await self._get_funding_score(symbol, signal)
                # Bloklash sharti: funding filter ichida hal qilinadi (orchestrator da)
                # Bu yerda faqat signal kuchiga qo'shamiz
                confidence = min(95, confidence + funding_sc * 0.3)

            # ── 13. ADX filter — trend kuchi tekshiruvi ──────────
            adx = self._calc_adx(df)
            if adx < 20:
                logger.debug(f"ADX filter: {symbol} skip (ADX={adx:.1f} < 20, bozor choppy)")
                return None

            # ── 14. Struktura asosida SL ──────────────────────────
            sl = self._swing_based_sl(df, signal, current_price, atr)
            sl_dist = abs(current_price - sl)

            # ── Maximal SL chegarasi: narxdan (katta zarar oldini olish) ──
            # Eslatma: dollar-risk allaqachon lot hisoblashda (risk_pct% balans)
            # boshqariladi — bu chegara faqat asossiz uzoq SL larni kesish uchun.
            # Ilgari 0.3% edi — bu 15-min kripto shamchasi uchun juda tor bo'lib,
            # oddiy tebranish (spread/noise) darhol SL ni urib, deyarli har bir
            # savdoni soniyalar ichida zararga yopib qo'yardi (win rate ~16%).
            max_sl_pct = 0.015   # 1.5% maksimal SL masofasi
            max_sl_dist = current_price * max_sl_pct
            if sl_dist > max_sl_dist:
                if signal == "BUY":
                    sl = current_price - max_sl_dist
                else:
                    sl = current_price + max_sl_dist
                sl_dist = max_sl_dist
                logger.debug(f"SL chegaralandi: {symbol} → 1.5% ({sl_dist:.5f})")

            # Minimal SL masofasi: kamida 0.5% (noise ichida qolmasin)
            min_sl_dist = current_price * 0.005
            if sl_dist < min_sl_dist:
                if signal == "BUY":
                    sl = current_price - min_sl_dist
                else:
                    sl = current_price + min_sl_dist
                sl_dist = min_sl_dist

            # TP: 2R sabit (tezkor foyda, kafolatlangan) — ADX ga qarab 2-3R
            if adx < 25:
                tp_mult = 2.0
            elif adx < 35:
                tp_mult = 2.5
            else:
                tp_mult = 3.0
            sl_dist = abs(current_price - sl)
            tp = current_price - sl_dist * tp_mult if signal == "SELL" else current_price + sl_dist * tp_mult
            rr = abs(tp - current_price) / max(abs(sl - current_price), 1e-10)

            reason_parts = [
                f"Tech:{tech_score:.0f}",
                f"Liq:{liq_score:.0f}",
                f"SMC:{smc_score_v:.0f}",
                f"Whl:{whale_v:.0f}",
                f"Mom:{momentum:.0f}",
                f"OB:{ob_score:.0f}",
                f"H1:{h1_trend}",
                f"Clust:{cluster_sc:.0f}({cluster_res.cluster_type})",
                f"CVD:{cluster_res.cvd_trend}",
                f"POC:{cluster_res.poc:.3f}",
            ]
            if funding_sc != 0:
                reason_parts.append(f"FR:{funding_sc:+.0f}")

            return MarketSignal(
                symbol=symbol,
                market_type=market_type,
                signal=signal,
                confidence=round(confidence, 1),
                entry=round(current_price, 5),
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                rr_ratio=round(rr, 2),
                liquidity_score=abs(liq_score),
                smc_score=abs(smc_score_v),
                whale_score=abs(whale_v),
                technical_score=abs(tech_score),
                total_score=round(total, 1),
                trend=smc.trend,
                volatility=volatility,
                timeframe="M15",
                reason=" | ".join(reason_parts),
                timestamp=datetime.utcnow().isoformat(),
                whale_activity={
                    "signal": whale.signal.value,
                    "direction": whale.direction,
                    "confidence": whale.confidence,
                    "institutional": whale.institutional_flow,
                    "description": whale.description
                },
                h1_trend=h1_trend,
                funding_score=funding_sc,
                ob_score=ob_score,
                cluster_score=cluster_sc,
                poc=cluster_res.poc,
                vah=cluster_res.vah,
                val=cluster_res.val,
                cluster_type=cluster_res.cluster_type,
                cvd_trend=cluster_res.cvd_trend,
            )

        except Exception as e:
            logger.debug(f"Scan xato ({symbol}): {e}")
            return None

    # ─── H1 TREND FILTER ──────────────────────────────────────────

    async def _h1_trend(self, symbol: str, market_type: str) -> tuple[str, float]:
        """
        H1 (soatlik) trend yo'nalishini aniqlash — Libertex MT5 uchun barcha instrumentlarda ishlaydi.
        Returns: (trend: "UP"|"DOWN"|"NEUTRAL", score: float)
        """
        try:
            # Libertex da barcha bozorlarda H1 trend tekshiramiz (Forex, Crypto, Stocks)
            # Faqat crypto emas, barcha uchun
            h1_df = await self._mde.get_ohlc_async(symbol, "H1", 60)
            if h1_df is None or len(h1_df) < 20:
                return "NEUTRAL", 0.0

            close = h1_df["close"].values
            # EMA 21 va EMA 50 hisoblash
            ema21 = self._ema(close, 21)
            ema50 = self._ema(close, 50)

            last_close = close[-1]
            last_e21   = ema21[-1]
            last_e50   = ema50[-1]

            # RSI H1
            rsi_h1 = float(h1_df["rsi"].iloc[-1]) if "rsi" in h1_df.columns else 50.0

            # Kuchli UP: narx EMA21 > EMA50 ustida, RSI > 50
            if last_close > last_e21 > last_e50 and rsi_h1 > 50:
                # Score: qanchalik EMA dan uzoq
                pct = (last_close - last_e21) / last_e21 * 100
                score = min(20.0, pct * 50)
                return "UP", score

            # Kuchli DOWN: narx EMA21 < EMA50 ostida, RSI < 50
            if last_close < last_e21 < last_e50 and rsi_h1 < 50:
                pct = (last_e21 - last_close) / last_e21 * 100
                score = min(20.0, pct * 50)
                return "DOWN", -score

            # Zaif trend: faqat EMA21 / EMA50 pozitsiyasiga qarab
            if last_close > last_e21 and last_e21 > last_e50:
                return "UP", 5.0
            if last_close < last_e21 and last_e21 < last_e50:
                return "DOWN", -5.0

            return "NEUTRAL", 0.0

        except Exception as e:
            logger.debug(f"H1 trend xato ({symbol}): {e}")
            return "NEUTRAL", 0.0

    @staticmethod
    def _ema(values: np.ndarray, period: int) -> np.ndarray:
        """Eksponentsial skользящая o'rtacha"""
        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(values, dtype=float)
        ema[0] = values[0]
        for i in range(1, len(values)):
            ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
        return ema

    @staticmethod
    def _calc_adx(df: pd.DataFrame, period: int = 14) -> float:
        """
        ADX (Average Directional Index) hisoblash.
        Trend kuchini o'lchaydi: <20 = choppy/range, >25 = trend.
        """
        try:
            n = len(df)
            if n < period + 5:
                return 25.0  # Ma'lumot yetarli emas — o'tkazib yuborish

            high  = df["high"].values.astype(float)
            low   = df["low"].values.astype(float)
            close = df["close"].values.astype(float)

            # True Range
            tr = np.zeros(n)
            dm_plus  = np.zeros(n)
            dm_minus = np.zeros(n)

            for i in range(1, n):
                h_diff = high[i] - high[i - 1]
                l_diff = low[i - 1] - low[i]
                tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
                dm_plus[i]  = h_diff if h_diff > l_diff and h_diff > 0 else 0
                dm_minus[i] = l_diff if l_diff > h_diff and l_diff > 0 else 0

            # Wilder's smoothing (period)
            def wilder(arr, p):
                s = np.zeros(n)
                s[p] = arr[1:p+1].sum()
                for i in range(p + 1, n):
                    s[i] = s[i-1] - s[i-1] / p + arr[i]
                return s

            atr14  = wilder(tr, period)
            dmp14  = wilder(dm_plus, period)
            dmm14  = wilder(dm_minus, period)

            with np.errstate(divide='ignore', invalid='ignore'):
                di_plus  = np.where(atr14 > 0, 100 * dmp14 / atr14, 0)
                di_minus = np.where(atr14 > 0, 100 * dmm14 / atr14, 0)
                di_sum   = di_plus + di_minus
                dx       = np.where(di_sum > 0, 100 * np.abs(di_plus - di_minus) / di_sum, 0)

            # ADX = EMA of DX
            adx_arr = np.zeros(n)
            adx_arr[2 * period] = dx[period:2*period+1].mean()
            for i in range(2 * period + 1, n):
                adx_arr[i] = (adx_arr[i-1] * (period - 1) + dx[i]) / period

            return float(adx_arr[-1])
        except Exception:
            return 25.0  # default — o'tkazib yuborish

    # ─── SWING-BASED SL ───────────────────────────────────────────

    def _swing_based_sl(self, df: pd.DataFrame, signal: str,
                         entry: float, atr: float) -> float:
        """
        Tebranish nuqtalariga asoslangan SL.
        SELL → so'nggi swing HIGH ustida
        BUY  → so'nggi swing LOW ostida

        Swing = kamida 3 shamdan yuqori/past nuqta.
        """
        highs = df["high"].values
        lows  = df["low"].values
        n = len(highs)

        if signal == "SELL":
            # So'nggi 30 shamda eng yaqin swing HIGH topish
            for i in range(n - 3, max(n - 31, 2), -1):
                if (highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and
                        highs[i] > highs[i + 1] and highs[i] > highs[i + 2]):
                    sl = highs[i] + atr * 0.4
                    # SL narxdan yuqori bo'lishi shart
                    if sl > entry:
                        return sl
            # Fallback: ATR 1.2x
            return entry + atr * 1.2

        else:  # BUY
            for i in range(n - 3, max(n - 31, 2), -1):
                if (lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and
                        lows[i] < lows[i + 1] and lows[i] < lows[i + 2]):
                    sl = lows[i] - atr * 0.4
                    if sl < entry:
                        return sl
            return entry - atr * 1.2

    # ─── TEXNIK TAHLIL ────────────────────────────────────────────

    def _technical_analysis(self, df: pd.DataFrame) -> dict:
        """Texnik ko'rsatkichlar — kengaytirilgan"""
        score = 0
        reasons = []
        close = df["close"].iloc[-1]

        # ── EMA trend ────────────────────────────────────────────
        if all(c in df.columns for c in ("ema20", "ema50", "ema200")):
            e20  = df["ema20"].iloc[-1]
            e50  = df["ema50"].iloc[-1]
            e200 = df["ema200"].iloc[-1]

            if close > e20 > e50 > e200:
                score += 25; reasons.append("EMA bull")
            elif close < e20 < e50 < e200:
                score -= 25; reasons.append("EMA bear")
            elif close > e50:
                score += 10
            elif close < e50:
                score -= 10

        # ── RSI ──────────────────────────────────────────────────
        if "rsi" in df.columns:
            rsi      = df["rsi"].iloc[-1]
            rsi_prev = df["rsi"].iloc[-2]

            if 28 <= rsi <= 42 and rsi > rsi_prev:
                score += 22; reasons.append(f"RSI bounce:{rsi:.0f}")
            elif 58 <= rsi <= 72 and rsi < rsi_prev:
                score -= 22; reasons.append(f"RSI drop:{rsi:.0f}")
            elif rsi < 25:
                score += 18; reasons.append(f"RSI OS:{rsi:.0f}")
            elif rsi > 75:
                score -= 18; reasons.append(f"RSI OB:{rsi:.0f}")

            # RSI divergence (matematik)
            score += self._rsi_divergence(df) * 0.5

        # ── MACD ─────────────────────────────────────────────────
        if "macd_hist" in df.columns:
            hist      = df["macd_hist"].iloc[-1]
            hist_prev = df["macd_hist"].iloc[-3]
            hist_pp   = df["macd_hist"].iloc[-5]

            if hist > 0 and hist > hist_prev > hist_pp:
                score += 15; reasons.append("MACD bull")
            elif hist < 0 and hist < hist_prev < hist_pp:
                score -= 15; reasons.append("MACD bear")
            elif hist > 0 and hist > hist_prev:
                score += 7
            elif hist < 0 and hist < hist_prev:
                score -= 7

        # ── Stochastic ───────────────────────────────────────────
        if "stoch_k" in df.columns:
            k = df["stoch_k"].iloc[-1]
            d = df["stoch_d"].iloc[-1]

            if k < 20 and k > d:
                score += 15; reasons.append(f"Stoch OS:{k:.0f}")
            elif k > 80 and k < d:
                score -= 15; reasons.append(f"Stoch OB:{k:.0f}")

        # ── Bollinger Band ────────────────────────────────────────
        if "bb_pct" in df.columns:
            bb = df["bb_pct"].iloc[-1]
            if bb < 0.08:
                score += 12; reasons.append("BB OS")
            elif bb > 0.92:
                score -= 12; reasons.append("BB OB")

        # ── Volume confirmation ───────────────────────────────────
        if "volume_ratio" in df.columns:
            vr = df["volume_ratio"].iloc[-1]
            if vr > 1.8:
                score += 10 if score > 0 else -10
                reasons.append(f"Vol:{vr:.1f}x")

        # ── Price Action: Pin bar, engulfing ──────────────────────
        pa_score = self._price_action(df)
        if abs(pa_score) > 0:
            score += pa_score
            reasons.append(f"PA:{pa_score:+.0f}")

        return {"score": score, "reasons": reasons}

    def _rsi_divergence(self, df: pd.DataFrame) -> float:
        """
        RSI divergence matematik aniqlash.
        Narx pastga ketayotgan, RSI yuqoriga (bullish div) → +score
        Narx yuqoriga, RSI pastga (bearish div) → -score
        """
        if "rsi" not in df.columns or len(df) < 10:
            return 0.0
        try:
            closes = df["close"].values[-10:]
            rsis   = df["rsi"].values[-10:]
            price_dir = closes[-1] - closes[-5]
            rsi_dir   = rsis[-1]  - rsis[-5]

            if price_dir < 0 and rsi_dir > 2:   # Bullish divergence
                return 15.0
            if price_dir > 0 and rsi_dir < -2:  # Bearish divergence
                return -15.0
        except Exception:
            pass
        return 0.0

    def _price_action(self, df: pd.DataFrame) -> float:
        """Pin bar va engulfing shamlar (price action matematik)"""
        try:
            last   = df.iloc[-1]
            prev   = df.iloc[-2]
            o, h, l, c = last["open"], last["high"], last["low"], last["close"]
            body   = abs(c - o)
            candle = h - l
            if candle < 1e-10:
                return 0.0
            wick_ratio = body / candle

            # Bullish pin bar: kichik body, uzun pastki soya
            lower_wick = min(o, c) - l
            upper_wick = h - max(o, c)
            if lower_wick > body * 2 and upper_wick < body * 0.5 and wick_ratio < 0.4:
                return 12.0  # Bullish pin

            # Bearish pin bar
            if upper_wick > body * 2 and lower_wick < body * 0.5 and wick_ratio < 0.4:
                return -12.0  # Bearish pin

            # Bullish engulfing
            p_o, p_c = prev["open"], prev["close"]
            if p_c < p_o and c > o and c > p_o and o < p_c:
                return 10.0

            # Bearish engulfing
            if p_c > p_o and c < o and c < p_o and o > p_c:
                return -10.0

        except Exception:
            pass
        return 0.0

    # ─── VOLUME DIVERGENCE ────────────────────────────────────────

    def _volume_divergence(self, df: pd.DataFrame) -> float:
        """
        Hajm divergence: narx pastga ketayotganda hajm oshsa → bullish pressure.
        Narx yuqoriga ketayotganda hajm kamaysa → signal kuchsiz.
        """
        if "volume" not in df.columns or len(df) < 10:
            return 0.0
        try:
            closes  = df["close"].values[-10:]
            volumes = df["volume"].values[-10:]

            price_change  = (closes[-1] - closes[-5]) / max(closes[-5], 1e-10)
            volume_change = (volumes[-3:].mean() - volumes[-8:-3].mean()) / max(volumes[-8:-3].mean(), 1e-10)

            # Narx pastga, hajm yuqoriga → kuchli bullish divergence
            if price_change < -0.005 and volume_change > 0.2:
                return 15.0
            # Narx yuqoriga, hajm pastga → bearish divergence
            if price_change > 0.005 and volume_change < -0.2:
                return -15.0
            # Narx yuqoriga, hajm yuqoriga → kuchli bullish momentum
            if price_change > 0.005 and volume_change > 0.2:
                return 10.0
            # Narx pastga, hajm pastga → zaif harakat
            if price_change < -0.005 and volume_change < -0.2:
                return -8.0
        except Exception:
            pass
        return 0.0

    # ─── MOMENTUM SCORE ───────────────────────────────────────────

    def _momentum_score(self, df: pd.DataFrame) -> float:
        """
        Matematik momentum: Rate of Change (ROC) + ATR normalizatsiya.
        Qanchalik tez harakatlanayotganini o'lchaydi.
        """
        if len(df) < 14:
            return 0.0
        try:
            closes = df["close"].values
            atr = df["atr"].values[-1] if "atr" in df.columns else closes[-1] * 0.01

            # 5-sham ROC (%)
            roc5 = (closes[-1] - closes[-6]) / max(closes[-6], 1e-10) * 100
            # 10-sham ROC (%)
            roc10 = (closes[-1] - closes[-11]) / max(closes[-11], 1e-10) * 100

            # Normalizatsiya: ATR ga nisbatan
            norm = atr / max(closes[-1], 1e-10) * 100
            if norm < 1e-5:
                return 0.0

            score = (roc5 * 0.6 + roc10 * 0.4) / norm * 5
            return float(np.clip(score, -20, 20))
        except Exception:
            pass
        return 0.0

    # ─── ORDER BOOK IMBALANCE (STAKAN) ────────────────────────────

    async def _orderbook_imbalance(self, symbol: str, price: float,
                                   market_type: str) -> float:
        """
        Order book imbalance — faqat Binance yoqilgan va crypto bo'lsa.
        Libertex rejimida 0 qaytaradi (MT5 da order book yo'q, lekin cluster bilan qoplanadi)
        """
        if not config.enable_binance:
            return 0.0  # Libertex — order book MT5 da yo'q
        if market_type != "crypto":
            return 0.0
        try:
            from engines.binance_executor import SYMBOL_MAP
            import aiohttp
            bn_sym = SYMBOL_MAP.get(symbol)
            if not bn_sym:
                return 0.0
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={bn_sym}&limit=20"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status != 200:
                        return 0.0
                    d = await r.json()
            bids = d.get("bids", [])[:10]
            asks = d.get("asks", [])[:10]
            bid_vol = sum(float(b[1]) for b in bids)
            ask_vol = sum(float(a[1]) for a in asks)
            total   = bid_vol + ask_vol
            if total < 1e-10:
                return 0.0
            imbalance = (bid_vol - ask_vol) / total
            return float(np.clip(imbalance * 25, -15, 15))
        except Exception:
            return 0.0

    # ─── FUNDING SCORE ────────────────────────────────────────────

    async def _get_funding_score(self, symbol: str, signal: str) -> float:
        """Funding rate — faqat Binance yoqilganda, Libertex da 0"""
        if not config.enable_binance:
            return 0.0
        try:
            from engines.binance_executor import SYMBOL_MAP
            import aiohttp
            bn_sym = SYMBOL_MAP.get(symbol)
            if not bn_sym:
                return 0.0
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={bn_sym}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=3)) as r:
                    if r.status != 200:
                        return 0.0
                    d = await r.json()
                    rate = float(d.get("lastFundingRate", 0))
            if signal == "SELL":
                if rate > 0.0008:  return 15.0
                if rate > 0.0003:  return 7.0
                if rate < -0.0001: return -8.0
            elif signal == "BUY":
                if rate < -0.0004: return 15.0
                if rate < -0.0001: return 7.0
                if rate > 0.001:   return -8.0
        except Exception:
            pass
        return 0.0

    # ─── VOLATILLIK ───────────────────────────────────────────────

    def _classify_volatility(self, df: pd.DataFrame) -> str:
        if "atr_pct" not in df.columns:
            return "normal"
        atr_pct = df["atr_pct"].iloc[-1]
        avg_atr  = df["atr_pct"].mean()
        ratio    = atr_pct / (avg_atr + 1e-10)

        if ratio > 3.5:   return "extreme"
        elif ratio > 2.0: return "high"
        elif ratio < 0.5: return "low"
        return "normal"

    # ─── MARKET OVERVIEW ──────────────────────────────────────────

    def _market_overview(self, market_data: dict, signals: list) -> dict:
        buy_signals  = [s for s in signals if s.signal == "BUY"]
        sell_signals = [s for s in signals if s.signal == "SELL"]

        by_type = {}
        for s in signals:
            t = s.market_type
            by_type.setdefault(t, {"BUY": 0, "SELL": 0})
            by_type[t][s.signal] = by_type[t].get(s.signal, 0) + 1

        if len(buy_signals) > len(sell_signals) * 1.5:
            sentiment = "RISK_ON"
        elif len(sell_signals) > len(buy_signals) * 1.5:
            sentiment = "RISK_OFF"
        else:
            sentiment = "MIXED"

        return {
            "total_buy":       len(buy_signals),
            "total_sell":      len(sell_signals),
            "sentiment":       sentiment,
            "by_market_type":  by_type,
            "best_opportunity": signals[0].symbol if signals else None,
            "markets_scanned": len(market_data),
        }
