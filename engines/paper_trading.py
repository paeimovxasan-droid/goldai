"""
GoldAI Ultra — Paper Trading (Demo Simulyatsiya)
Real pul bo'lmaganda (balans < $50) savdolarni simulyatsiya qiladi:
  - Real narxlar va real signal hisoblamalari
  - PostgreSQL ga 'paper' manbali sifatida yozadi
  - Telegram orqali to'liq hisobot yuboradi
  - Real pul kelganda avtomatik real rejimga o'tadi
"""

import asyncio
import aiohttp
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from core.logger import logger
from core.config import config


PAPER_THRESHOLD_USD = 5.0


def _paper_mode_from_config(balance: float) -> bool:
    """Respect an explicit mode; never silently paper-trade a funded MT5 account."""
    mode = getattr(config, "trading_mode", "live")
    if mode == "paper":
        return True
    if mode == "live":
        return False
    return balance < PAPER_THRESHOLD_USD


@dataclass
class PaperResult:
    success: bool
    ticket:  int
    error:   str = ""


@dataclass
class PaperPosition:
    ticket:      int
    symbol:      str
    side:        str        # BUY | SELL
    lot:         float
    entry_price: float
    stop_loss:   float
    take_profit: float
    open_time:   float      # time.time()
    current_price: float = 0.0
    paper_profit:  float = 0.0
    closed:        bool  = False
    close_price:   float = 0.0
    close_reason:  str   = ""


class PaperTradingEngine:
    """
    Binance narxlarini real-vaqt kuzatib,
    SL/TP larga yetganda pozitsiyani yopadi va DB + Telegram'ga xabar beradi.
    """

    BN_MAP = {
        "BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "BNBUSD": "BNBUSDT",
        "SOLUSD": "SOLUSDT", "XRPUSD": "XRPUSDT", "ADAUSD": "ADAUSDT",
    }

    def __init__(self):
        self._positions: dict[int, PaperPosition] = {}
        self._next_ticket = int(time.time()) % 100000
        self._closed_log: list[dict] = []

    def is_paper_mode(self, balance: float) -> bool:
        return _paper_mode_from_config(balance)

    def open_position(self, symbol: str, side: str, lot: float,
                       entry: float, sl: float, tp: float) -> PaperResult:
        self._next_ticket += 1
        pos = PaperPosition(
            ticket=self._next_ticket,
            symbol=symbol, side=side, lot=lot,
            entry_price=entry, stop_loss=sl, take_profit=tp,
            open_time=time.time(), current_price=entry
        )
        self._positions[self._next_ticket] = pos
        logger.info(
            f"📝 PAPER TRADE #{self._next_ticket}: {side} {symbol} "
            f"@ {entry} | SL:{sl} | TP:{tp} | Lot:{lot}"
        )
        return PaperResult(success=True, ticket=self._next_ticket)

    def get_all_positions(self) -> list:
        return [
            {
                "ticket": p.ticket, "symbol": p.symbol,
                "side": p.side, "type": p.side,
                "lot": p.lot, "volume": p.lot,
                "open_price": p.entry_price,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "profit": p.paper_profit,
                "is_paper": True,
            }
            for p in self._positions.values()
            if not p.closed
        ]

    async def update_prices(self) -> list[dict]:
        """
        Binance'dan real narxlarni olish va
        SL/TP ga yetganlarni yopish. Yopilgan pozitsiyalar qaytariladi.
        """
        if not self._positions:
            return []

        closed_now = []
        symbols = {p.symbol for p in self._positions.values() if not p.closed}

        # Narxlarni olish
        prices = {}
        for sym in symbols:
            bn_sym = self.BN_MAP.get(sym)
            if not bn_sym:
                continue
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={bn_sym}",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            prices[sym] = float(data["price"])
            except Exception:
                pass

        # Har pozitsiyani tekshirish
        for ticket, pos in list(self._positions.items()):
            if pos.closed:
                continue
            price = prices.get(pos.symbol)
            if not price:
                continue

            pos.current_price = price

            # Floating profit hisoblash
            if pos.side == "BUY":
                pos.paper_profit = (price - pos.entry_price) * pos.lot * self._contract_size(pos.symbol)
            else:
                pos.paper_profit = (pos.entry_price - price) * pos.lot * self._contract_size(pos.symbol)

            # SL/TP tekshiruvi
            reason = None
            close_price = price

            if pos.side == "BUY":
                if price <= pos.stop_loss:
                    reason = "STOP_LOSS"
                    close_price = pos.stop_loss
                elif price >= pos.take_profit:
                    reason = "TAKE_PROFIT"
                    close_price = pos.take_profit
            else:
                if price >= pos.stop_loss:
                    reason = "STOP_LOSS"
                    close_price = pos.stop_loss
                elif price <= pos.take_profit:
                    reason = "TAKE_PROFIT"
                    close_price = pos.take_profit

            if reason:
                if pos.side == "BUY":
                    final_profit = (close_price - pos.entry_price) * pos.lot * self._contract_size(pos.symbol)
                else:
                    final_profit = (pos.entry_price - close_price) * pos.lot * self._contract_size(pos.symbol)

                pos.closed = True
                pos.close_price = close_price
                pos.close_reason = reason
                pos.paper_profit = final_profit

                logger.info(
                    f"{'✅' if reason == 'TAKE_PROFIT' else '❌'} PAPER CLOSE #{ticket}: "
                    f"{pos.symbol} {pos.side} | {reason} @ {close_price} | P/L: ${final_profit:+.2f}"
                )
                closed_now.append({
                    "ticket": ticket, "symbol": pos.symbol, "side": pos.side,
                    "entry": pos.entry_price, "close_price": close_price,
                    "profit": final_profit, "reason": reason,
                    "lot": pos.lot,
                    "duration_min": int((time.time() - pos.open_time) / 60)
                })
                del self._positions[ticket]

        return closed_now

    def _contract_size(self, symbol: str) -> float:
        sizes = {
            "BTCUSD": 1.0, "ETHUSD": 1.0, "BNBUSD": 1.0,
            "SOLUSD": 1.0, "XRPUSD": 1.0,
        }
        return sizes.get(symbol, 1.0)

    def get_stats(self) -> dict:
        total = len(self._closed_log)
        if total == 0:
            return {}
        wins = sum(1 for t in self._closed_log if t.get("profit", 0) > 0)
        total_pnl = sum(t.get("profit", 0) for t in self._closed_log)
        return {
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": wins / total * 100,
            "total_pnl": round(total_pnl, 2),
        }
