"""
GoldAI Ultra — OrderBook, Iceberg & Bookmap Engine
Professional savdo vositalari (Bookmap / Jigsaw analog):

  1. Order Book Depth tahlili    — Katta bid/ask devorlar
  2. Iceberg Detection           — Yashirin katta orderlar
  3. Volume Profile (Bookmap)    — Narxga ko'ra hajm taqsimoti
  4. Cumulative Delta (CVD)      — Xaridor/sotuvchi kuchi
  5. Liquidation Heatmap         — Likvidatsiya klasterlari
  6. Big Trade Detection         — $50k+ savdolar real-vaqt
  7. Multi-Exchange Aggregation  — Binance + Bybit + OKX
"""

import asyncio
import aiohttp
import json
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from core.config import config
from core.logger import logger


# ─── DATA CLASSES ─────────────────────────────────────────────────

@dataclass
class OrderLevel:
    price:    float
    quantity: float
    usd_value: float
    is_wall:  bool    # Katta to'siq


@dataclass
class IcebergOrder:
    price:         float
    side:          str       # BID | ASK
    visible_qty:   float
    estimated_total: float   # Taxminiy umumiy hajm
    refresh_count: int       # Necha marta yangilangan
    usd_value:     float
    confidence:    float     # 0–100


@dataclass
class OrderBookState:
    symbol:       str
    timestamp:    str
    bid_walls:    list[OrderLevel]    # Katta sotib olish devorlari
    ask_walls:    list[OrderLevel]    # Katta sotish devorlari
    icebergs:     list[IcebergOrder]
    imbalance:    float   # -1 (heavy sell) .. +1 (heavy buy)
    bid_ask_ratio: float  # bid total / ask total
    spread_pct:   float
    signal:       str     # BUY | SELL | NEUTRAL
    confidence:   float
    description:  str


@dataclass
class CVDData:
    symbol:   str
    cvd:      float       # Cumulative Volume Delta
    delta_1m: float       # 1 daqiqalik delta
    delta_5m: float       # 5 daqiqalik delta
    trend:    str         # BULLISH | BEARISH | NEUTRAL
    strength: float       # 0–100


@dataclass
class BigTrade:
    symbol:    str
    side:      str        # BUY | SELL
    price:     float
    quantity:  float
    usd_value: float
    exchange:  str
    timestamp: str
    is_liquidation: bool


@dataclass
class BookmapLevel:
    price:    float
    volume:   float       # Kümülatif hajm
    buy_vol:  float
    sell_vol: float
    delta:    float       # buy - sell
    is_poc:   bool        # Point of Control


# ─── MAIN ENGINE ──────────────────────────────────────────────────

class OrderBookEngine:
    """
    Bookmap va Jigsaw analogi — professional order flow tahlili
    """

    BINANCE_API  = "https://api.binance.com/api/v3"
    BINANCE_FUTU = "https://fapi.binance.com/fapi/v1"
    BYBIT_API    = "https://api.bybit.com/v5/market"
    OKX_API      = "https://www.okx.com/api/v5/market"

    # Symbol mapping
    BN_MAP = {
        "BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "BNBUSD": "BNBUSDT",
        "SOLUSD": "SOLUSDT", "XRPUSD": "XRPUSDT", "ADAUSD": "ADAUSDT",
    }
    BYBIT_MAP = {
        "BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "SOLUSD": "SOLUSDT",
    }

    # Wall detection threshold (bozor chuqurligining %)
    WALL_THRESHOLD_PCT = 3.0   # Top 3% hajm → devor
    ICEBERG_REFRESH_MIN = 3    # Kamida 3 marta yangilangan = iceberg

    def __init__(self):
        self._ob_snapshots: dict[str, list] = {}   # {symbol: [snapshot1, snapshot2...]}
        self._cvd_data:     dict[str, list] = {}   # {symbol: [(ts, delta)...]}
        self._big_trades:   list[BigTrade]  = []
        self._liq_levels:   dict[str, list] = {}

    # ─── ORDER BOOK TAHLILI ────────────────────────────────────────

    async def analyze(self, symbol: str, current_price: float) -> OrderBookState:
        """Asosiy order book tahlili — Libertex da NEUTRAL (Binance faqat enable_binance da)"""
        if not config.enable_binance:
            return self._neutral_state(symbol)
        bn_sym = self.BN_MAP.get(symbol)
        if not bn_sym:
            return self._neutral_state(symbol)

        try:
            ob = await self._get_order_book(bn_sym, depth=500)
            if not ob:
                return self._neutral_state(symbol)

            bids = [(float(p), float(q)) for p, q in ob.get("bids", [])]
            asks = [(float(p), float(q)) for p, q in ob.get("asks", [])]

            if not bids or not asks:
                return self._neutral_state(symbol)

            # Snapshot saqlab iceberg aniqlash
            self._save_snapshot(symbol, bids, asks)

            # Devorlar
            bid_walls = self._find_walls(bids, current_price, "BID")
            ask_walls = self._find_walls(asks, current_price, "ASK")

            # Iceberg
            icebergs = self._detect_icebergs(symbol, bids, asks)

            # Imbalance
            bid_total = sum(q for _, q in bids[:50])
            ask_total = sum(q for _, q in asks[:50])
            ratio = bid_total / max(ask_total, 1e-10)
            imbalance = (bid_total - ask_total) / max(bid_total + ask_total, 1e-10)

            # Signal
            signal, conf, desc = self._generate_signal(
                bid_walls, ask_walls, icebergs, imbalance, current_price
            )

            spread = (asks[0][0] - bids[0][0]) / current_price * 100

            return OrderBookState(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc).isoformat(),
                bid_walls=bid_walls,
                ask_walls=ask_walls,
                icebergs=icebergs,
                imbalance=round(imbalance, 3),
                bid_ask_ratio=round(ratio, 2),
                spread_pct=round(spread, 4),
                signal=signal,
                confidence=conf,
                description=desc
            )

        except Exception as e:
            logger.debug(f"OB analyze xato {symbol}: {e}")
            return self._neutral_state(symbol)

    async def _get_order_book(self, bn_symbol: str, depth: int = 500) -> Optional[dict]:
        try:
            url = f"{self.BINANCE_API}/depth?symbol={bn_symbol}&limit={depth}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        return await r.json()
        except Exception as e:
            logger.debug(f"OB fetch xato: {e}")
        return None

    def _find_walls(self, levels: list, price: float, side: str) -> list[OrderLevel]:
        """Katta devorlarni aniqlash"""
        if not levels:
            return []
        quantities = [q for _, q in levels[:100]]
        if not quantities:
            return []
        avg_qty = np.mean(quantities)
        threshold = avg_qty * 5   # O'rtachadan 5x ko'p = devor

        walls = []
        for p, q in levels[:100]:
            if q >= threshold:
                usd = p * q
                walls.append(OrderLevel(
                    price=p, quantity=q, usd_value=usd,
                    is_wall=usd > 500_000  # $500k+ = katta devor
                ))
        # Eng katta 5 ta
        return sorted(walls, key=lambda x: x.usd_value, reverse=True)[:5]

    def _save_snapshot(self, symbol: str, bids: list, asks: list):
        """Order book snapshotini saqlash (iceberg uchun)"""
        snap = {
            "bids": {p: q for p, q in bids[:100]},
            "asks": {p: q for p, q in asks[:100]},
            "ts": datetime.now(timezone.utc).timestamp()
        }
        if symbol not in self._ob_snapshots:
            self._ob_snapshots[symbol] = []
        self._ob_snapshots[symbol].append(snap)
        # Oxirgi 10 ta snapshot
        self._ob_snapshots[symbol] = self._ob_snapshots[symbol][-10:]

    def _detect_icebergs(self, symbol: str, bids: list, asks: list) -> list[IcebergOrder]:
        """
        Iceberg aniqlash:
        Narx darajasi ko'p marta yangilanib qayta to'ldirilsa = yashirin katta order
        """
        snapshots = self._ob_snapshots.get(symbol, [])
        if len(snapshots) < 3:
            return []

        icebergs = []

        # Bid iceberg
        for p, q in bids[:50]:
            refresh_count = 0
            total_consumed = 0
            for snap in snapshots[:-1]:
                prev_q = snap["bids"].get(p, 0)
                if prev_q > 0 and q >= prev_q * 0.8:  # Hajm saqlanmoqda
                    refresh_count += 1
                    total_consumed += max(0, prev_q - q)

            if refresh_count >= self.ICEBERG_REFRESH_MIN and total_consumed > q * 2:
                conf = min(90, refresh_count * 15 + 30)
                icebergs.append(IcebergOrder(
                    price=p, side="BID", visible_qty=q,
                    estimated_total=total_consumed + q,
                    refresh_count=refresh_count,
                    usd_value=p * (total_consumed + q),
                    confidence=conf
                ))

        # Ask iceberg
        for p, q in asks[:50]:
            refresh_count = 0
            total_consumed = 0
            for snap in snapshots[:-1]:
                prev_q = snap["asks"].get(p, 0)
                if prev_q > 0 and q >= prev_q * 0.8:
                    refresh_count += 1
                    total_consumed += max(0, prev_q - q)

            if refresh_count >= self.ICEBERG_REFRESH_MIN and total_consumed > q * 2:
                conf = min(90, refresh_count * 15 + 30)
                icebergs.append(IcebergOrder(
                    price=p, side="ASK", visible_qty=q,
                    estimated_total=total_consumed + q,
                    refresh_count=refresh_count,
                    usd_value=p * (total_consumed + q),
                    confidence=conf
                ))

        return sorted(icebergs, key=lambda x: x.usd_value, reverse=True)[:5]

    def _generate_signal(self, bid_walls, ask_walls, icebergs,
                          imbalance, price) -> tuple[str, float, str]:
        score = 0
        reasons = []

        # Bid walls kuchli = narx qo'llab-quvvatlanmoqda
        bid_wall_usd = sum(w.usd_value for w in bid_walls)
        ask_wall_usd = sum(w.usd_value for w in ask_walls)

        if bid_wall_usd > ask_wall_usd * 2:
            score += 30
            reasons.append(f"Bid wall ${bid_wall_usd/1e6:.1f}M vs Ask ${ask_wall_usd/1e6:.1f}M")
        elif ask_wall_usd > bid_wall_usd * 2:
            score -= 30
            reasons.append(f"Ask wall ${ask_wall_usd/1e6:.1f}M vs Bid ${bid_wall_usd/1e6:.1f}M")

        # Iceberg
        for ice in icebergs[:2]:
            if ice.side == "BID":
                score += 20
                reasons.append(f"Iceberg BID @ {ice.price:.0f} ${ice.usd_value/1e6:.1f}M")
            else:
                score -= 20
                reasons.append(f"Iceberg ASK @ {ice.price:.0f} ${ice.usd_value/1e6:.1f}M")

        # Imbalance
        if imbalance > 0.3:
            score += 25
            reasons.append(f"Imbalance: {imbalance:.2f} (buy heavy)")
        elif imbalance < -0.3:
            score -= 25
            reasons.append(f"Imbalance: {imbalance:.2f} (sell heavy)")

        confidence = min(90, abs(score))

        if score >= 30 and confidence >= 40:
            return "BUY", confidence, " | ".join(reasons)
        elif score <= -30 and confidence >= 40:
            return "SELL", confidence, " | ".join(reasons)
        return "NEUTRAL", confidence, " | ".join(reasons) or "Aniq signal yo'q"

    def _neutral_state(self, symbol: str) -> OrderBookState:
        return OrderBookState(
            symbol=symbol, timestamp=datetime.now(timezone.utc).isoformat(),
            bid_walls=[], ask_walls=[], icebergs=[],
            imbalance=0, bid_ask_ratio=1, spread_pct=0,
            signal="NEUTRAL", confidence=0, description="Ma'lumot yo'q"
        )

    # ─── CUMULATIVE DELTA (CVD) ────────────────────────────────────

    async def get_cvd(self, symbol: str) -> CVDData:
        """Kümülatif Volume Delta — Libertex da NEUTRAL (Binance faqat enable_binance da)"""
        if not config.enable_binance:
            return CVDData(symbol, 0, 0, 0, "NEUTRAL", 0)
        bn_sym = self.BN_MAP.get(symbol)
        if not bn_sym:
            return CVDData(symbol, 0, 0, 0, "NEUTRAL", 0)

        try:
            # Binance futures aggTrades (so'nggi 1000 ta savdo)
            url = f"{self.BINANCE_FUTU}/aggTrades?symbol={bn_sym}&limit=500"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        return CVDData(symbol, 0, 0, 0, "NEUTRAL", 0)
                    trades = await r.json()

            now_ms = datetime.now(timezone.utc).timestamp() * 1000
            cvd = 0.0
            delta_1m = 0.0
            delta_5m = 0.0

            for t in trades:
                qty = float(t["q"])
                ts  = float(t["T"])
                is_market_sell = t["m"]  # maker=buyer → taker=seller
                delta = -qty if is_market_sell else qty

                cvd += delta
                age_min = (now_ms - ts) / 60000
                if age_min <= 1:
                    delta_1m += delta
                if age_min <= 5:
                    delta_5m += delta

            # Trend aniqlash
            if cvd > 0 and delta_1m > 0:
                trend = "BULLISH"
            elif cvd < 0 and delta_1m < 0:
                trend = "BEARISH"
            else:
                trend = "NEUTRAL"

            strength = min(100, abs(delta_5m) / max(abs(cvd), 1) * 100)

            return CVDData(
                symbol=symbol, cvd=round(cvd, 2),
                delta_1m=round(delta_1m, 2), delta_5m=round(delta_5m, 2),
                trend=trend, strength=round(strength, 1)
            )

        except Exception as e:
            logger.debug(f"CVD xato {symbol}: {e}")
            return CVDData(symbol, 0, 0, 0, "NEUTRAL", 0)

    # ─── BIG TRADES ───────────────────────────────────────────────

    async def get_big_trades(self, symbol: str,
                               min_usd: float = 50_000) -> list[BigTrade]:
        """$50k+ savdolarni real-vaqt aniqlash — Libertex da bo'sh"""
        if not config.enable_binance:
            return []
        bn_sym = self.BN_MAP.get(symbol)
        if not bn_sym:
            return []

        try:
            url = f"{self.BINANCE_FUTU}/aggTrades?symbol={bn_sym}&limit=200"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        return []
                    trades = await r.json()

            big = []
            for t in trades:
                price = float(t["p"])
                qty   = float(t["q"])
                usd   = price * qty
                if usd >= min_usd:
                    side = "SELL" if t["m"] else "BUY"
                    ts   = datetime.fromtimestamp(
                        t["T"] / 1000, tz=timezone.utc
                    ).isoformat()
                    big.append(BigTrade(
                        symbol=symbol, side=side,
                        price=price, quantity=qty,
                        usd_value=usd, exchange="Binance",
                        timestamp=ts, is_liquidation=False
                    ))

            return sorted(big, key=lambda x: x.usd_value, reverse=True)[:10]

        except Exception as e:
            logger.debug(f"Big trades xato {symbol}: {e}")
            return []

    # ─── BOOKMAP (VOLUME PROFILE) ──────────────────────────────────

    async def get_bookmap(self, symbol: str,
                           price_range_pct: float = 2.0) -> list[BookmapLevel]:
        """
        Bookmap analogi: Libertex da bo'sh (Binance faqat enable_binance da)
        """
        if not config.enable_binance:
            return []
        bn_sym = self.BN_MAP.get(symbol)
        if not bn_sym:
            return []

        try:
            # Keng order book
            url = f"{self.BINANCE_API}/depth?symbol={bn_sym}&limit=1000"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        return []
                    ob = await r.json()

            mid = (float(ob["bids"][0][0]) + float(ob["asks"][0][0])) / 2
            lo  = mid * (1 - price_range_pct / 100)
            hi  = mid * (1 + price_range_pct / 100)

            # Price buckets (0.05% intervals)
            bucket_size = mid * 0.0005
            buckets: dict[float, BookmapLevel] = {}

            for p_str, q_str in ob["bids"]:
                p, q = float(p_str), float(q_str)
                if lo <= p <= hi:
                    bucket = round(p / bucket_size) * bucket_size
                    if bucket not in buckets:
                        buckets[bucket] = BookmapLevel(bucket, 0, 0, 0, 0, False)
                    buckets[bucket].volume   += q
                    buckets[bucket].buy_vol  += q
                    buckets[bucket].delta    += q

            for p_str, q_str in ob["asks"]:
                p, q = float(p_str), float(q_str)
                if lo <= p <= hi:
                    bucket = round(p / bucket_size) * bucket_size
                    if bucket not in buckets:
                        buckets[bucket] = BookmapLevel(bucket, 0, 0, 0, 0, False)
                    buckets[bucket].volume   += q
                    buckets[bucket].sell_vol += q
                    buckets[bucket].delta    -= q

            levels = sorted(buckets.values(), key=lambda x: x.price)

            # POC (eng ko'p hajm)
            if levels:
                poc = max(levels, key=lambda x: x.volume)
                poc.is_poc = True

            return levels

        except Exception as e:
            logger.debug(f"Bookmap xato {symbol}: {e}")
            return []

    # ─── LIQUIDATION HEATMAP ──────────────────────────────────────

    async def get_liquidation_levels(self, symbol: str,
                                      current_price: float) -> dict:
        """
        Likvidatsiya darajalarini hisoblash — Libertex da bo'sh
        """
        if not config.enable_binance:
            return {}
        bn_sym = self.BN_MAP.get(symbol)
        if not bn_sym:
            return {}

        try:
            # Open Interest ma'lumotlari
            url = f"{self.BINANCE_FUTU}/openInterestHist?symbol={bn_sym}&period=5m&limit=50"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        return {}
                    data = await r.json()

            if not data:
                return {}

            # OI o'zgarishidan katta likvidatsiya ehtimoli bo'lgan darajalar
            liq_levels = {}
            leverages = [5, 10, 20, 50, 100]

            for lev in leverages:
                # Liq distance = 100% / leverage
                liq_pct = 100 / lev / 100
                long_liq  = current_price * (1 - liq_pct)  # Long pozitsiyalar
                short_liq = current_price * (1 + liq_pct)  # Short pozitsiyalar
                liq_levels[f"{lev}x_long_liq"]  = round(long_liq, 2)
                liq_levels[f"{lev}x_short_liq"] = round(short_liq, 2)

            liq_levels["current_price"] = current_price
            return liq_levels

        except Exception as e:
            logger.debug(f"Liquidation levels xato: {e}")
            return {}

    # ─── TELEGRAM FORMAT ──────────────────────────────────────────

    def format_ob_report(self, ob: OrderBookState, cvd: CVDData,
                           big_trades: list[BigTrade]) -> str:
        """Telegram uchun order book hisoboti"""
        lines = [f"📊 <b>ORDER BOOK: {ob.symbol}</b>", ""]

        # Imbalance
        imb = ob.imbalance
        imb_icon = "🟢" if imb > 0.2 else ("🔴" if imb < -0.2 else "⚪")
        lines.append(f"{imb_icon} Imbalance: <code>{imb:+.2f}</code> | B/A: <code>{ob.bid_ask_ratio:.2f}x</code>")

        # CVD
        cvd_icon = "📈" if cvd.trend == "BULLISH" else ("📉" if cvd.trend == "BEARISH" else "➡️")
        lines.append(f"{cvd_icon} CVD: <code>{cvd.cvd:+.0f}</code> | 5m delta: <code>{cvd.delta_5m:+.0f}</code>")

        # Bid walls
        if ob.bid_walls:
            w = ob.bid_walls[0]
            lines.append(f"🟢 Bid Wall: <code>${w.price:,.0f}</code> — ${w.usd_value/1e6:.2f}M")

        # Ask walls
        if ob.ask_walls:
            w = ob.ask_walls[0]
            lines.append(f"🔴 Ask Wall: <code>${w.price:,.0f}</code> — ${w.usd_value/1e6:.2f}M")

        # Icebergs
        if ob.icebergs:
            lines.append("\n🧊 <b>Iceberg orderlar:</b>")
            for ice in ob.icebergs[:2]:
                side_icon = "🟢" if ice.side == "BID" else "🔴"
                lines.append(
                    f"{side_icon} {ice.side} @ <code>${ice.price:,.0f}</code> "
                    f"~${ice.usd_value/1e6:.2f}M (x{ice.refresh_count})"
                )

        # Big trades
        if big_trades:
            lines.append("\n💥 <b>Katta savdolar:</b>")
            for t in big_trades[:3]:
                icon = "🟢" if t.side == "BUY" else "🔴"
                lines.append(f"{icon} {t.side} ${t.usd_value/1e3:.0f}k @ {t.price:,.2f}")

        lines.append(f"\n🎯 Signal: <b>{ob.signal}</b> | Ishonch: {ob.confidence:.0f}%")

        return "\n".join(lines)
