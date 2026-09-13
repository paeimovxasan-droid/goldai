"""
GoldAI Ultra — Whale & Institutional Flow Monitor
Katta o'yinchilarni kuzatish: Kit harakatini aniqlash
"""

import asyncio
import aiohttp
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

from core.config import config
from core.logger import logger


class WhaleSignal(Enum):
    ACCUMULATION = "ACCUMULATION"    # Yig'ish — yuqoriga harakat
    DISTRIBUTION = "DISTRIBUTION"   # Tarqatish — pastga harakat
    STOP_HUNT = "STOP_HUNT"          # Stop ovlash
    LIQUIDITY_GRAB = "LIQ_GRAB"      # Likvidlik olish
    NEUTRAL = "NEUTRAL"


@dataclass
class WhaleActivity:
    symbol: str
    signal: WhaleSignal
    direction: str              # BUY | SELL | NEUTRAL
    confidence: float           # 0–100
    volume_spike: float         # O'rtachaga nisbatan
    price_impact: float         # Narxga ta'sir %
    order_size_usd: float       # USD'dagi hajm
    exchange: str               # binance | coinbase | bybit | mt5
    description: str
    timestamp: str = ""
    key_level: float = 0.0
    institutional_flow: bool = False


@dataclass
class OrderFlowData:
    symbol: str
    timeframe: str
    delta: float                # Buy volume - Sell volume
    cumulative_delta: float
    buy_volume: float
    sell_volume: float
    imbalance_pct: float        # |buy-sell| / total
    large_orders: list = field(default_factory=list)


class WhaleMonitor:
    """
    Kit harakatini kuzatish:
    1. Binance WebSocket — real-time large trades
    2. Order flow imbalance
    3. Volume spike detection
    4. Dark pool flow (CVD tahlili)
    5. Open Interest o'zgarishi (futures)
    6. Liquidation clusters
    """

    BINANCE_WS = "wss://stream.binance.com:9443/ws"
    BINANCE_API = "https://api.binance.com/api/v3"
    BINANCE_FUTURES = "https://fapi.binance.com/fapi/v1"

    def __init__(self):
        self._whale_cache: dict[str, list[WhaleActivity]] = {}
        self._order_flow: dict[str, OrderFlowData] = {}
        self._large_trades: dict[str, list] = {}
        self._open_interest: dict[str, float] = {}
        self._oi_history: dict[str, list] = {}
        self._liquidations: dict[str, list] = {}
        self._running = False

    # ─── ASOSIY TAHLIL ────────────────────────────────────────

    async def analyze_whale_activity(self, symbol: str, df: pd.DataFrame) -> WhaleActivity:
        """Symbol bo'yicha whale faoliyatini tahlil qilish — Libertex da MT5 volume + Binance faqat enable_binance da"""

        tasks = [
            self._analyze_volume_profile(symbol, df),
            self._detect_order_imbalance(symbol, df),
            self._check_vwap_deviation(symbol, df),
        ]

        # Crypto uchun qo'shimcha — faqat Binance yoqilganda (Libertex da MT5 yetarli)
        if config.enable_binance and self._is_crypto(symbol):
            tasks.append(self._get_open_interest_change(symbol))
            tasks.append(self._get_large_trades(symbol))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return self._synthesize_whale_signal(symbol, df, results)

    async def _analyze_volume_profile(self, symbol: str, df: pd.DataFrame) -> dict:
        """Volume Profile tahlili — qayerda ko'p hajm bor"""
        if len(df) < 20:
            return {"spike": 1.0, "above_avg": False}

        volumes = df["volume"].values
        avg_vol = np.mean(volumes[-20:])
        current_vol = volumes[-1]
        spike = current_vol / (avg_vol + 1e-10)

        # Volume clustering
        price_vol = {}
        price_range = df["high"].max() - df["low"].min()
        bucket_size = price_range / 20

        for _, row in df.tail(50).iterrows():
            bucket = round(row["close"] / bucket_size) * bucket_size
            price_vol[bucket] = price_vol.get(bucket, 0) + row["volume"]

        # Eng ko'p hajm to'plangan narx
        if price_vol:
            poc = max(price_vol, key=price_vol.get)
        else:
            poc = df["close"].iloc[-1]

        return {
            "spike": round(spike, 2),
            "above_avg": spike > 2.5,
            "poc": poc,                          # Point of Control
            "avg_volume": avg_vol,
            "current_volume": current_vol,
        }

    async def _detect_order_imbalance(self, symbol: str, df: pd.DataFrame) -> dict:
        """Taker buy/sell imbalance — kimlar aggressiv"""
        if len(df) < 5:
            return {"delta": 0, "bias": "NEUTRAL"}

        # Har bir bar uchun buying/selling pressure
        deltas = []
        for _, row in df.tail(20).iterrows():
            body = row["close"] - row["open"]
            total = row["high"] - row["low"] + 1e-10

            # Bullish bar → buy pressure
            if row["close"] > row["open"]:
                buy_vol = row["volume"] * (0.5 + abs(body) / total * 0.5)
                sell_vol = row["volume"] - buy_vol
            else:
                sell_vol = row["volume"] * (0.5 + abs(body) / total * 0.5)
                buy_vol = row["volume"] - sell_vol

            deltas.append(buy_vol - sell_vol)

        cumulative_delta = sum(deltas)
        recent_delta = sum(deltas[-5:])
        total_vol = df["volume"].tail(20).sum()

        imbalance = abs(recent_delta) / (total_vol + 1e-10) * 100

        bias = "BUY" if cumulative_delta > 0 else "SELL" if cumulative_delta < 0 else "NEUTRAL"

        flow = OrderFlowData(
            symbol=symbol,
            timeframe="M15",
            delta=recent_delta,
            cumulative_delta=cumulative_delta,
            buy_volume=sum(d for d in deltas if d > 0),
            sell_volume=abs(sum(d for d in deltas if d < 0)),
            imbalance_pct=imbalance
        )
        self._order_flow[symbol] = flow

        return {
            "delta": cumulative_delta,
            "recent_delta": recent_delta,
            "imbalance_pct": imbalance,
            "bias": bias
        }

    async def _check_vwap_deviation(self, symbol: str, df: pd.DataFrame) -> dict:
        """VWAP dan og'ish — institutional benchmark"""
        if len(df) < 10:
            return {"deviation": 0, "above_vwap": True}

        typical = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical * df["volume"]).sum() / df["volume"].sum()
        current = df["close"].iloc[-1]
        deviation = (current - vwap) / vwap * 100

        return {
            "vwap": round(vwap, 5),
            "deviation": round(deviation, 3),
            "above_vwap": current > vwap,
            "far_from_vwap": abs(deviation) > 0.5
        }

    async def _get_open_interest_change(self, symbol: str) -> dict:
        """Futures Open Interest o'zgarishi — Libertex da 0 (Binance faqat enable_binance da)"""
        if not config.enable_binance:
            return {"open_interest": 0, "oi_change_pct": 0, "oi_rising": False, "oi_falling": False}
        # Binance futures symbol formatting
        futures_symbol = symbol.replace("USD", "USDT")

        try:
            url = f"{self.BINANCE_FUTURES}/openInterest?symbol={futures_symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        oi = float(data.get("openInterest", 0))

                        # O'zgarish hisoblash
                        prev_oi = self._open_interest.get(symbol, oi)
                        oi_change_pct = (oi - prev_oi) / (prev_oi + 1e-10) * 100
                        self._open_interest[symbol] = oi

                        # OI history
                        hist = self._oi_history.get(symbol, [])
                        hist.append({"oi": oi, "time": datetime.utcnow().isoformat()})
                        self._oi_history[symbol] = hist[-100:]

                        return {
                            "open_interest": oi,
                            "oi_change_pct": round(oi_change_pct, 3),
                            "oi_rising": oi_change_pct > 0.5,
                            "oi_falling": oi_change_pct < -0.5
                        }
        except Exception as e:
            logger.debug(f"OI fetch xato ({symbol}): {e}")

        return {"open_interest": 0, "oi_change_pct": 0, "oi_rising": False, "oi_falling": False}

    async def _get_large_trades(self, symbol: str) -> dict:
        """Katta savdolarni aniqlash — Libertex da bo'sh (Binance faqat enable_binance da)"""
        if not config.enable_binance:
            return {"large_trades_count": 0, "whale_buy_pct": 0, "whale_sell_pct": 0, "largest_trade_usd": 0, "institutional_bias": "NEUTRAL"}
        futures_symbol = symbol.replace("USD", "USDT")
        large_trades = []

        try:
            url = f"{self.BINANCE_API}/trades?symbol={futures_symbol}&limit=500"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        trades = await resp.json()

                        quantities = [float(t["qty"]) for t in trades]
                        avg_qty = np.mean(quantities)
                        threshold = avg_qty * 10  # O'rtachadan 10x katta

                        for t in trades:
                            qty = float(t["qty"])
                            price = float(t["price"])
                            usd_value = qty * price

                            if qty > threshold:
                                large_trades.append({
                                    "side": "BUY" if t.get("isBuyerMaker", False) is False else "SELL",
                                    "qty": qty,
                                    "price": price,
                                    "usd_value": usd_value,
                                    "time": t["time"]
                                })

                        self._large_trades[symbol] = large_trades
        except Exception as e:
            logger.debug(f"Large trades xato ({symbol}): {e}")

        buy_volume = sum(t["usd_value"] for t in large_trades if t["side"] == "BUY")
        sell_volume = sum(t["usd_value"] for t in large_trades if t["side"] == "SELL")
        total = buy_volume + sell_volume + 1e-10

        return {
            "large_trades_count": len(large_trades),
            "whale_buy_pct": buy_volume / total * 100,
            "whale_sell_pct": sell_volume / total * 100,
            "largest_trade_usd": max((t["usd_value"] for t in large_trades), default=0),
            "institutional_bias": "BUY" if buy_volume > sell_volume * 1.3 else
                                  "SELL" if sell_volume > buy_volume * 1.3 else "NEUTRAL"
        }

    def _synthesize_whale_signal(self, symbol: str, df: pd.DataFrame, results: list) -> WhaleActivity:
        """Barcha ma'lumotlarni birlashtirish"""

        volume_data = results[0] if not isinstance(results[0], Exception) else {}
        flow_data = results[1] if not isinstance(results[1], Exception) else {}
        vwap_data = results[2] if not isinstance(results[2], Exception) else {}
        oi_data = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else {}
        large_trades = results[4] if len(results) > 4 and not isinstance(results[4], Exception) else {}

        score = 0
        reasons = []
        institutional = False

        # Volume spike
        spike = volume_data.get("spike", 1.0)
        if spike > 3.0:
            reasons.append(f"Hajm anomaliya: {spike:.1f}x")
            institutional = True

        # Order flow
        flow_bias = flow_data.get("bias", "NEUTRAL")
        imbalance = flow_data.get("imbalance_pct", 0)
        if flow_bias == "BUY" and imbalance > 30:
            score += imbalance * 0.5
            reasons.append(f"Buy imbalance: {imbalance:.1f}%")
        elif flow_bias == "SELL" and imbalance > 30:
            score -= imbalance * 0.5
            reasons.append(f"Sell imbalance: {imbalance:.1f}%")

        # VWAP
        if vwap_data.get("far_from_vwap"):
            dev = vwap_data.get("deviation", 0)
            if dev > 0:
                score -= 15  # VWAP ga qaytish ehtimoli (mean reversion)
                reasons.append(f"VWAP ustida: +{dev:.2f}%")
            else:
                score += 15
                reasons.append(f"VWAP ostida: {dev:.2f}%")

        # Open Interest
        if oi_data.get("oi_rising") and flow_bias == "BUY":
            score += 20
            reasons.append("OI o'sishi + Buy flow = Bullish trend")
            institutional = True
        elif oi_data.get("oi_falling") and flow_bias == "SELL":
            score -= 20
            reasons.append("OI pasayishi + Sell flow = Bearish")

        # Large trades (whale)
        whale_bias = large_trades.get("institutional_bias", "NEUTRAL")
        if whale_bias == "BUY":
            score += 25
            reasons.append(f"Kit BUY: {large_trades.get('whale_buy_pct', 0):.0f}%")
            institutional = True
        elif whale_bias == "SELL":
            score -= 25
            reasons.append(f"Kit SELL: {large_trades.get('whale_sell_pct', 0):.0f}%")
            institutional = True

        # Signal aniqlash
        confidence = min(95, abs(score))
        current = df["close"].iloc[-1] if len(df) > 0 else 0

        if score >= 30:
            signal = WhaleSignal.ACCUMULATION
            direction = "BUY"
        elif score <= -30:
            signal = WhaleSignal.DISTRIBUTION
            direction = "SELL"
        elif spike > 5.0:
            signal = WhaleSignal.STOP_HUNT
            direction = "NEUTRAL"
        else:
            signal = WhaleSignal.NEUTRAL
            direction = "NEUTRAL"

        activity = WhaleActivity(
            symbol=symbol,
            signal=signal,
            direction=direction,
            confidence=round(confidence, 1),
            volume_spike=spike,
            price_impact=abs(vwap_data.get("deviation", 0)),
            order_size_usd=large_trades.get("largest_trade_usd", 0),
            exchange="mt5" if not config.enable_binance else ("binance" if self._is_crypto(symbol) else "mt5"),
            description=" | ".join(reasons[:4]),
            timestamp=datetime.utcnow().isoformat(),
            key_level=volume_data.get("poc", current),
            institutional_flow=institutional
        )

        if activity.signal != WhaleSignal.NEUTRAL:
            logger.info(
                f"🐋 WHALE [{symbol}]: {signal.value} | "
                f"Direction: {direction} | "
                f"Confidence: {confidence:.1f}% | "
                f"{'🏛️ Institutional' if institutional else ''}"
            )

        cache = self._whale_cache.get(symbol, [])
        cache.append(activity)
        self._whale_cache[symbol] = cache[-50:]

        return activity

    async def monitor_liquidations(self, symbol: str) -> dict:
        """Liquidation cluster — Libertex da bo'sh (Binance faqat enable_binance da)"""
        if not config.enable_binance:
            return {"total_liq_usd": 0, "long_liq": 0, "short_liq": 0, "danger": False}
        futures_symbol = symbol.replace("USD", "USDT")
        liq_data = {"total_liq_usd": 0, "long_liq": 0, "short_liq": 0, "danger": False}

        try:
            # Binance liquidation heatmap (taxminiy)
            url = f"{self.BINANCE_FUTURES}/allForceOrders?symbol={futures_symbol}&limit=100"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        orders = await resp.json()

                        long_liq = sum(float(o.get("origQty", 0)) * float(o.get("price", 0))
                                      for o in orders if o.get("side") == "SELL")
                        short_liq = sum(float(o.get("origQty", 0)) * float(o.get("price", 0))
                                       for o in orders if o.get("side") == "BUY")
                        total = long_liq + short_liq

                        liq_data = {
                            "total_liq_usd": total,
                            "long_liq_usd": long_liq,
                            "short_liq_usd": short_liq,
                            "liq_bias": "SELL" if long_liq > short_liq * 1.5 else
                                        "BUY" if short_liq > long_liq * 1.5 else "NEUTRAL",
                            "danger": total > 10_000_000  # $10M+ likvidatsiya xavfli
                        }
        except Exception as e:
            logger.debug(f"Liquidation fetch xato: {e}")

        return liq_data

    def _is_crypto(self, symbol: str) -> bool:
        from core.config import config
        return config.markets.get(symbol, {}).get("type") == "crypto"

    def get_whale_summary(self, symbol: str) -> dict:
        """Oxirgi whale faoliyati xulosasi"""
        activities = self._whale_cache.get(symbol, [])
        if not activities:
            return {"signal": "NEUTRAL", "confidence": 0}

        recent = activities[-5:]
        buy_count = sum(1 for a in recent if a.direction == "BUY")
        sell_count = sum(1 for a in recent if a.direction == "SELL")

        dominant = "BUY" if buy_count > sell_count else "SELL" if sell_count > buy_count else "NEUTRAL"
        avg_confidence = np.mean([a.confidence for a in recent])

        return {
            "signal": dominant,
            "confidence": round(avg_confidence, 1),
            "institutional": any(a.institutional_flow for a in recent),
            "volume_spike": max(a.volume_spike for a in recent),
            "last_activity": recent[-1].description if recent else ""
        }

    def get_order_flow(self, symbol: str) -> Optional[OrderFlowData]:
        return self._order_flow.get(symbol)

    async def start_ws_monitoring(self, symbols: list, callback):
        """WebSocket orqali real-time monitoring — Libertex da o'chiq (Binance faqat enable_binance da)"""
        if not config.enable_binance:
            logger.info("🐋 Whale WS o'chiq — Libertex rejimida MT5 ma'lumotlari ishlatiladi")
            return
        if not symbols:
            return

        # Faqat crypto symbollar uchun
        crypto_symbols = [s for s in symbols if self._is_crypto(s)]
        if not crypto_symbols:
            return

        streams = "/".join([f"{s.lower().replace('usd', 'usdt')}@aggTrade"
                           for s in crypto_symbols[:5]])
        ws_url = f"{self.BINANCE_WS}/{streams}"

        logger.info(f"🐋 Whale WS monitoring boshlandi: {crypto_symbols}")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(ws_url) as ws:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            await self._process_ws_trade(data, callback)
            except Exception as e:
                logger.error(f"Whale WS xato: {e}")

    async def _process_ws_trade(self, data: dict, callback):
        """WebSocket savdosini tahlil qilish"""
        try:
            symbol_raw = data.get("s", "")
            symbol = symbol_raw.replace("USDT", "USD")
            qty = float(data.get("q", 0))
            price = float(data.get("p", 0))
            usd_value = qty * price
            is_buyer_maker = data.get("m", False)

            # $100,000+ savdolar = whale
            if usd_value >= 100_000:
                side = "SELL" if is_buyer_maker else "BUY"
                logger.info(
                    f"🐋 WHALE TRADE! {symbol} | {side} | "
                    f"${usd_value:,.0f} | Price: {price}"
                )
                await callback({
                    "type": "whale_trade",
                    "symbol": symbol,
                    "side": side,
                    "usd_value": usd_value,
                    "price": price,
                    "timestamp": datetime.utcnow().isoformat()
                })
        except Exception as e:
            logger.debug(f"WS process xato: {e}")
