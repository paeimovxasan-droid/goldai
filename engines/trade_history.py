"""
GoldAI Ultra — Trade History Engine
Barcha savdolarni PostgreSQL'ga yozish:
  - Ochilish: symbol, side, entry, SL, TP, lot, ishonch
  - Yopilish: close_price, profit, sabab (TP/SL/manual)
  - Statistika: win rate, avg profit, best/worst trade
"""

import asyncio
try:
    import asyncpg
except ImportError:
    asyncpg = None  # Linux CI — DB memory mode

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional
from core.logger import logger
from core.config import config


DB_URL = config.database.url


@dataclass
class TradeRecord:
    ticket:       int
    symbol:       str
    market_type:  str
    category:     str
    side:         str          # BUY | SELL
    lot:          float
    entry_price:  float
    stop_loss:    float
    take_profit:  float
    confidence:   float
    tier:         str
    whale_signal: bool
    reason:       str
    source:       str = "mt5"  # mt5 | binance


@dataclass
class TradeStats:
    total:       int
    wins:        int
    losses:      int
    win_rate:    float
    total_profit: float
    avg_profit:  float
    best_trade:  float
    worst_trade: float
    avg_rr:      float
    by_symbol:   dict
    by_market:   dict


class TradeHistory:
    """PostgreSQL da savdolarni saqlash va tahlil"""

    def __init__(self):
        self._pool: Optional[asyncpg.Pool] = None
        self._connected = False

    async def connect(self) -> bool:
        if asyncpg is None:
            logger.info("ℹ️ Trade History: asyncpg yo'q — xotira rejimi (Windows da DB ishlaydi)")
            self._connected = False
            return False
        try:
            self._pool = await asyncpg.create_pool(
                DB_URL, min_size=1, max_size=5,
                command_timeout=10
            )
            self._connected = True
            logger.info("✅ Trade History: PostgreSQL ulandi")
            return True
        except Exception as e:
            logger.warning(f"Trade History DB ulana olmadi: {e} — xotira rejimida ishlaydi")
            self._connected = False
            return False

    # ─── YOZISH ───────────────────────────────────────────────────

    async def save_open(self, trade: TradeRecord):
        """Yangi savdo ochilganda yozish"""
        if not self._connected:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO trades
                      (ticket, symbol, market_type, category, side, lot,
                       entry_price, stop_loss, take_profit, ai_confidence,
                       tier, whale_signal, comment, status, open_time)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'OPEN',NOW())
                    ON CONFLICT (ticket) DO NOTHING
                """,
                    trade.ticket, trade.symbol, trade.market_type,
                    trade.category, trade.side, trade.lot,
                    trade.entry_price, trade.stop_loss, trade.take_profit,
                    trade.confidence, trade.tier, trade.whale_signal,
                    trade.reason[:200] if trade.reason else ""
                )
        except Exception as e:
            logger.debug(f"DB save_open xato: {e}")

    async def save_close(self, ticket: int, close_price: float,
                          profit: float, reason: str):
        """Savdo yopilganda yangilash"""
        if not self._connected:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    UPDATE trades
                    SET close_price=$1, profit=$2, close_reason=$3,
                        status='CLOSED', close_time=NOW()
                    WHERE ticket=$4
                """, close_price, profit, reason[:50], ticket)
        except Exception as e:
            logger.debug(f"DB save_close xato: {e}")

    async def save_signal(self, signal_data: dict):
        """Signal yozish (bajarilsin yoki bajarilmasin)"""
        if not self._connected:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO signals
                      (symbol, market_type, signal, confidence,
                       entry_price, stop_loss, take_profit, rr_ratio, tier,
                       technical_score, liquidity_score, smc_score, whale_score,
                       whale_signal, institutional, reason, executed)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                """,
                    signal_data.get("symbol"), signal_data.get("market_type"),
                    signal_data.get("signal"), signal_data.get("confidence"),
                    signal_data.get("entry"), signal_data.get("sl"),
                    signal_data.get("tp"), signal_data.get("rr"),
                    signal_data.get("tier"), signal_data.get("tech_score", 0),
                    signal_data.get("liq_score", 0), signal_data.get("smc_score", 0),
                    signal_data.get("whale_score", 0),
                    signal_data.get("whale_signal", ""),
                    signal_data.get("institutional", False),
                    signal_data.get("reason", "")[:500],
                    signal_data.get("executed", False)
                )
        except Exception as e:
            logger.debug(f"DB save_signal xato: {e}")

    async def save_whale(self, symbol: str, signal: str, direction: str,
                          confidence: float, volume_spike: float,
                          order_size_usd: float, institutional: bool,
                          description: str):
        """Whale faoliyatini yozish"""
        if not self._connected:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO whale_activity
                      (symbol, signal, direction, confidence,
                       volume_spike, order_size_usd, exchange,
                       institutional, description)
                    VALUES ($1,$2,$3,$4,$5,$6,'binance',$7,$8)
                """,
                    symbol, signal, direction, confidence,
                    volume_spike, order_size_usd, institutional, description[:300]
                )
        except Exception as e:
            logger.debug(f"DB save_whale xato: {e}")

    async def save_balance(self, balance: float, equity: float, tier: str, growth: float):
        """Balans tarixini yozish"""
        if not self._connected:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO balance_history (balance, equity, tier, capital_growth)
                    VALUES ($1,$2,$3,$4)
                """, balance, equity, tier, growth)
        except Exception as e:
            logger.debug(f"DB save_balance xato: {e}")

    # ─── O'QISH ───────────────────────────────────────────────────

    async def get_open_trades(self) -> list:
        """Ochiq savdolar"""
        if not self._connected:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticket, symbol, side, lot, entry_price,
                           stop_loss, take_profit, open_time, comment
                    FROM trades WHERE status='OPEN'
                    ORDER BY open_time DESC
                """)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.debug(f"DB get_open_trades xato: {e}")
            return []

    async def get_history(self, limit: int = 50) -> list:
        """So'nggi savdolar tarixi"""
        if not self._connected:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticket, symbol, market_type, side, lot,
                           entry_price, close_price, profit, close_reason,
                           ai_confidence, tier, whale_signal,
                           open_time, close_time
                    FROM trades WHERE status='CLOSED'
                    ORDER BY close_time DESC LIMIT $1
                """, limit)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.debug(f"DB get_history xato: {e}")
            return []

    async def get_stats(self) -> Optional[TradeStats]:
        """Umumiy statistika"""
        if not self._connected:
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) AS wins,
                        SUM(CASE WHEN profit<=0 THEN 1 ELSE 0 END) AS losses,
                        ROUND(SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)::numeric/
                              NULLIF(COUNT(*),0)*100,1) AS win_rate,
                        ROUND(SUM(profit)::numeric,2) AS total_profit,
                        ROUND(AVG(profit)::numeric,2) AS avg_profit,
                        MAX(profit) AS best_trade,
                        MIN(profit) AS worst_trade
                    FROM trades WHERE status='CLOSED'
                """)
                if not row or not row["total"]:
                    return None

                # Symbol bo'yicha
                sym_rows = await conn.fetch("""
                    SELECT symbol,
                           COUNT(*) as total,
                           ROUND(SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END)::numeric/
                                 COUNT(*)*100,1) as wr,
                           ROUND(SUM(profit)::numeric,2) as profit
                    FROM trades WHERE status='CLOSED'
                    GROUP BY symbol ORDER BY profit DESC LIMIT 10
                """)
                # Market bo'yicha
                mkt_rows = await conn.fetch("""
                    SELECT market_type,
                           COUNT(*) as total,
                           ROUND(SUM(profit)::numeric,2) as profit
                    FROM trades WHERE status='CLOSED'
                    GROUP BY market_type ORDER BY profit DESC
                """)

                return TradeStats(
                    total=row["total"] or 0,
                    wins=row["wins"] or 0,
                    losses=row["losses"] or 0,
                    win_rate=float(row["win_rate"] or 0),
                    total_profit=float(row["total_profit"] or 0),
                    avg_profit=float(row["avg_profit"] or 0),
                    best_trade=float(row["best_trade"] or 0),
                    worst_trade=float(row["worst_trade"] or 0),
                    avg_rr=0,
                    by_symbol={r["symbol"]: {"total": r["total"], "wr": float(r["wr"] or 0),
                                              "profit": float(r["profit"] or 0)}
                               for r in sym_rows},
                    by_market={r["market_type"]: {"total": r["total"],
                                                   "profit": float(r["profit"] or 0)}
                               for r in mkt_rows}
                )
        except Exception as e:
            logger.debug(f"DB get_stats xato: {e}")
            return None

    async def get_today_stats(self) -> dict:
        """Bugungi statistika"""
        if not self._connected:
            return {}
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) as wins,
                           ROUND(SUM(profit)::numeric,2) as pnl,
                           COUNT(DISTINCT symbol) as symbols,
                           SUM(CASE WHEN close_reason='STOP_LOSS' THEN 1 ELSE 0 END) as sl_hits,
                           SUM(CASE WHEN close_reason='TAKE_PROFIT' THEN 1 ELSE 0 END) as tp_hits
                    FROM trades
                    WHERE status='CLOSED' AND DATE(close_time)=CURRENT_DATE
                """)
                if row:
                    return dict(row)
        except Exception:
            pass
        return {}

    async def detect_losing_patterns(self) -> list:
        """Qaysi sharoitlarda ko'p yo'qotilmoqda — tahlil"""
        if not self._connected:
            return []
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT symbol, market_type,
                           COUNT(*) as sl_count,
                           ROUND(AVG(profit)::numeric,2) as avg_loss
                    FROM trades
                    WHERE status='CLOSED' AND close_reason='STOP_LOSS'
                      AND close_time > NOW() - INTERVAL '7 days'
                    GROUP BY symbol, market_type
                    HAVING COUNT(*) >= 2
                    ORDER BY sl_count DESC
                """)
                return [dict(r) for r in rows]
        except Exception:
            return []
