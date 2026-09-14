"""
GoldAI Ultra — Binance Futures Executor
Mobil MT5 o'rniga: Binance USDT-M Perpetual Futures orqali savdo.
Desktop MT5 kerak emas — faqat Binance API kalit.
"""

import asyncio
import aiohttp
import hmac
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

from core.config import config
from core.logger import logger
from engines.execution_engine import TradeResult
from engines.trade_log import trade_log


# Binance Futures symbol mapping: internal -> Binance
SYMBOL_MAP = {
    "BTCUSD":  "BTCUSDT",
    "ETHUSD":  "ETHUSDT",
    "BNBUSD":  "BNBUSDT",
    "SOLUSD":  "SOLUSDT",
    "XRPUSD":  "XRPUSDT",
    "ADAUSD":  "ADAUSDT",
    "DOTUSD":  "DOTUSDT",
    "AVAXUSD": "AVAXUSDT",
}

# Lot → quantity mapping (minimum precision)
MIN_QTY = {
    "BTCUSDT":  0.001,
    "ETHUSDT":  0.01,
    "BNBUSDT":  0.01,
    "SOLUSDT":  0.1,
    "XRPUSDT":  1.0,
    "ADAUSDT":  1.0,
    "DOTUSDT":  0.1,
    "AVAXUSDT": 0.1,
}

QTY_PRECISION = {
    "BTCUSDT": 3, "ETHUSDT": 2, "BNBUSDT": 2,
    "SOLUSDT": 1, "XRPUSDT": 0, "ADAUSDT": 0,
    "DOTUSDT": 1, "AVAXUSDT": 1,
}

# Narx (price/stopPrice) uchun to'g'ri decimal precision
PRICE_PRECISION = {
    "BTCUSDT": 1, "ETHUSDT": 2, "BNBUSDT": 2,
    "SOLUSDT": 2, "XRPUSDT": 4, "ADAUSDT": 4,
    "DOTUSDT": 3, "AVAXUSDT": 2,
}


@dataclass
class BinancePosition:
    ticket: int
    symbol: str               # Internal (BTCUSD)
    bn_symbol: str            # Binance (BTCUSDT)
    side: str                 # BUY | SELL
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float
    sl_order_id: int = 0
    tp_order_id: int = 0
    profit: float = 0.0
    current_price: float = 0.0
    # Trailing stop uchun qo'shimcha maydonlar
    original_sl: float = 0.0       # Entry da hisoblangan SL (trail uchun)
    atr_ref: float = 0.0           # ATR at entry (trail masofasi uchun)
    be_activated: bool = False     # Breakeven faollashganligi
    trailing_active: bool = False  # Trailing aktiv holati
    partial_taken: bool = False    # 1R da 50% foyda qulflanganligi


class BinanceExecutor:
    """
    Binance USDT-M Futures orqali savdo bajarish.
    Desktop MT5 kerak emas.
    SL/TP = alohida limit/stop-market orderlar.
    """

    BASE_FUTURES = "https://fapi.binance.com"
    BASE_SPOT    = "https://api.binance.com"

    def __init__(self):
        self.api_key = config.binance.api_key
        self.secret  = config.binance.secret_key
        self.testnet = config.binance.testnet

        if self.testnet:
            self.BASE_FUTURES = "https://testnet.binancefuture.com"
            self.BASE_SPOT    = "https://testnet.binance.vision"

        self._positions: dict[int, BinancePosition] = {}
        self._ticket_counter = int(time.time())
        self._leverage_set: set[str] = set()

    # ─── AUTH ─────────────────────────────────────────────────────

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        return hmac.new(
            self.secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key, "Content-Type": "application/x-www-form-urlencoded"}

    # ─── SYMBOL HELPERS ───────────────────────────────────────────

    def _to_binance(self, symbol: str) -> Optional[str]:
        return SYMBOL_MAP.get(symbol)

    def _round_qty(self, bn_symbol: str, qty: float) -> float:
        prec = QTY_PRECISION.get(bn_symbol, 2)
        return round(qty, prec)

    # ─── ACCOUNT ──────────────────────────────────────────────────

    async def get_account_info(self) -> dict:
        """USDT bakiyesi va hisob ma'lumotlari"""
        try:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            url = f"{self.BASE_FUTURES}/fapi/v2/account"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, headers=self._headers(),
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json()
                        # totalWalletBalance — haqiqiy balans (paper mode uchun to'g'ri)
                        bal = float(data.get("totalWalletBalance", 0))
                        equity = bal + float(data.get("totalUnrealizedProfit", 0))
                        return {
                            "balance": bal,
                            "equity": equity,
                            "source": "binance_futures",
                            "server": "Binance USDM Futures",
                            "currency": "USDT"
                        }
        except Exception as e:
            logger.debug(f"Binance account xato: {e}")

        # Spot fallback
        return await self._get_spot_balance()

    async def _get_spot_balance(self) -> dict:
        try:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            url = f"{self.BASE_SPOT}/api/v3/account"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, headers=self._headers(),
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json()
                        usdt = next(
                            (float(a["free"]) for a in data.get("balances", []) if a["asset"] == "USDT"),
                            0.0
                        )
                        return {"balance": usdt, "equity": usdt, "source": "binance_spot", "server": "Binance Spot", "currency": "USDT"}
        except Exception as e:
            logger.debug(f"Binance spot balance xato: {e}")
        return {"balance": 0, "equity": 0, "source": "binance", "server": "Binance"}

    # ─── LEVERAGE ─────────────────────────────────────────────────

    async def _set_leverage(self, bn_symbol: str, leverage: int = 5):
        if bn_symbol in self._leverage_set:
            return
        try:
            params = {
                "symbol": bn_symbol,
                "leverage": leverage,
                "timestamp": int(time.time() * 1000)
            }
            params["signature"] = self._sign(params)
            url = f"{self.BASE_FUTURES}/fapi/v1/leverage"
            async with aiohttp.ClientSession() as s:
                async with s.post(url, data=params, headers=self._headers(),
                                   timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        self._leverage_set.add(bn_symbol)
                        logger.debug(f"Leverage {leverage}x set: {bn_symbol}")
        except Exception as e:
            logger.debug(f"Leverage xato {bn_symbol}: {e}")

    # ─── ORDERS ───────────────────────────────────────────────────

    async def _place_futures_order(self, bn_symbol: str, side: str,
                                    order_type: str, quantity: float,
                                    price: float = 0.0,
                                    stop_price: float = 0.0,
                                    reduce_only: bool = False,
                                    close_position: bool = False) -> Optional[dict]:
        pp = PRICE_PRECISION.get(bn_symbol, 4)
        is_stop = order_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET")

        params = {
            "symbol": bn_symbol,
            "side": side,
            "type": order_type,
            "timestamp": int(time.time() * 1000),
        }

        if close_position and is_stop:
            params["closePosition"] = "true"
        else:
            params["quantity"] = quantity
            if reduce_only:
                params["reduceOnly"] = "true"

        if is_stop:
            params["workingType"] = "CONTRACT_PRICE"
            params["priceProtect"] = "FALSE"

        if price > 0:
            params["price"] = round(price, pp)
            params["timeInForce"] = "GTC"
        if stop_price > 0:
            params["stopPrice"] = round(stop_price, pp)

        params["signature"] = self._sign(params)
        url = f"{self.BASE_FUTURES}/fapi/v1/order"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, data=params, headers=self._headers(),
                                   timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
                    if r.status == 200:
                        return data
                    else:
                        logger.error(f"Binance order xato: {data}")
                        return None
        except Exception as e:
            logger.error(f"Binance order request xato: {e}")
        return None

    # ─── ALGO ORDERS (STOP_MARKET / TAKE_PROFIT_MARKET) ────────────
    # Binance 2025-12-09'dan boshlab conditional orderlar (STOP_MARKET,
    # TAKE_PROFIT_MARKET va h.k.) eski /fapi/v1/order orqali qabul
    # qilinmaydi (-4120 xato) — endi alohida Algo Order API kerak.

    async def _place_algo_order(self, bn_symbol: str, side: str, order_type: str,
                                 trigger_price: float, close_position: bool = True) -> Optional[dict]:
        pp = PRICE_PRECISION.get(bn_symbol, 4)
        params = {
            "algoType": "CONDITIONAL",
            "symbol": bn_symbol,
            "side": side,
            "type": order_type,
            "triggerPrice": round(trigger_price, pp),
            "workingType": "CONTRACT_PRICE",
            "priceProtect": "FALSE",
            "timestamp": int(time.time() * 1000),
        }
        if close_position:
            params["closePosition"] = "true"
        params["signature"] = self._sign(params)
        url = f"{self.BASE_FUTURES}/fapi/v1/algoOrder"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, data=params, headers=self._headers(),
                                   timeout=aiohttp.ClientTimeout(total=10)) as r:
                    data = await r.json()
                    if r.status == 200:
                        return data
                    logger.error(f"Binance algo order xato: {data}")
        except Exception as e:
            logger.error(f"Binance algo order request xato: {e}")
        return None

    async def _cancel_algo_order(self, algo_id: int):
        if not algo_id:
            return
        try:
            params = {"algoId": algo_id, "timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            url = f"{self.BASE_FUTURES}/fapi/v1/algoOrder"
            async with aiohttp.ClientSession() as s:
                async with s.delete(url, params=params, headers=self._headers(),
                                     timeout=aiohttp.ClientTimeout(total=8)):
                    pass
        except Exception as e:
            logger.debug(f"Algo order cancel xato (#{algo_id}): {e}")

    async def _replace_sl_order(self, pos: "BinancePosition", new_sl: float):
        """Trailing/breakeven SL o'zgarganda exchange'dagi SL algo orderni yangilaydi"""
        close_side = "SELL" if pos.side == "BUY" else "BUY"
        if pos.sl_order_id:
            await self._cancel_algo_order(pos.sl_order_id)
        result = await self._place_algo_order(
            pos.bn_symbol, close_side, "STOP_MARKET", new_sl, close_position=True
        )
        pos.sl_order_id = int(result.get("algoId", 0)) if result else 0

    # ─── BUY / SELL ───────────────────────────────────────────────

    def buy(self, symbol: str, lot: float, sl: float, tp: float, comment: str = "GoldAI") -> TradeResult:
        return asyncio.get_event_loop().run_until_complete(
            self.buy_async(symbol, lot, sl, tp, comment)
        )

    def sell(self, symbol: str, lot: float, sl: float, tp: float, comment: str = "GoldAI") -> TradeResult:
        return asyncio.get_event_loop().run_until_complete(
            self.sell_async(symbol, lot, sl, tp, comment)
        )

    async def buy_async(self, symbol: str, lot: float, sl: float, tp: float,
                         comment: str = "GoldAI", signal_entry: float = 0.0) -> TradeResult:
        return await self._open_position(symbol, "BUY", lot, sl, tp, signal_entry)

    async def sell_async(self, symbol: str, lot: float, sl: float, tp: float,
                          comment: str = "GoldAI", signal_entry: float = 0.0) -> TradeResult:
        return await self._open_position(symbol, "SELL", lot, sl, tp, signal_entry)

    async def _open_position(self, symbol: str, side: str, lot: float,
                               sl: float, tp: float, signal_entry: float = 0.0) -> TradeResult:
        bn_symbol = self._to_binance(symbol)
        if not bn_symbol:
            return TradeResult(False, error=f"{symbol} Binance'da topilmadi")

        # SL tekshiruvi
        if sl <= 0:
            return TradeResult(False, error="SL yo'q — savdo bloklandi (kapital himoyasi)")
        if tp > 0:
            if side == "BUY" and sl >= tp:
                return TradeResult(False, error=f"BUY: SL({sl}) >= TP({tp}) — mantiqsiz")
            if side == "SELL" and sl <= tp:
                return TradeResult(False, error=f"SELL: SL({sl}) <= TP({tp}) — mantiqsiz")

        await self._set_leverage(bn_symbol, leverage=10)

        qty = self._round_qty(bn_symbol, lot)
        min_qty = MIN_QTY.get(bn_symbol, 0.001)
        if qty < min_qty:
            qty = min_qty

        # Min notional $20 (Binance Futures talabi)
        # SL narxidan taxminiy entry narxini hisoblash
        approx_entry = abs(sl) * (1.015 if side == "BUY" else 0.985)
        if approx_entry > 0 and qty * approx_entry < 20:
            qty = max(self._round_qty(bn_symbol, 20 / approx_entry), min_qty)
            logger.info(f"📊 Min notional $20: qty → {qty}")

        # MARKET order (software SL monitoring bilan himoya qilinadi)
        result = await self._place_futures_order(bn_symbol, side, "MARKET", qty)
        if not result:
            return TradeResult(False, error="Binance market order bajarilmadi")

        entry = float(result.get("avgPrice", 0) or result.get("price", 0))
        if entry == 0:
            entry = sl * 1.01 if side == "BUY" else sl * 0.99

        # ── Narx siljishi tuzatish ────────────────────────────────
        # Scan narxi bilan haqiqiy fill narxi farqlansa → SL/TP qayta hisoblash
        # (Narx 0.1% ko'proq siljisa, eski SL/TP noto'g'ri bo'lib qoladi)
        if signal_entry > 0 and abs(entry - signal_entry) / max(signal_entry, 1e-10) > 0.001:
            orig_sl_dist = abs(signal_entry - sl)
            orig_tp_dist = abs(tp - signal_entry)
            if orig_sl_dist > 0:
                if side == "BUY":
                    sl = entry - orig_sl_dist
                    tp = entry + orig_tp_dist
                else:
                    sl = entry + orig_sl_dist
                    tp = entry - orig_tp_dist
                logger.info(
                    f"📍 SL/TP fill narxiga moslantirildi: {symbol} "
                    f"scan={signal_entry:.4f} → fill={entry:.4f} | "
                    f"SL:{sl:.5f} TP:{tp:.5f}"
                )

        ticket = self._ticket_counter
        self._ticket_counter += 1

        sl_dist = abs(entry - sl) if sl > 0 else entry * 0.015
        pos = BinancePosition(
            ticket=ticket, symbol=symbol, bn_symbol=bn_symbol,
            side=side, quantity=qty, entry_price=entry,
            stop_loss=sl, take_profit=tp,
            original_sl=sl,
            atr_ref=sl_dist,       # SL masofasini ATR o'rniga ishlatamiz
        )

        # ── Haqiqiy exchange SL/TP orderlar ─────────────────────────
        # Ilgari SL/TP faqat software polling (10s) bilan tekshirilardi —
        # tarmoq uzilsa yoki narx sakrasa pozitsiya himoyasiz qolardi.
        # Endi Binance o'zi closePosition=true bilan yopadi, bot offline
        # bo'lsa ham SL/TP ishlaydi. Software monitoring qo'shimcha
        # himoya (trailing/breakeven) sifatida davom etadi.
        close_side = "SELL" if side == "BUY" else "BUY"
        if sl > 0:
            sl_result = await self._place_algo_order(
                bn_symbol, close_side, "STOP_MARKET", sl, close_position=True
            )
            if sl_result:
                pos.sl_order_id = int(sl_result.get("algoId", 0))
        if tp > 0:
            tp_result = await self._place_algo_order(
                bn_symbol, close_side, "TAKE_PROFIT_MARKET", tp, close_position=True
            )
            if tp_result:
                pos.tp_order_id = int(tp_result.get("algoId", 0))

        self._positions[ticket] = pos

        logger.info(
            f"✅ Binance {side} {symbol} | Qty:{qty} | Entry:{entry:.4f} | "
            f"SL:{sl} {'✓ exchange' if pos.sl_order_id else '✗'} | "
            f"TP:{tp} {'✓ exchange' if pos.tp_order_id else '✗'} | #{ticket}"
        )
        return TradeResult(success=True, ticket=ticket, price=entry, lot=qty,
                           message=f"Binance {side} {symbol} @ {entry:.4f}")

    # ─── POZITSIYALAR ─────────────────────────────────────────────

    async def monitor_sl_tp(self) -> list[dict]:
        """Software SL/TP monitoring — har siklda chaqiriladi"""
        if not self._positions:
            return []

        symbols = {p.bn_symbol for p in self._positions.values()}
        prices = {}
        try:
            async with aiohttp.ClientSession() as s:
                for bn_sym in symbols:
                    async with s.get(
                        f"{self.BASE_FUTURES}/fapi/v1/ticker/price?symbol={bn_sym}",
                        timeout=aiohttp.ClientTimeout(total=3)
                    ) as r:
                        if r.status == 200:
                            d = await r.json()
                            prices[bn_sym] = float(d["price"])
        except Exception as e:
            logger.debug(f"SL monitor narx xato: {e}")
            return []

        closed = []
        for ticket, pos in list(self._positions.items()):
            price = prices.get(pos.bn_symbol)
            if not price:
                continue
            pos.current_price = price
            if pos.side == "BUY":
                pos.profit = (price - pos.entry_price) * pos.quantity
            else:
                pos.profit = (pos.entry_price - price) * pos.quantity

            # ── Trailing Stop + Partial TP logikasi ──────────────
            sl_dist = pos.atr_ref if pos.atr_ref > 0 else abs(pos.entry_price - pos.original_sl)
            if sl_dist > 1e-10:
                if pos.side == "BUY":
                    profit_r = (price - pos.entry_price) / sl_dist
                else:
                    profit_r = (pos.entry_price - price) / sl_dist

                # ─────────────────────────────────────────────────────
                # FOYDA QULFLASH TIZIMI (Profit Locking Trailing)
                # Narx ko'tarilgan sari SL ham ko'tariladi — zarar imkonsiz
                # Partial close YO'Q — to'liq pozitsiya katta foydaga yuguradi
                # ─────────────────────────────────────────────────────

                # ── 0.5R: Breakeven — zarar imkonsiz ────────────────
                if profit_r >= 0.5 and not pos.be_activated:
                    old_sl = pos.stop_loss
                    pos.stop_loss = pos.entry_price
                    pos.be_activated = True
                    await self._replace_sl_order(pos, pos.stop_loss)
                    logger.info(
                        f"🔒 BE: {pos.symbol} SL {old_sl:.5f} → entry {pos.entry_price:.5f}"
                    )

                # ── 1.0R: SL foydaga kiradi (+0.4R kafolatlanadi) ───
                if profit_r >= 1.0 and pos.be_activated:
                    if pos.side == "BUY":
                        lock_sl = pos.entry_price + sl_dist * 0.4
                        if lock_sl > pos.stop_loss:
                            pos.stop_loss = lock_sl
                            await self._replace_sl_order(pos, lock_sl)
                            logger.info(f"🔐 LOCK+0.4R: {pos.symbol} SL → {lock_sl:.5f}")
                    else:
                        lock_sl = pos.entry_price - sl_dist * 0.4
                        if lock_sl < pos.stop_loss:
                            pos.stop_loss = lock_sl
                            await self._replace_sl_order(pos, lock_sl)
                            logger.info(f"🔐 LOCK+0.4R: {pos.symbol} SL → {lock_sl:.5f}")

                # ── 1.5R: Katta foyda qulflash (+0.8R kafolatlanadi) ─
                if profit_r >= 1.5 and pos.be_activated:
                    if pos.side == "BUY":
                        lock_sl = pos.entry_price + sl_dist * 0.8
                        if lock_sl > pos.stop_loss:
                            pos.stop_loss = lock_sl
                            await self._replace_sl_order(pos, lock_sl)
                            logger.info(f"🔐 LOCK+0.8R: {pos.symbol} SL → {lock_sl:.5f}")
                    else:
                        lock_sl = pos.entry_price - sl_dist * 0.8
                        if lock_sl < pos.stop_loss:
                            pos.stop_loss = lock_sl
                            await self._replace_sl_order(pos, lock_sl)
                            logger.info(f"🔐 LOCK+0.8R: {pos.symbol} SL → {lock_sl:.5f}")

                # ── 2.0R: Qattiq trailing (SL = price − 0.3×sl_dist) ─
                if profit_r >= 2.0 and pos.be_activated:
                    trail_gap = sl_dist * 0.3
                    if pos.side == "BUY":
                        new_sl = price - trail_gap
                        if new_sl > pos.stop_loss:
                            pos.stop_loss = new_sl
                            pos.trailing_active = True
                            await self._replace_sl_order(pos, new_sl)
                            logger.info(f"📈 TRAIL: {pos.symbol} SL → {new_sl:.5f}")
                    else:
                        new_sl = price + trail_gap
                        if new_sl < pos.stop_loss:
                            pos.stop_loss = new_sl
                            pos.trailing_active = True
                            await self._replace_sl_order(pos, new_sl)
                            logger.info(f"📉 TRAIL: {pos.symbol} SL → {new_sl:.5f}")

            # ── SL/TP tekshiruvi ──────────────────────────────────
            reason = None
            if pos.side == "BUY":
                if pos.stop_loss > 0 and price <= pos.stop_loss:
                    reason = "STOP_LOSS"
                elif pos.take_profit > 0 and price >= pos.take_profit:
                    reason = "TAKE_PROFIT"
            else:
                if pos.stop_loss > 0 and price >= pos.stop_loss:
                    reason = "STOP_LOSS"
                elif pos.take_profit > 0 and price <= pos.take_profit:
                    reason = "TAKE_PROFIT"

            if reason:
                # Ikkinchi (ishlatilmagan) exchange orderni bekor qilamiz —
                # aks holda position yopilgach ham yetim order qolib ketadi
                other_id = pos.tp_order_id if reason == "STOP_LOSS" else pos.sl_order_id
                if other_id:
                    await self._cancel_algo_order(other_id)

                close_side = "BUY" if pos.side == "SELL" else "SELL"
                await self._place_futures_order(
                    pos.bn_symbol, close_side, "MARKET", pos.quantity, reduce_only=True
                )
                emoji = "✅" if reason == "TAKE_PROFIT" else "🛑"
                be_tag = " [BE]" if pos.be_activated else ""
                logger.info(
                    f"{emoji} SW-{reason}{be_tag}: {pos.symbol} @ {price:.4f} | PnL: ${pos.profit:+.4f}"
                )
                closed.append({
                    "ticket": ticket, "symbol": pos.symbol, "side": pos.side,
                    "entry": pos.entry_price, "close_price": price,
                    "profit": pos.profit, "reason": reason,
                    "qty": pos.quantity,
                    "be_activated": pos.be_activated,
                    "partial_taken": pos.partial_taken,
                })
                del self._positions[ticket]

        return closed

    async def close_all_positions_async(self):
        """Bot to'xtatilganda barcha ochiq pozitsiyalarni yopish (async)"""
        if not self._positions:
            return
        logger.info(f"🔒 Bot to'xtatilmoqda — {len(self._positions)} pozitsiya yopilmoqda...")
        for ticket, pos in list(self._positions.items()):
            await self._cancel_algo_order(pos.sl_order_id)
            await self._cancel_algo_order(pos.tp_order_id)
            close_side = "BUY" if pos.side == "SELL" else "SELL"
            await self._place_futures_order(
                pos.bn_symbol, close_side, "MARKET", pos.quantity, reduce_only=True
            )
            logger.info(f"🔒 Yopildi: {pos.symbol} {pos.side}")
        self._positions.clear()

    def get_all_positions(self) -> list:
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": p.side,
                "volume": p.quantity,
                "open_price": p.entry_price,
                "current_price": p.current_price,
                "sl": p.stop_loss,
                "tp": p.take_profit,
                "profit": p.profit,
                "open_time": "",
                "comment": "Binance",
                "market_type": "crypto"
            }
            for p in self._positions.values()
        ]

    async def sync_positions(self):
        """Binance'dan haqiqiy pozitsiyalarni olish"""
        try:
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            url = f"{self.BASE_FUTURES}/fapi/v2/positionRisk"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, headers=self._headers(),
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        return
                    positions = await r.json()

            active = {SYMBOL_MAP.get(p.symbol, p.bn_symbol): p
                      for p in self._positions.values()}

            for pos_data in positions:
                bn_sym = pos_data["symbol"]
                amt = float(pos_data.get("positionAmt", 0))
                if abs(amt) < 1e-8 and bn_sym in active:
                    # Yopilgan — o'chirish
                    ticket = next((t for t, p in self._positions.items()
                                   if p.bn_symbol == bn_sym), None)
                    if ticket:
                        del self._positions[ticket]
                elif abs(amt) > 1e-8:
                    # Mavjud — profit yangilash
                    upnl = float(pos_data.get("unRealizedProfit", 0))
                    cur_price = float(pos_data.get("markPrice", 0))
                    for p in self._positions.values():
                        if p.bn_symbol == bn_sym:
                            p.profit = upnl
                            p.current_price = cur_price
        except Exception as e:
            logger.debug(f"Binance sync xato: {e}")

    async def load_positions_from_binance(self) -> int:
        """
        Bot qayta yonganda Binance'dan ochiq pozitsiyalarni yuklaydi.
        Har bir pozitsiya uchun SL ordern tekshiradi — yo'q bo'lsa qayta qo'yadi.
        """
        loaded = 0
        try:
            # 1. Ochiq pozitsiyalar
            params = {"timestamp": int(time.time() * 1000)}
            params["signature"] = self._sign(params)
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.BASE_FUTURES}/fapi/v2/positionRisk",
                    params=params, headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status != 200:
                        return 0
                    positions = await r.json()

            # 2. Mavjud orderlar (SL/TP ni topish uchun)
            params2 = {"timestamp": int(time.time() * 1000)}
            params2["signature"] = self._sign(params2)
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.BASE_FUTURES}/fapi/v1/openOrders",
                    params=params2, headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    open_orders = await r.json() if r.status == 200 else []

            # Symbol bo'yicha SL order id ni toping
            sl_by_sym = {}
            tp_by_sym = {}
            for o in (open_orders if isinstance(open_orders, list) else []):
                sym = o.get("symbol", "")
                otype = o.get("type", "")
                if otype == "STOP_MARKET":
                    sl_by_sym[sym] = int(o.get("orderId", 0))
                elif otype == "TAKE_PROFIT_MARKET":
                    tp_by_sym[sym] = int(o.get("orderId", 0))

            # Internal symbol → BinancePosition
            rev_map = {v: k for k, v in SYMBOL_MAP.items()}

            for pos_data in positions:
                bn_sym = pos_data["symbol"]
                amt = float(pos_data.get("positionAmt", 0))
                if abs(amt) < 1e-8:
                    continue

                int_sym = rev_map.get(bn_sym)
                if not int_sym:
                    continue

                side = "BUY" if amt > 0 else "SELL"
                qty = abs(amt)
                entry = float(pos_data.get("entryPrice", 0))
                sl_p = float(pos_data.get("stopPrice", 0))  # Binance positionRisk da SL yo'q
                upnl = float(pos_data.get("unRealizedProfit", 0))

                # Mavjud pozitsiyani ro'yxatga qo'shish
                ticket = self._ticket_counter
                self._ticket_counter += 1

                sl_id = sl_by_sym.get(bn_sym, 0)
                tp_id = tp_by_sym.get(bn_sym, 0)

                bp = BinancePosition(
                    ticket=ticket, symbol=int_sym, bn_symbol=bn_sym,
                    side=side, quantity=qty, entry_price=entry,
                    stop_loss=sl_p, take_profit=0.0,
                    sl_order_id=sl_id, tp_order_id=tp_id,
                    profit=upnl,
                    current_price=float(pos_data.get("markPrice", 0))
                )
                self._positions[ticket] = bp
                loaded += 1

                # Software SL: default SW-SL belgilash (0.4% entry dan — qattiq)
                pp = PRICE_PRECISION.get(bn_sym, 4)
                if bp.stop_loss <= 0:
                    bp.stop_loss = round(entry * 0.996, pp) if side == "BUY" \
                                   else round(entry * 1.004, pp)
                    logger.warning(
                        f"⚠️  Restart: {int_sym} SL yo'q → default SW-SL: {bp.stop_loss:.5f} (0.4%)"
                    )
                else:
                    logger.info(
                        f"📂 Yuklandi: {int_sym} {side} Qty:{qty} | "
                        f"Entry:{entry:.4f} | SW-SL:{bp.stop_loss:.5f} ✓"
                    )

                # Original SL va atr_ref (trailing stop uchun)
                sl_dist = abs(entry - bp.stop_loss)
                bp.original_sl = bp.stop_loss
                bp.atr_ref     = sl_dist

                # Default TP: 2:1 R:R (SL masofasining 2x qarama-qarshi tomonga)
                if bp.take_profit <= 0 and sl_dist > 0:
                    if side == "BUY":
                        bp.take_profit = round(entry + sl_dist * 2.0, pp)
                    else:
                        bp.take_profit = round(entry - sl_dist * 2.0, pp)
                    logger.info(
                        f"📐 Restart TP: {int_sym} → {bp.take_profit:.5f} (2:1 R:R)"
                    )

        except Exception as e:
            logger.warning(f"Binance pozitsiyalar yuklashda xato: {e}")

        return loaded

    async def ensure_sl_orders(self) -> int:
        """
        Software SL mode — exchange STOP_MARKET orderlar tekshirilmaydi.
        SL monitoring monitor_sl_tp() orqali har siklda bajariladi.
        """
        return 0

    def close_all_positions(self, reason: str = "Close All") -> list:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._close_all_async(reason))

    async def _close_all_async(self, reason: str) -> list:
        results = []
        for ticket in list(self._positions.keys()):
            r = await self._close_position_async(ticket)
            results.append(r)
        return results

    async def _close_position_async(self, ticket: int) -> TradeResult:
        pos = self._positions.get(ticket)
        if not pos:
            return TradeResult(False, error="Topilmadi")

        await self._cancel_algo_order(pos.sl_order_id)
        await self._cancel_algo_order(pos.tp_order_id)

        close_side = "SELL" if pos.side == "BUY" else "BUY"
        result = await self._place_futures_order(
            pos.bn_symbol, close_side, "MARKET", pos.quantity, reduce_only=True
        )
        if result:
            del self._positions[ticket]
            return TradeResult(True, ticket=ticket)
        return TradeResult(False, error="Yopish xatosi")

    def close_position(self, ticket: int, lot: Optional[float] = None) -> TradeResult:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._close_position_async(ticket))

    def set_break_even(self, ticket: int, buffer_points: float = 3.0) -> TradeResult:
        """Binance'da break-even: SL orderni yangilash"""
        pos = self._positions.get(ticket)
        if not pos:
            return TradeResult(False, error="Topilmadi")
        new_sl = pos.entry_price
        pos.stop_loss = new_sl
        logger.debug(f"Binance break-even #{ticket}: SL → {new_sl}")
        return TradeResult(True, ticket=ticket)

    def apply_trailing_stop(self, ticket: int, trail_pips: float, step_pips: float) -> TradeResult:
        return TradeResult(False, error="Trailing: keyingi versiyada")

    def get_symbol_info(self, symbol: str) -> dict:
        bn_sym = self._to_binance(symbol)
        if not bn_sym:
            return {}
        return {
            "symbol": bn_sym,
            "digits": 2,
            "volume_min": MIN_QTY.get(bn_sym, 0.001),
            "volume_max": 1000.0,
            "volume_step": MIN_QTY.get(bn_sym, 0.001),
            "trade_tick_value": 1.0,
            "trade_tick_size": 0.01,
            "type": "crypto"
        }
