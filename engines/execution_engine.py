"""
GoldAI Ultra — Libertex (ForexClub) Execution Engine
Barcha bozorlar uchun: Forex, Crypto, Stocks, Commodities via ForexClub MT5
Lager: ForexClub-MT5 Real/Demo Server
"""

import time
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    class _MockMT5:
        ORDER_TYPE_BUY = 0; ORDER_TYPE_SELL = 1
        TRADE_ACTION_DEAL = 1; TRADE_ACTION_SLTP = 2
        ORDER_TIME_GTC = 0; ORDER_FILLING_IOC = 1; ORDER_FILLING_FOK = 2; ORDER_FILLING_RETURN = 4
        TRADE_RETCODE_DONE = 10009
        def __getattr__(self, name): return 0
        def last_error(self): return "MT5 not available"
        def order_send(self, *a, **kw): return None
        def positions_get(self, *a, **kw): return None
        def symbol_info(self, *a, **kw): return None
        def symbol_info_tick(self, *a, **kw): return None
        def symbol_select(self, *a, **kw): return False
        def symbols_get(self): return None
    mt5 = _MockMT5()

from dataclasses import dataclass
from typing import Optional

from core.config import MARKETS, LIBERTEX_SYMBOL_ALIASES
from core.logger import logger
from core.config import config


@dataclass
class TradeResult:
    success: bool
    ticket: int = 0
    price: float = 0.0
    lot: float = 0.0
    error: str = ""
    message: str = ""


class ExecutionEngine:
    """Libertex MT5 orqali savdo ijrosi — ForexClub"""

    def __init__(self):
        self.magic = config.mt5.magic_number
        self.slippage = 20
        self._last_order_time = 0.0
        self._min_interval = 1.5
        self.broker = config.mt5.broker

    def _wait(self):
        elapsed = time.time() - self._last_order_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_order_time = time.time()

    @staticmethod
    def _trade_allowed(info) -> bool:
        """Handle both old MT5 builds and current SymbolInfo fields."""
        explicit = getattr(info, "trade_allowed", None)
        if explicit is not None:
            return bool(explicit)
        trade_mode = getattr(info, "trade_mode", None)
        if trade_mode is None:
            return True
        disabled = getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", 0)
        return trade_mode != disabled

    @staticmethod
    def _filling_mode(info):
        """Select a filling mode supported by the broker symbol.

        ``ORDER_FILLING_*`` values are request values, while
        ``SYMBOL_FILLING_*`` values are flags; comparing the two directly was
        the reason many Libertex orders were rejected with invalid filling.
        """
        flags = int(getattr(info, "filling_mode", 0) or 0)
        symbol_fok = getattr(mt5, "SYMBOL_FILLING_FOK", 1)
        symbol_ioc = getattr(mt5, "SYMBOL_FILLING_IOC", 2)
        if flags & symbol_ioc:
            return mt5.ORDER_FILLING_IOC
        if flags & symbol_fok:
            return mt5.ORDER_FILLING_FOK
        # RETURN is accepted for non-market execution; IOC is the safest
        # fallback for market-execution symbols.
        execution = getattr(info, "trade_exemode", None)
        market_execution = getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2)
        if execution != market_execution:
            return mt5.ORDER_FILLING_RETURN
        return mt5.ORDER_FILLING_IOC

    @staticmethod
    def _successful_result(result) -> bool:
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009)}
        partial = getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)
        accepted.add(partial)
        return getattr(result, "retcode", None) in accepted

    def _get_price(self, symbol: str, order_type: str) -> float:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return 0.0
        return tick.ask if order_type == "BUY" else tick.bid

    def _normalize_symbol(self, symbol: str) -> str:
        """Libertex MT5 da symbol mavjudligini tekshirish — ForexClub suffixlari"""
        # Avval to'g'ridan tekshirish
        info = mt5.symbol_info(symbol)
        if info is not None:
            mt5.symbol_select(symbol, True)
            return symbol

        # Alias larni tekshirish
        aliases = LIBERTEX_SYMBOL_ALIASES.get(symbol, [])
        for alias in aliases:
            if mt5.symbol_info(alias) is not None:
                mt5.symbol_select(alias, True)
                if alias != symbol:
                    logger.info(f"📊 Libertex symbol: {symbol} → {alias}")
                return alias

        # Suffix bilan tekshirish (ForexClub ko'pincha suffixsiz, lekin ba'zan . va boshqalar)
        for suffix in ["", ".", ".a", ".r", "m", "#", ".pro", ".ecn"]:
            test = symbol + suffix
            if mt5.symbol_info(test) is not None:
                mt5.symbol_select(test, True)
                if test != symbol:
                    logger.info(f"📊 Libertex symbol: {symbol} → {test}")
                return test

        # Barcha mavjud symollar orasidan prefix/suffix bo'yicha qidirish
        try:
            all_symbols = mt5.symbols_get()
            wanted = "".join(ch for ch in symbol.upper() if ch.isalnum())
            if all_symbols:
                for item in all_symbols:
                    name = str(getattr(item, "name", ""))
                    normalized = "".join(ch for ch in name.upper() if ch.isalnum())
                    if normalized.startswith(wanted) or normalized.endswith(wanted):
                        mt5.symbol_select(name, True)
                        logger.info(f"📊 Libertex symbol (fuzzy): {symbol} → {name}")
                        return name
        except Exception:
            pass

        logger.warning(f"⚠️ Symbol topilmadi MT5 da: {symbol} — baribir urinib ko'riladi")
        return symbol

    def buy(self, symbol: str, lot: float, sl: float, tp: float, comment: str = "GoldAI") -> TradeResult:
        return self._send_order(symbol, mt5.ORDER_TYPE_BUY, lot, sl, tp, comment)

    def sell(self, symbol: str, lot: float, sl: float, tp: float, comment: str = "GoldAI") -> TradeResult:
        return self._send_order(symbol, mt5.ORDER_TYPE_SELL, lot, sl, tp, comment)

    def _send_order(self, symbol: str, order_type: int, lot: float, sl: float, tp: float, comment: str) -> TradeResult:
        self._wait()

        original_symbol = symbol
        symbol = self._normalize_symbol(symbol)
        type_str = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
        price = self._get_price(symbol, type_str)

        if price == 0:
            logger.error(f"❌ {type_str} {original_symbol} ({symbol}): Narx olinmadi — symbol mavjud emas yoki bozor yopiq")
            return TradeResult(success=False, error=f"Narx olinmadi: {symbol} (bozor yopiq yoki symbol noto'g'ri)")

        # ── SL MAJBURIY TEKSHIRUV ────────────────────────────────
        if sl <= 0:
            logger.error(
                f"🚨 BLOKLANDI: {type_str} {symbol} | SL yo'q ({sl}) — "
                f"SLsiz savdo qilinmaydi! Kapitalni himoya qiling."
            )
            return TradeResult(success=False, error="SL yo'q — savdo bloklandi (kapital himoyasi)")

        if order_type == mt5.ORDER_TYPE_BUY and sl >= price:
            logger.error(f"🚨 BUY SL narxdan yuqori: SL={sl} >= Narx={price:.5f}")
            return TradeResult(success=False, error=f"BUY SL narxdan yuqori: {sl} >= {price:.5f}")

        if order_type == mt5.ORDER_TYPE_SELL and sl <= price:
            logger.error(f"🚨 SELL SL narxdan past: SL={sl} <= Narx={price:.5f}")
            return TradeResult(success=False, error=f"SELL SL narxdan past: {sl} <= {price:.5f}")
        # ─────────────────────────────────────────────────────────

        # Symbol info va lot tekshiruvi — Libertex uchun
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"❌ {symbol}: symbol_info yo'q")
            return TradeResult(success=False, error=f"Symbol info yo'q: {symbol}")

        terminal_info = getattr(mt5, "terminal_info", None)
        terminal = terminal_info() if callable(terminal_info) else None
        if terminal is not None and getattr(terminal, "trade_allowed", True) is False:
            return TradeResult(success=False, error="MT5 AutoTrading o'chiq — terminalda Algo Trading/AutoTrading ni yoqing")

        # Libertex lot tekshiruvi
        volume_min = float(getattr(info, "volume_min", 0.01) or 0.01)
        volume_max = float(getattr(info, "volume_max", lot) or lot)
        volume_step = float(getattr(info, "volume_step", volume_min) or volume_min)
        if lot < volume_min:
            logger.warning(f"⚠️ Lot juda kichik: {lot} < min {volume_min} → {volume_min} ga oshirildi")
            lot = volume_min
        if lot > volume_max:
            logger.warning(f"⚠️ Lot juda katta: {lot} > max {volume_max} → {volume_max} ga kamaytirildi")
            lot = volume_max
        if volume_step > 0:
            lot = volume_min + round((lot - volume_min) / volume_step) * volume_step
            lot = min(volume_max, max(volume_min, round(lot, 8)))

        # Current MT5 SymbolInfo does not expose ``trade_allowed``; it uses
        # ``trade_mode``.  Accessing the old attribute raised AttributeError
        # immediately before order_send, so no order could be opened.
        if not self._trade_allowed(info):
            logger.error(f"❌ {symbol}: instrumentda savdo ruxsat etilmagan")
            return TradeResult(success=False, error=f"{symbol}: savdo ruxsat etilmagan (trade_mode disabled)")

        # Digits normalizatsiya
        digits = int(getattr(info, "digits", 5) or 5)
        sl = round(sl, digits)
        tp = round(tp, digits) if tp > 0 else 0
        price = round(price, digits)
        if tp > 0:
            if order_type == mt5.ORDER_TYPE_BUY and tp <= price:
                return TradeResult(success=False, error="BUY TP narxdan yuqori bo'lishi kerak")
            if order_type == mt5.ORDER_TYPE_SELL and tp >= price:
                return TradeResult(success=False, error="SELL TP narxdan past bo'lishi kerak")

        # Filling mode brokerning SYMBOL_FILLING_* flaglaridan tanlanadi.
        filling = self._filling_mode(info)

        # Libertex da ba'zan symbol stops level tekshiruvi
        stops_level = info.trade_stops_level
        if stops_level > 0:
            min_dist = stops_level * info.point
            if type_str == "BUY":
                if abs(price - sl) < min_dist:
                    logger.warning(f"⚠️ SL juda yaqin: {abs(price-sl):.5f} < min {min_dist:.5f} → SL uzoqlashtirildi")
                    sl = round(price - min_dist * 1.2, digits)
                if tp > 0 and abs(tp - price) < min_dist:
                    tp = round(price + min_dist * 1.2, digits)
            else:
                if abs(sl - price) < min_dist:
                    sl = round(price + min_dist * 1.2, digits)
                if tp > 0 and abs(price - tp) < min_dist:
                    tp = round(price - min_dist * 1.2, digits)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": self.slippage,
            "magic": self.magic,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        logger.info(f"📤 Libertex order: {type_str} {original_symbol} ({symbol}) Lot:{lot} @ {price} SL:{sl} TP:{tp}")

        result = mt5.order_send(request)

        if result is None:
            err = str(mt5.last_error())
            logger.error(f"❌ {type_str} {symbol}: order_send None — {err}")
            return TradeResult(success=False, error=err)

        if not self._successful_result(result):
            err = f"Retcode:{getattr(result, 'retcode', '?')} {getattr(result, 'comment', '')}"
            logger.error(f"❌ {type_str} {symbol}: {err} (Ask:{price} SL:{sl} TP:{tp} Lot:{lot})")
            # Qo'shimcha ma'lumot
            if result.retcode == 10018:  # TRADE_RETCODE_MARKET_CLOSED
                logger.error("   → Bozor yopiq (dam olish kuni yoki sessiya yopiq)")
            elif result.retcode == 10019:
                logger.error("   → Mablag' yetarli emas (Free margin tekshiring)")
            return TradeResult(success=False, error=err)

        market_type = MARKETS.get(original_symbol, {}).get("type", "forex")
        type_icons = {"forex": "💱", "crypto": "₿", "commodity": "🏅", "stock": "📈", "index": "📊"}
        icon = type_icons.get(market_type, "📊")

        ticket = int(getattr(result, "order", 0) or getattr(result, "deal", 0) or 0)
        result_price = float(getattr(result, "price", 0) or price)
        logger.info(
            f"✅ TRADE {icon} Libertex | {type_str} {original_symbol} ({symbol}) | "
            f"#{ticket} | Price:{result_price} | Lot:{lot} | SL:{sl} | TP:{tp}"
        )

        return TradeResult(
            success=True, ticket=ticket,
            price=result_price, lot=lot,
            message=f"{type_str} {original_symbol} @ {result_price} (Libertex)"
        )

    def close_position(self, ticket: int, lot: Optional[float] = None) -> TradeResult:
        self._wait()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, error=f"#{ticket} topilmadi")

        pos = positions[0]
        close_lot = lot or pos.volume
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        symbol = pos.symbol
        price = self._get_price(symbol, "SELL" if pos.type == 0 else "BUY")

        # Filling mode
        info = mt5.symbol_info(symbol)
        filling = self._filling_mode(info) if info is not None else mt5.ORDER_FILLING_IOC
        if price <= 0:
            return TradeResult(success=False, error=f"#{ticket}: yopish narxi olinmadi (bozor yopiq yoki symbol noto'g'ri)")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_lot,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": self.slippage,
            "magic": self.magic,
            "comment": f"Close #{ticket}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        result = mt5.order_send(request)
        if result is None or not self._successful_result(result):
            err = str(mt5.last_error()) if result is None else f"Retcode:{getattr(result, 'retcode', '?')} {getattr(result, 'comment', '')}"
            logger.error(f"❌ Close #{ticket}: {err}")
            return TradeResult(success=False, error=err)

        result_price = float(getattr(result, "price", 0) or price)
        logger.info(f"✅ CLOSED Libertex #{ticket} {symbol} @ {result_price}")
        return TradeResult(success=True, ticket=ticket, price=result_price, lot=close_lot)

    def verify_all_sl(self) -> int:
        """
        Barcha ochiq pozitsiyalarda SL borligini tekshiradi.
        SL yo'q bo'lgan pozitsiyani darhol yopadi — sliv oldini olish.
        """
        try:
            positions = mt5.positions_get()
        except Exception:
            return 0
        if not positions:
            return 0

        closed = 0
        for pos in positions:
            if pos.sl == 0:
                logger.warning(
                    f"⚠️  SL YO'Q (Libertex): #{pos.ticket} {pos.symbol} | "
                    f"Narx: {pos.price_current:.5f} — YOPILMOQDA (himoya)!"
                )
                result = self.close_position(pos.ticket)
                if result.success:
                    logger.info(f"✅ SLsiz pozitsiya yopildi: #{pos.ticket} {pos.symbol}")
                    closed += 1
                else:
                    logger.error(f"❌ Yopishda xato #{pos.ticket}: {result.error}")
        return closed

    def close_all_positions(self, reason: str = "Close All") -> list:
        positions = mt5.positions_get()
        if not positions:
            return []
        results = [self.close_position(p.ticket) for p in positions]
        logger.info(f"Close All Libertex ({reason}): {len(results)} ta pozitsiya")
        return results

    def modify_position(self, ticket: int, sl=None, tp=None) -> TradeResult:
        self._wait()
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, error="Topilmadi")

        pos = positions[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": sl if sl is not None else pos.sl,
            "tp": tp if tp is not None else pos.tp,
            "magic": self.magic,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            return TradeResult(success=False, error=str(mt5.last_error()) if result is None else result.comment)
        logger.info(f"✏️ Modified Libertex #{ticket}: SL={sl} TP={tp}")
        return TradeResult(success=True, ticket=ticket)

    def set_break_even(self, ticket: int, buffer_points: float = 3.0) -> TradeResult:
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, error="Topilmadi")

        pos = positions[0]
        info = mt5.symbol_info(pos.symbol)
        if info is None:
            return TradeResult(success=False, error="Symbol info yo'q")

        point = info.point
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return TradeResult(success=False, error="Tick yo'q")

        if pos.type == 0:  # BUY
            current = tick.bid
            profit_pts = (current - pos.price_open) / point
            if profit_pts >= 15:
                new_sl = pos.price_open + buffer_points * point
                if new_sl > pos.sl:
                    return self.modify_position(ticket, sl=new_sl)
        else:  # SELL
            current = tick.ask
            profit_pts = (pos.price_open - current) / point
            if profit_pts >= 15:
                new_sl = pos.price_open - buffer_points * point
                if pos.sl == 0 or new_sl < pos.sl:
                    return self.modify_position(ticket, sl=new_sl)

        return TradeResult(success=False, error="Shartlar bajarilmadi")

    def apply_trailing_stop(self, ticket: int, trail_pips: float, step_pips: float) -> TradeResult:
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return TradeResult(success=False, error="Topilmadi")

        pos = positions[0]
        info = mt5.symbol_info(pos.symbol)
        if info is None:
            return TradeResult(success=False, error="Symbol info yo'q")

        point = info.point
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            return TradeResult(success=False, error="Tick yo'q")

        if pos.type == 0:  # BUY
            new_sl = tick.bid - trail_pips * point
            if new_sl > pos.sl + step_pips * point:
                return self.modify_position(ticket, sl=round(new_sl, info.digits))
        else:  # SELL
            new_sl = tick.ask + trail_pips * point
            if pos.sl == 0 or new_sl < pos.sl - step_pips * point:
                return self.modify_position(ticket, sl=round(new_sl, info.digits))

        return TradeResult(success=False, error="Trailing: shartlar bajarilmadi")
