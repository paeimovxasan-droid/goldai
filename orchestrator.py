"""
GoldAI Ultra — Multi-Market Orchestrator
Libertex (ForexClub) Edition
  • MT5 mode — Libertex MT5 via ForexClub (Forex + Crypto + Stocks + Commodities) — ASOSIY
  • Binance mode — Faqat ENABLE_BINANCE=true bo'lsa (ixtiyoriy fallback)

$10 → $1,000,000 Capital Growth System
Broker: ForexClub / Libertex
"""

import asyncio
import json
import os
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from core.config import config, MARKETS
from core.logger import logger
from engines.market_data import MultiMarketDataEngine
from engines.risk_engine import DynamicRiskEngine
from engines.execution_engine import ExecutionEngine
try:
    from engines.binance_executor import BinanceExecutor
except ImportError:
    BinanceExecutor = None  # Libertex da kerak emas, ENABLE_BINANCE=true da yuklanadi
from engines.whale_monitor import WhaleMonitor
from engines.market_scanner import MultiMarketScanner, MarketSignal
from engines.trade_history import TradeHistory, TradeRecord
from engines.news_engine import NewsEngine
from engines.orderbook_engine import OrderBookEngine
from engines.paper_trading import PaperTradingEngine, PAPER_THRESHOLD_USD
from agents.deepseek_agent import DeepSeekAgent
from bot.telegram_bot import TelegramBot
from engines.trade_log import trade_log
from engines.signal_filter import SignalFilter


@dataclass
class TradingDecision:
    action: str
    symbol: str
    market_type: str
    confidence: float
    lot: float
    entry: float
    stop_loss: float
    take_profit: float
    rr_ratio: float
    tier: str
    reason: str
    whale_involved: bool
    timestamp: str = ""
    cluster_score: float = 0.0
    cluster_type: str = ""
    poc: float = 0.0
    cvd_trend: str = ""


class UltraOrchestrator:
    """
    Asosiy tizim — Libertex MT5 va Binance rejimlarini avtomatik aniqlaydi.

    MT5 mode (Libertex):  Forex, Crypto, Stocks, Commodities, Indices — ASOSIY
    Binance mode: Faqat ENABLE_BINANCE=true bo'lsa, Crypto fallback
    """

    MODE_MT5     = "mt5"
    MODE_BINANCE = "binance"
    MODE_LIBERTEX = "mt5"  # Libertex ham MT5 orqali, alias

    def __init__(self):
        self.market    = MultiMarketDataEngine()
        self.risk      = DynamicRiskEngine()
        self.whale     = WhaleMonitor()
        self.scanner   = MultiMarketScanner()
        self.ai        = DeepSeekAgent()
        self.telegram  = TelegramBot()
        self.history   = TradeHistory()
        self.news      = NewsEngine()
        self.orderbook = OrderBookEngine()
        self.paper     = PaperTradingEngine()
        self.sig_filter = SignalFilter()

        # Execution engine — initialize qilinadi (Libertex MT5 asosiy, Binance faqat ENABLE_BINANCE da)
        self.execution: Optional[object] = None
        self.binance_exec: Optional[object] = None

        self._mode = self.MODE_MT5
        self._running = False
        self._cycle_count = 0
        self._trades_today = 0
        self._last_whale_alert: dict = {}
        self._open_ticket_map: dict = {}  # ticket → {symbol, entry, sl, tp, side, qty}
        self._auto_mode = True            # True=avtonomiya, False=faqat qo'lda
        self._sl_cooldown: dict = {}      # symbol → unix timestamp (SL olgandan keyin 45 min kutish)

        # State fayli joyi (script yonida)
        _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._state_file = os.path.join(_base, "goldai_state.json")

    # ─── INIT ─────────────────────────────────────────────────────

    async def initialize(self) -> bool:
        logger.info("=" * 65)
        logger.info("🚀 GoldAI Ultra — Libertex Edition")
        logger.info(f"   Broker: {config.mt5.broker} | Server: {config.mt5.server}")
        logger.info("   Forex | Crypto | Stocks | Commodities | Indices")
        logger.info("=" * 65)

        # TradeHistory DB ulanish
        await self.history.connect()

        # 1. Libertex MT5 ulanishiga urinib ko'rish — ASOSIY
        mt5_ok = self.market.connect_mt5()

        if mt5_ok:
            self._mode = self.MODE_MT5
            self.execution = ExecutionEngine()
            logger.info(f"✅ Rejim: LIBERTEX MT5 MODE ({config.mt5.broker} | Forex + Crypto + Stocks)")
            account = self.market.get_account_info()
            balance = account.get("balance", 0)
            logger.info(f"🏦 Libertex hisob: Login={account.get('login')} | Server={account.get('server')} | Leverage 1:{account.get('leverage')}")

        else:
            # MT5 ulana olmadi
            if config.enable_binance and BinanceExecutor is not None:
                logger.warning("⚠️  Libertex MT5 ulanmadi — BINANCE MODE ga o'tilmoqda (ixtiyoriy fallback)")
                self._mode = self.MODE_BINANCE
                self.binance_exec = BinanceExecutor()
                self.execution = self.binance_exec

                balance = 0
                for _attempt in range(3):
                    account = await self.binance_exec.get_account_info()
                    balance = account.get("balance", 0)
                    if balance > 0:
                        break
                    if _attempt < 2:
                        logger.warning(f"Binance balance 0 — {_attempt+1}/3 urinish, 3s kutilmoqda...")
                        await asyncio.sleep(3)

                logger.info(f"✅ Rejim: BINANCE MODE | Balans: ${balance:.2f} USDT")
            elif config.enable_binance and BinanceExecutor is None:
                logger.error("❌ ENABLE_BINANCE=true lekin BinanceExecutor yuklanmadi — modul xatosi")
                # Demo balans bilan davom etish
                balance = 10.0
                account = {"balance": balance, "equity": balance}
                self._mode = self.MODE_MT5
                self.execution = ExecutionEngine()
                logger.warning(f"⚠️  Demo rejimda davom etiladi: ${balance:.2f} (savdo qilinmaydi, faqat signal tahlili)")
            else:
                logger.error("❌ Libertex MT5 ulanmadi va ENABLE_BINANCE=false")
                logger.error("💡 Yechim: 1) MT5 terminal o'rnatilganligini tekshiring")
                logger.error("   2) .env da MT5_LOGIN/PASSWORD/SERVER to'g'riligini tekshiring")
                logger.error("   3) Libertex kabinetidagi server nomini 100% aniq ko'chiring")
                logger.error("   4) MT5 terminalida qo'lda login qilib ko'ring")
                # Demo balans bilan davom etish (monitoring uchun)
                balance = 10.0
                account = {"balance": balance, "equity": balance}
                self._mode = self.MODE_MT5
                self.execution = ExecutionEngine()
                logger.warning(f"⚠️  Demo rejimda davom etiladi: ${balance:.2f} (savdo qilinmaydi, faqat signal tahlili)")

        if balance < 1:
            logger.warning(f"⚠️  Balans past: ${balance:.2f} — demo balans $10 bilan davom etiladi")
            balance = max(balance, 10.0)

        self.risk.initialize(balance)
        params = config.risk.get_for_balance(balance)
        active = self._get_active_symbols(balance)

        logger.info(f"💰 Balans: ${balance:.2f} | Tier: {params['tier'].upper()}")
        logger.info(f"📊 Aktiv bozorlar ({len(active)}): {', '.join(active[:6])}...")
        logger.info(f"🎯 Risk/savdo: {params['risk_pct']*100:.1f}% | Daily limit: {params['daily_limit']*100:.0f}%")

        # ── STARTUP: SL tekshiruvi — bot qayta yonganda ──────────
        await self._startup_sl_check()
        # ─────────────────────────────────────────────────────────

        return True

    async def _startup_sl_check(self):
        """
        Bot ishga tushganda barcha ochiq pozitsiyalarda SL borligini tekshiradi.
        SL yo'q bo'lsa pozitsiyani darhol yopadi — sliv oldini olish.
        """
        logger.info("🔍 Startup: ochiq pozitsiyalar SL tekshiruvi...")

        if self._mode == self.MODE_BINANCE:
            # Binance: mavjud pozitsiyalarni yuklab olish (software SL bilan restore)
            loaded = await self.binance_exec.load_positions_from_binance()
            if loaded > 0:
                logger.info(
                    f"📂 Binance: {loaded} ta oldingi pozitsiya software SL bilan yuklandi"
                )
                await self.telegram.send(
                    f"📂 <b>Restart: {loaded} ta pozitsiya yuklandi</b>\n"
                    f"Software SL monitoring davom etmoqda."
                )
            else:
                logger.info("Binance: ochiq pozitsiya yo'q")

        elif self._mode == self.MODE_MT5:
            # MT5: SL yo'q pozitsiyalarni tekshirish va yopish
            closed = self.execution.verify_all_sl()
            if closed > 0:
                logger.warning(f"⚠️  MT5: SLsiz {closed} ta pozitsiya yopildi")
                await self.telegram.send(
                    f"⚠️ <b>Startup SL tekshiruvi (MT5)</b>\n"
                    f"SLsiz <b>{closed}</b> ta pozitsiya avtomatik yopildi.\n"
                    f"Kapital himoyasi faollashdi."
                )
            else:
                logger.info("✅ MT5: barcha pozitsiyalarda SL bor")

    def _get_active_symbols(self, balance: float) -> list:
        """Rejimga qarab aktiv symbollar — Libertex da barcha bozorlar mavjud"""
        all_symbols = config.get_active_symbols(balance)
        if self._mode == self.MODE_BINANCE:
            # Binance fallback — faqat crypto
            try:
                from engines.binance_executor import SYMBOL_MAP
                return [s for s in all_symbols if s in SYMBOL_MAP]
            except Exception:
                return [s for s in all_symbols if MARKETS.get(s, {}).get("type") == "crypto"]
        # Libertex MT5 — barcha bozorlar (Forex + Crypto + Stocks)
        return all_symbols

    # ─── ACCOUNT ──────────────────────────────────────────────────

    async def _get_account(self) -> dict:
        if self._mode == self.MODE_MT5:
            return self.market.get_account_info()
        else:
            return await self.binance_exec.get_account_info()

    def _get_positions(self) -> list:
        paper_pos = self.paper.get_all_positions()
        if paper_pos:
            return paper_pos
        if self._mode == self.MODE_MT5:
            return self.market.get_all_positions()
        else:
            return self.binance_exec.get_all_positions()

    # ─── MAIN CYCLE ───────────────────────────────────────────────

    async def run_cycle(self):
        self._cycle_count += 1

        try:
            # 1. Hisob ma'lumotlari
            account = await self._get_account()
            balance = account.get("balance", 0)
            equity  = account.get("equity", 0)

            if balance < 1:
                if self._cycle_count % 30 == 0:
                    logger.warning(f"⚠️  Balans: ${balance:.2f} — savdo yo'q, monitoring davom etadi")
                    if self._mode == self.MODE_BINANCE:
                        logger.warning("   Binance Futures walletingizga USDT o'tkazing!")
                    else:
                        logger.warning(f"   Libertex hisobingizga mablag' o'tkazing! Server: {config.mt5.server}")
                await self._check_whale_alerts(
                    await self._scan_market_data(self._get_active_symbols(10)), 10
                )
                return

            # Binance rejimida SL/TP tezkor monitoring (10s loop) da bajariladi
            # Bu yerda faqat pozitsiyalar soni yangilanadi

            # Binance rejimida pozitsiyalarni sinxronlashtirish
            if self._mode == self.MODE_BINANCE and self._cycle_count % 5 == 0:
                await self.binance_exec.sync_positions()

            # 2. Risk tekshiruvi
            positions = self._get_positions()
            risk_status = self.risk.check_risk(balance, equity, open_positions_count=len(positions))

            if not risk_status.is_safe:
                logger.warning(f"⚠️ {risk_status.message}")
                await self._handle_risk_breach(risk_status)
                return

            # 3. Yangiliklar + Sentiment (har 20 siklda)
            if self._cycle_count % 20 == 0:
                active_sym = self._get_active_symbols(balance)
                await self.news.get_sentiment(
                    [s.replace("USD","") for s in active_sym[:4]]
                )

            # News blackout — muhim yangilik kelsa savdo to'xtatish
            blackout, blackout_reason = self.news.is_blackout()
            if blackout:
                logger.warning(f"⏸️ News Blackout: {blackout_reason}")
                return

            # 4. Bozor ma'lumotlari
            active = self._get_active_symbols(balance)
            market_data = await self._scan_market_data(active)
            if not market_data:
                logger.warning("Bozor ma'lumoti yo'q")
                return

            # 5. Signal skanerlash
            scan = await self.scanner.scan_all(market_data, balance)
            if scan.total_signals == 0:
                logger.debug(f"Sikl #{self._cycle_count}: Signal yo'q ({scan.total_scanned} bozor)")
            elif not self._auto_mode:
                logger.debug(f"Manual rejim — {scan.total_signals} signal bor lekin o'tkazildi")
            else:
                # 6. Eng yaxshi 2 signal — OB/CVD kuchaytirib
                for signal in scan.best_signals[:2]:
                    await self._process_signal(signal, account, risk_status, market_data)

            # 7. AI sharh (har 10 siklda)
            if self._cycle_count % 10 == 0 and scan.best_signals:
                await self._ai_market_review(scan, account)

            # 8. Pozitsiyalarni boshqarish
            await self._manage_positions(balance)

            # 9. Whale monitoring (har 5 siklda)
            if self._cycle_count % 5 == 0:
                await self._check_whale_alerts(market_data, balance)

            # 10. Yopilgan pozitsiyalarni tarixga yozish
            await self._sync_closed_positions()

            # 10b. Paper trade SL/TP monitoringi
            closed_papers = await self.paper.update_prices()
            for cp in closed_papers:
                await self.history.save_close(
                    ticket=cp["ticket"], close_price=cp["close_price"],
                    profit=cp["profit"], reason=cp["reason"]
                )
                await self.telegram.send_trade_close(
                    symbol=cp["symbol"], side=cp["side"],
                    entry=cp["entry"], close_price=cp["close_price"],
                    profit=cp["profit"], reason=cp["reason"] + " [PAPER]",
                    ticket=cp["ticket"]
                )
                self.risk.record_trade_result(cp["profit"])

            # 11. Balans tarixini yozish (har 30 siklda) + state saqlash
            if self._cycle_count % 30 == 0:
                tier = config.risk.get_for_balance(balance)["tier"]
                growth = (balance - self.risk._start_balance) / max(1, self.risk._start_balance) * 100
                await self.history.save_balance(balance, equity, tier, round(growth, 2))
                trade_log.log_balance(balance, equity, tier, round(growth, 2))
                self._save_state()

            # 12. Soatlik hisobot (har 120 siklda)
            if self._cycle_count % 120 == 0:
                await self._hourly_report(account, risk_status)

            # 13. Orderbook alert (har 10 siklda)
            if self._cycle_count % 10 == 0 and scan.best_signals:
                await self._check_orderbook_alerts(scan.best_signals[:1])

            # 14. SL tekshiruvi (har 20 siklda) — ishlaydigan paytda ham himoya
            if self._cycle_count % 20 == 0:
                await self._runtime_sl_check()

        except Exception as e:
            logger.error(f"Sikl xatosi: {e}", exc_info=True)

    async def _scan_market_data(self, active_symbols: list) -> dict:
        """Bozor ma'lumotlarini olish — Libertex MT5 birinchi"""
        if self._mode == self.MODE_MT5:
            # Libertex MT5 — barcha instrumentlar MT5 dan
            return await self.market.scan_all_markets_list(active_symbols)
        else:
            # Binance fallback — faqat crypto
            results = {}
            tasks = {s: self.market.get_ohlc_async(s, "M15", 200) for s in active_symbols}
            for symbol, task in tasks.items():
                try:
                    df = await task
                    if df is not None and len(df) > 50:
                        results[symbol] = df
                except Exception as e:
                    logger.debug(f"OHLC xato ({symbol}): {e}")
            logger.info(f"📡 Binance scan: {len(results)}/{len(active_symbols)} symbol")
            return results

    # ─── SIGNAL PROCESSING ────────────────────────────────────────

    async def _process_signal(self, signal: MarketSignal, account: dict,
                               risk_status, market_data: dict = None):
        balance = account.get("balance", 0)

        # Duplicate tekshiruvi
        positions = self._get_positions()
        if any(p["symbol"] == signal.symbol for p in positions):
            logger.debug(f"Allaqachon ochiq: {signal.symbol}")
            return

        # SL olgandan keyin 45 daqiqa cooldown
        if signal.symbol in self._sl_cooldown:
            elapsed = time.time() - self._sl_cooldown[signal.symbol]
            if elapsed < 1800:  # 30 daqiqa
                mins_left = int((1800 - elapsed) / 60) + 1
                logger.info(f"⏳ {signal.symbol} cooldown: {mins_left}m qoldi (SL olgandan keyin)")
                return
            else:
                del self._sl_cooldown[signal.symbol]

        # Symbol info — Libertex MT5
        if self._mode == self.MODE_MT5:
            symbol_info = self.market.get_symbol_info(signal.symbol)
        else:
            try:
                symbol_info = self.binance_exec.get_symbol_info(signal.symbol)
            except Exception:
                symbol_info = self.market.get_symbol_info(signal.symbol)

        # ── Signal Filter (session + funding rate) ────────────────
        filter_ok, filter_reason = await self.sig_filter.check(
            symbol=signal.symbol, signal=signal.signal,
            market_type=signal.market_type
        )
        if not filter_ok:
            logger.info(f"🚫 {signal.symbol} filter blok: {filter_reason}")
            return

        # ── Smart SL ──────────────────────────────────────────────
        smart_sl = signal.stop_loss
        df = (market_data or {}).get(signal.symbol)
        if df is not None:
            atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else 0
            if atr > 0:
                smart_sl = self.risk.calculate_smart_sl(
                    symbol=signal.symbol,
                    side=signal.signal,
                    entry=signal.entry,
                    raw_sl=signal.stop_loss,
                    df=df,
                    atr=atr
                )
                if smart_sl != signal.stop_loss:
                    # Smart SL R:R ni pastga tushirsa — original SL ishlatamiz
                    orig_rr = abs(signal.take_profit - signal.entry) / max(abs(signal.stop_loss - signal.entry), 1e-10)
                    smart_rr = abs(signal.take_profit - signal.entry) / max(abs(smart_sl - signal.entry), 1e-10)
                    if smart_rr < max(1.0, orig_rr * 0.6):
                        logger.info(f"⚠️ Smart SL R:R ({smart_rr:.2f}) juda past — original SL: {signal.stop_loss:.5f}")
                        smart_sl = signal.stop_loss
                    else:
                        logger.info(
                            f"🛡️ Smart SL: {signal.stop_loss:.5f} → {smart_sl:.5f} "
                            f"(stop-hunt qochish | R:R:{smart_rr:.2f})"
                        )

        # ── Orderbook kuchaytiruvi ─────────────────────────────────
        news_modifier = self.news.get_signal_modifier(signal.symbol, signal.signal)
        adjusted_conf = min(99, signal.confidence * news_modifier)
        if news_modifier != 1.0:
            logger.info(f"📰 News modifier: x{news_modifier:.2f} → Ishonch: {adjusted_conf:.1f}%")

        # ── Lot hisoblash ─────────────────────────────────────────
        pos_size = self.risk.calculate_lot(
            symbol=signal.symbol,
            balance=balance,
            entry=signal.entry,
            stop_loss=smart_sl,
            take_profit=signal.take_profit,
            symbol_info=symbol_info
        )

        if not pos_size.allowed:
            logger.info(f"⚠️ {signal.symbol} savdo blok: {pos_size.reason}")
            return

        # Paper mode yoki minimal lot tekshiruvi
        is_paper = self.paper.is_paper_mode(balance)
        min_lot = symbol_info.get("volume_min", 0.001)
        if pos_size.lot < min_lot:
            # Minimal lot bilan davom et (paper yoki real)
            tag = "Paper" if is_paper else "Real-MinLot"
            pos_size = type(pos_size)(
                lot=min_lot,
                risk_amount=pos_size.risk_amount,
                sl_distance=pos_size.sl_distance,
                tp_distance=pos_size.tp_distance,
                rr_ratio=pos_size.rr_ratio,
                allowed=True,
                reason=f"{tag} lot: {min_lot}"
            )
            logger.info(f"📐 {tag}: lot {min_lot} ishlatildi")

        whale_involved = bool(signal.whale_activity and
                              signal.whale_activity.get("confidence", 0) > 50)
        reason_parts = [signal.reason]
        if news_modifier > 1.0:
            reason_parts.append("news_bullish" if signal.signal == "BUY" else "news_bearish")
        if smart_sl != signal.stop_loss:
            reason_parts.append("smart_sl_adjusted")

        decision = TradingDecision(
            action=signal.signal,
            symbol=signal.symbol,
            market_type=signal.market_type,
            confidence=adjusted_conf,
            lot=pos_size.lot,
            entry=signal.entry,
            stop_loss=smart_sl,
            take_profit=signal.take_profit,
            rr_ratio=pos_size.rr_ratio,
            tier=risk_status.tier,
            reason=" | ".join(reason_parts),
            whale_involved=whale_involved,
            timestamp=datetime.utcnow().isoformat(),
            cluster_score=getattr(signal, "cluster_score", 0.0),
            cluster_type=getattr(signal, "cluster_type", ""),
            poc=getattr(signal, "poc", 0.0),
            cvd_trend=getattr(signal, "cvd_trend", ""),
        )

        # Signal tarixini yozish
        await self.history.save_signal({
            "symbol": signal.symbol, "market_type": signal.market_type,
            "signal": signal.signal, "confidence": adjusted_conf,
            "entry": signal.entry, "sl": smart_sl,
            "tp": signal.take_profit, "rr": pos_size.rr_ratio,
            "tier": risk_status.tier, "whale_signal": str(signal.whale_activity or ""),
            "reason": decision.reason, "executed": True
        })

        await self._execute_trade(decision)

    async def _execute_trade(self, decision: TradingDecision):
        icons = {"forex": "💱", "crypto": "₿", "commodity": "🏅", "stock": "📈", "index": "📊"}
        emoji = icons.get(decision.market_type, "📊")
        if self._mode == self.MODE_BINANCE:
            mode_tag = "[Binance]"
        else:
            mode_tag = f"[Libertex MT5]"

        logger.info(
            f"\n{'='*55}\n"
            f"{emoji} {mode_tag} SAVDO: {decision.action} {decision.symbol}\n"
            f"   Tier: {decision.tier.upper()} | Ishonch: {decision.confidence:.1f}%\n"
            f"   Entry: {decision.entry} | Lot: {decision.lot}\n"
            f"   SL: {decision.stop_loss} | TP: {decision.take_profit}\n"
            f"   R:R: {decision.rr_ratio:.2f}\n"
            f"{'='*55}"
        )

        comment = f"GoldAI {decision.market_type[:3].upper()} {decision.confidence:.0f}%"

        # ── Balansga qarab real yoki paper mode ───────────────────
        account = await self._get_account()
        real_balance = float(account.get("balance") or 0)
        use_paper = self.paper.is_paper_mode(real_balance)

        if use_paper:
            result = self.paper.open_position(
                symbol=decision.symbol, side=decision.action,
                lot=decision.lot, entry=decision.entry,
                sl=decision.stop_loss, tp=decision.take_profit
            )
        elif self._mode == self.MODE_BINANCE and self.binance_exec:
            if decision.action == "BUY":
                result = await self.binance_exec.buy_async(
                    decision.symbol, decision.lot,
                    decision.stop_loss, decision.take_profit, comment,
                    signal_entry=decision.entry
                )
            else:
                result = await self.binance_exec.sell_async(
                    decision.symbol, decision.lot,
                    decision.stop_loss, decision.take_profit, comment,
                    signal_entry=decision.entry
                )
        else:
            # Libertex MT5 — ASOSIY
            if decision.action == "BUY":
                result = self.execution.buy(
                    decision.symbol, decision.lot,
                    decision.stop_loss, decision.take_profit, comment
                )
            else:
                result = self.execution.sell(
                    decision.symbol, decision.lot,
                    decision.stop_loss, decision.take_profit, comment
                )

        if result.success:
            self._trades_today += 1
            logger.info(f"✅ Savdo #{self._trades_today}: {decision.symbol} #{result.ticket}")

            # TXT trade log
            source_tag = "paper" if use_paper else ("binance" if self._mode == self.MODE_BINANCE else "libertex")
            trade_log.log_open(
                ticket=result.ticket,
                symbol=decision.symbol,
                side=decision.action,
                lot=decision.lot,
                entry=result.price or decision.entry,
                sl=decision.stop_loss,
                tp=decision.take_profit,
                tier=decision.tier,
                confidence=decision.confidence,
                rr=decision.rr_ratio,
                source=source_tag
            )

            # Trade history'ga yozish
            market = MARKETS.get(decision.symbol, {})
            source_tag2 = "paper" if use_paper else ("binance" if self._mode == self.MODE_BINANCE else "libertex")
            trade_rec = TradeRecord(
                ticket=result.ticket,
                symbol=decision.symbol,
                market_type=decision.market_type,
                category=market.get("category", decision.market_type),
                side=decision.action,
                lot=decision.lot,
                entry_price=decision.entry,
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
                confidence=decision.confidence,
                tier=decision.tier,
                whale_signal=decision.whale_involved,
                reason=decision.reason,
                source=source_tag2
            )
            await self.history.save_open(trade_rec)
            self._open_ticket_map[result.ticket] = {
                "symbol": decision.symbol,
                "entry": decision.entry,
                "sl": decision.stop_loss,
                "tp": decision.take_profit,
                "side": decision.action,
                "qty": decision.lot,
            }

            paper_tag = " [PAPER DEMO]" if use_paper else ""
            await self.telegram.send_signal(
                signal=decision.action,
                symbol=decision.symbol,
                market_type=decision.market_type,
                confidence=decision.confidence,
                entry=decision.entry,
                sl=decision.stop_loss,
                tp=decision.take_profit,
                lot=decision.lot,
                rr=decision.rr_ratio,
                tier=decision.tier,
                whale=decision.whale_involved,
                reason=decision.reason + paper_tag,
                cluster_score=decision.cluster_score,
                cluster_type=decision.cluster_type,
                poc=decision.poc,
                cvd_trend=decision.cvd_trend,
            )
        else:
            logger.error(f"❌ Savdo muvaffaqiyatsiz: {result.error}")

    # ─── POSITION MANAGEMENT ──────────────────────────────────────

    async def _manage_positions(self, balance: float):
        positions = self._get_positions()
        if not positions:
            return

        for pos in positions:
            ticket = pos["ticket"]
            profit  = pos["profit"]
            open_price = pos["open_price"]
            current    = pos.get("current_price", open_price)
            atr = await self._get_atr(pos["symbol"])

            if profit > 0:
                pip_profit = abs(current - open_price)
                if pip_profit >= atr * 0.5:
                    self.execution.set_break_even(ticket)

            if self._mode == self.MODE_MT5:
                self.execution.apply_trailing_stop(
                    ticket=ticket,
                    trail_pips=atr * 0.8,
                    step_pips=atr * 0.2
                )

    async def _get_atr(self, symbol: str) -> float:
        df = await self.market.get_ohlc_async(symbol, "M15", 20)
        if df is not None and "atr" in df.columns:
            return float(df["atr"].iloc[-1])
        return MARKETS.get(symbol, {}).get("pip", 0.01) * 20

    # ─── WHALE / AI / REPORTS ─────────────────────────────────────

    async def _check_whale_alerts(self, market_data: dict, balance: float):
        active = self._get_active_symbols(balance)
        crypto = [s for s in active
                  if MARKETS.get(s, {}).get("type") == "crypto"
                  and s in market_data]

        for symbol in crypto[:3]:
            df = market_data.get(symbol)
            if df is None:
                continue
            activity = await self.whale.analyze_whale_activity(symbol, df)

            last = self._last_whale_alert.get(symbol)
            if (activity.institutional_flow and
                    activity.confidence > 70 and
                    activity.signal.value != "NEUTRAL" and
                    last != activity.signal.value):

                self._last_whale_alert[symbol] = activity.signal.value
                logger.info(
                    f"🐋 WHALE! {symbol}: {activity.signal.value} | "
                    f"{activity.confidence:.1f}%"
                )
                await self.telegram.send_whale_alert(
                    symbol=symbol,
                    signal=activity.signal.value,
                    confidence=activity.confidence,
                    description=activity.description,
                    institutional=activity.institutional_flow
                )

    async def _ai_market_review(self, scan, account: dict):
        try:
            best = scan.best_signals[0] if scan.best_signals else None
            if not best:
                return
            summary = {
                "scanned": scan.total_scanned,
                "signals": scan.total_signals,
                "sentiment": scan.market_overview.get("sentiment"),
                "best_symbol": best.symbol,
                "best_confidence": best.confidence,
                "market_types": scan.market_overview.get("by_market_type", {}),
            }
            await self.ai.quick_review(summary, account)
        except Exception as e:
            logger.debug(f"AI review xato: {e}")

    async def _sync_closed_positions(self):
        """Yopilgan pozitsiyalarni tarixga yozish"""
        if not self._open_ticket_map:
            return
        current_positions = self._get_positions()
        current_tickets = {p["ticket"] for p in current_positions}

        for ticket, info in list(self._open_ticket_map.items()):
            if ticket not in current_tickets:
                entry = info["entry"]
                tp    = info["tp"]
                sl    = info["sl"]
                side  = info["side"]
                qty   = info.get("qty", 1.0)

                # Binance rejimida: SW-SL allaqachon qayta ishlagan
                # Bu yerda faqat history save + map tozalash (Telegram yuborilmaydi)
                if self._mode == self.MODE_BINANCE:
                    # Agar monitor_sl_tp() yurib ketgan bo'lsa, ticket allaqachon o'chirilgan.
                    # Bu yerga faqat manual/external close uchun tushamiz.
                    try:
                        from engines.binance_executor import SYMBOL_MAP
                        import aiohttp
                        bn_sym = SYMBOL_MAP.get(info["symbol"], "")
                        last_price = entry
                        if bn_sym:
                            async with aiohttp.ClientSession() as s:
                                async with s.get(
                                    f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={bn_sym}",
                                    timeout=aiohttp.ClientTimeout(total=3)
                                ) as resp:
                                    if resp.status == 200:
                                        pdata = await resp.json()
                                        last_price = float(pdata.get("price", entry))
                    except Exception:
                        last_price = entry

                    tp_dist = abs(last_price - tp)
                    sl_dist = abs(last_price - sl)
                    if tp_dist < sl_dist:
                        reason = "TAKE_PROFIT"
                        profit = abs(last_price - entry) * qty * (1 if side == "BUY" else -1)
                    else:
                        reason = "STOP_LOSS"
                        profit = abs(last_price - entry) * qty * (-1 if side == "BUY" else 1)

                    await self.history.save_close(ticket, last_price, profit, reason)
                    del self._open_ticket_map[ticket]
                    logger.info(f"📋 Sync: #{ticket} {info['symbol']} {reason} | P/L: {profit:+.4f}")
                    continue

                # MT5 mode: haqiqiy close price ni aniqlaymiz
                try:
                    last_price = entry
                    sl_dist = abs(last_price - sl)
                    tp_dist = abs(last_price - tp)
                    entry_dist = abs(last_price - entry)

                    if tp_dist < sl_dist and entry_dist > 0:
                        reason = "TAKE_PROFIT"
                        profit_sign = 1
                    elif sl_dist < tp_dist and entry_dist > 0:
                        reason = "STOP_LOSS"
                        profit_sign = -1
                    else:
                        reason = "MANUAL"
                        profit_sign = 1 if last_price > entry else -1

                    profit = abs(last_price - entry) * qty * profit_sign

                    await self.history.save_close(ticket, last_price, profit, reason)
                    del self._open_ticket_map[ticket]

                    logger.info(f"📋 Trade yopildi: #{ticket} {info['symbol']} | {reason} | P/L: {profit:+.4f}")

                    if reason == "STOP_LOSS":
                        trade_log.log_sl_hit(ticket, info["symbol"], last_price, profit)
                    elif reason == "TAKE_PROFIT":
                        trade_log.log_tp_hit(ticket, info["symbol"], last_price, profit)
                    else:
                        trade_log.log_close(
                            ticket=ticket, symbol=info["symbol"], side=side,
                            entry=entry, close_price=last_price, profit=profit, reason=reason
                        )

                    await self.telegram.send_trade_close(
                        symbol=info["symbol"], side=side, entry=entry,
                        close_price=last_price, profit=profit, reason=reason, ticket=ticket
                    )
                except Exception as e:
                    logger.debug(f"Sync close xato #{ticket}: {e}")
                    del self._open_ticket_map[ticket]

    async def execute_manual_trade(self, symbol: str, side: str) -> str:
        """
        Telegram /buy BTCUSD yoki /sell ETHUSD buyrug'i uchun.
        Signal skanerlash → Smart SL/TP → paper yoki real bajarish.
        """
        # 1. Ma'lumot olish
        df = await self.market.get_ohlc_async(symbol, "M15", 200)
        if df is None or len(df) < 50:
            return f"❌ {symbol} uchun ma'lumot yo'q"

        # 2. Signal skanerlash
        account = await self._get_account()
        balance = max(float(account.get("balance") or 0), 10.0)

        scan = await self.scanner.scan_all({symbol: df}, balance)
        risk_status = self.risk.check_risk(balance, balance, 0)

        from engines.market_scanner import MarketSignal

        atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else float(df["close"].iloc[-1]) * 0.005
        price = float(df["close"].iloc[-1])

        if scan.best_signals:
            sig = scan.best_signals[0]
            manual_sig = MarketSignal(
                symbol=sig.symbol, market_type=sig.market_type,
                signal=side, confidence=sig.confidence,
                entry=sig.entry, stop_loss=sig.stop_loss, take_profit=sig.take_profit,
                rr_ratio=sig.rr_ratio, liquidity_score=sig.liquidity_score,
                smc_score=sig.smc_score, whale_score=sig.whale_score,
                technical_score=sig.technical_score, total_score=sig.total_score,
                trend=sig.trend, volatility=sig.volatility, timeframe=sig.timeframe,
                reason=f"Manual {side} | " + sig.reason,
                whale_activity=sig.whale_activity
            )
        else:
            sl = price - atr * 1.5 if side == "BUY" else price + atr * 1.5
            tp = price + atr * 3.0  if side == "BUY" else price - atr * 3.0
            mkt = MARKETS.get(symbol, {})
            manual_sig = MarketSignal(
                symbol=symbol, market_type=mkt.get("type", "crypto"),
                signal=side, confidence=55.0,
                entry=price, stop_loss=round(sl, 5), take_profit=round(tp, 5),
                rr_ratio=2.0, liquidity_score=0, smc_score=0,
                whale_score=0, technical_score=0, total_score=0,
                trend="UNKNOWN", volatility="normal", timeframe="M15",
                reason=f"Manual {side} — ATR SL/TP",
                whale_activity=None
            )

        # 3. Bajarish
        await self._process_signal(manual_sig, account, risk_status, {symbol: df})

        account2 = await self._get_account()
        balance2 = float(account2.get("balance") or 0)
        is_paper = self.paper.is_paper_mode(balance2)
        mode = "📝 PAPER" if is_paper else "💰 REAL"

        return (
            f"✅ {mode} {side} {symbol}\n"
            f"Entry: {manual_sig.entry:,.4f}\n"
            f"SL: {manual_sig.stop_loss:,.4f}\n"
            f"TP: {manual_sig.take_profit:,.4f}\n"
            f"Ishonch: {manual_sig.confidence:.1f}%"
        )

    async def _check_orderbook_alerts(self, signals: list):
        """Orderbook / Iceberg alertlarni tekshirish"""
        for signal in signals:
            try:
                ob_state = await self.orderbook.analyze(signal.symbol, signal.entry)
                if ob_state.icebergs:
                    logger.info(
                        f"🧊 ICEBERG: {signal.symbol} | "
                        f"{ob_state.icebergs[0].side} @ {ob_state.icebergs[0].price:.0f} "
                        f"${ob_state.icebergs[0].usd_value/1e6:.2f}M"
                    )
                    await self.telegram.send_orderbook_alert(signal.symbol, ob_state)

                big_trades = await self.orderbook.get_big_trades(signal.symbol, 100_000)
                if big_trades:
                    logger.info(
                        f"💥 BIG TRADE: {signal.symbol} "
                        f"{big_trades[0].side} ${big_trades[0].usd_value/1e3:.0f}k"
                    )
            except Exception as e:
                logger.debug(f"OB alert xato: {e}")

    async def _runtime_sl_check(self):
        """Ishlaydigan paytda ham SL borligini tekshiradi (fon himoyasi)"""
        try:
            if self._mode == self.MODE_MT5:
                closed = self.execution.verify_all_sl()
                if closed > 0:
                    logger.warning(f"⚠️  Runtime: MT5 SLsiz {closed} pozitsiya yopildi")
                    await self.telegram.send(
                        f"⚠️ <b>Runtime SL tekshiruvi</b>\n"
                        f"SLsiz <b>{closed}</b> ta pozitsiya avtomatik yopildi!"
                    )
            # Binance mode: software SL monitor_sl_tp() orqali har siklda ishlaydi
            # ensure_sl_orders() kerak emas (exchange SL yo'q, -4120)
        except Exception as e:
            logger.debug(f"Runtime SL tekshiruv xato: {e}")

    async def _handle_risk_breach(self, risk_status):
        if risk_status.drawdown_pct >= 18:
            logger.warning("🚨 Kritik Drawdown! Barcha pozitsiyalar yopilmoqda...")
            self.execution.close_all_positions("Emergency")
            await self.telegram.send_risk_alert(
                f"🚨 EMERGENCY! Drawdown {risk_status.drawdown_pct:.1f}%",
                risk_status.daily_loss_pct,
                risk_status.drawdown_pct
            )

    async def _hourly_report(self, account: dict, risk_status):
        balance = account.get("balance", 0)
        stats = self.risk.get_statistics(balance)
        next_tier = stats.get("next_tier_target", {})
        mode_str = "MT5 Mode" if self._mode == self.MODE_MT5 else "Binance Mode"

        logger.info(
            f"\n📊 SOATLIK HISOBOT [{mode_str}]\n"
            f"   Balans: ${balance:.2f} | Tier: {risk_status.tier.upper()}\n"
            f"   Bugungi savdolar: {self._trades_today}\n"
            f"   Win rate: {stats.get('win_rate', 0):.1f}%\n"
            f"   Keyingi tier: ${next_tier.get('target_amount', 0)} "
            f"({next_tier.get('progress_pct', 0):.1f}%)"
        )

    # ─── START ────────────────────────────────────────────────────

    async def start(self):
        if not await self.initialize():
            return

        # Oldingi holatni yuklash (agar mavjud bo'lsa)
        self._load_state()

        self._running = True
        account = await self._get_account()
        balance = account.get("balance", 0)
        if self._mode == self.MODE_BINANCE:
            mode_name = "Binance Futures"
        else:
            mode_name = f"Libertex MT5 ({config.mt5.broker})"

        trade_log.log_start(
            balance=balance,
            mode=mode_name,
            tier=config.risk.get_for_balance(balance)["tier"]
        )

        await self.telegram.send_startup_ultra(
            balance=balance,
            server=account.get("server", mode_name),
            tier=config.risk.get_for_balance(balance)["tier"],
            active_markets=len(self._get_active_symbols(balance))
        )

        logger.info(f"🔄 Multi-Market loop boshlandi [{mode_name}]...")

        # Whale WebSocket — faqat Binance yoqilganda yoki crypto uchun
        active = self._get_active_symbols(balance)
        if config.enable_binance:
            asyncio.create_task(
                self.whale.start_ws_monitoring(active, self._on_whale_trade)
            )
        else:
            logger.info("🐋 Whale WS o'chiq (Libertex rejimida MT5 ma'lumotlari ishlatiladi)")

        # Telegram command polling — init (eski xabarlarni o'tkazish)
        await self.telegram.init_polling(orchestrator=self)

        _last_cycle_time = 0
        _last_sl_check_time = 0

        while self._running:
            try:
                import time
                now = time.time()

                # Har 1 soniyada Telegram buyruqlarini tekshirish
                await self.telegram.poll_once()

                # ── Har 10 soniyada tezkor SL monitoring (slippage oldini olish) ──
                if (self._mode == self.MODE_BINANCE and self.binance_exec
                        and now - _last_sl_check_time >= 10):
                    _last_sl_check_time = now
                    try:
                        closed = await self.binance_exec.monitor_sl_tp()
                        for c in closed:
                            info = self._open_ticket_map.get(c["ticket"], {})
                            side  = c.get("side", info.get("side", "BUY"))
                            entry = c.get("entry", info.get("entry", c.get("close_price", 0)))
                            trade_log.log_close(
                                ticket=c["ticket"], symbol=c["symbol"], side=side,
                                entry=entry, close_price=c["close_price"],
                                profit=c["profit"], reason=c["reason"]
                            )
                            self.risk.record_trade_result(c["profit"])
                            self._open_ticket_map.pop(c["ticket"], None)
                            await self.telegram.send_trade_close(
                                symbol=c["symbol"], side=side, entry=entry,
                                close_price=c["close_price"], profit=c["profit"],
                                reason=c["reason"], ticket=c["ticket"]
                            )
                            if c["reason"] == "STOP_LOSS":
                                self._sl_cooldown[c["symbol"]] = time.time()
                                logger.info(f"⏳ {c['symbol']}: 30 daqiqa cooldown (SL olgandan keyin)")
                    except Exception as _e:
                        logger.debug(f"Tezkor SL check xato: {_e}")

                # Har 60 soniyada to'liq bozor siklini ishlatish
                if now - _last_cycle_time >= 60:
                    _last_cycle_time = now
                    await self.run_cycle()

                await asyncio.sleep(1)

            except KeyboardInterrupt:
                logger.info("🛑 Foydalanuvchi to'xtatdi — state saqlanmoqda...")
                trade_log.log_stop("Foydalanuvchi to'xtatdi (Ctrl+C)")
                self._save_state()
                break
            except Exception as e:
                logger.error(f"Loop xatosi: {e}", exc_info=True)
                self._save_state()
                await asyncio.sleep(10)

        self._save_state()
        if self._mode == self.MODE_MT5 and self.market.mt5_connected:
            self.market.disconnect_mt5()
        logger.info("✅ GoldAI Ultra to'xtatildi")

    async def _on_whale_trade(self, data: dict):
        usd_value = data.get("usd_value", 0)
        if usd_value >= 500_000:
            logger.info(
                f"🐋 MEGA WHALE! {data.get('symbol')} {data.get('side')} "
                f"${usd_value:,.0f}"
            )

    # ─── STATE PERSISTENCE ────────────────────────────────────────

    def _save_state(self):
        """Joriy holatni faylga saqlash — qayta ishga tushganda davom etadi"""
        try:
            state = {
                "saved_at": datetime.utcnow().isoformat(),
                "cycle_count": self._cycle_count,
                "trades_today": self._trades_today,
                "risk_start_balance": self.risk._start_balance,
                "risk_peak_balance": self.risk._peak_balance,
                "risk_trade_count": self.risk._trade_count,
                "risk_win_count": self.risk._win_count,
                "risk_loss_count": self.risk._loss_count,
                "open_ticket_map": {
                    str(k): v for k, v in self._open_ticket_map.items()
                },
            }
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.debug(f"💾 State saqlandi: {self._state_file}")
        except Exception as e:
            logger.warning(f"State saqlash xatosi: {e}")

    def _load_state(self):
        """Oldingi holatni yuklash"""
        if not os.path.exists(self._state_file):
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            self._cycle_count = state.get("cycle_count", 0)
            self._trades_today = state.get("trades_today", 0)

            if state.get("risk_start_balance"):
                self.risk._start_balance = state["risk_start_balance"]
            if state.get("risk_peak_balance"):
                self.risk._peak_balance = state["risk_peak_balance"]
            if state.get("risk_trade_count"):
                self.risk._trade_count = state["risk_trade_count"]
            if state.get("risk_win_count"):
                self.risk._win_count = state["risk_win_count"]
            if state.get("risk_loss_count"):
                self.risk._loss_count = state["risk_loss_count"]

            ticket_map = state.get("open_ticket_map", {})
            self._open_ticket_map = {int(k): v for k, v in ticket_map.items()}

            saved_at = state.get("saved_at", "noma'lum")
            logger.info(
                f"📂 Oldingi holat yuklandi: {saved_at} | "
                f"Sikl#{self._cycle_count} | Savdolar:{self._trades_today}"
            )
        except Exception as e:
            logger.warning(f"State yuklash xatosi: {e} — yangi sessiya boshlanadi")

    async def stop_async(self):
        self._running = False
        self._save_state()
        # Binance pozitsiyalarini YOPMAYMIZ — restart bo'lganda load_positions_from_binance()
        # ularni software SL bilan qayta yuklaydi (foydalanuvchi talabi: persistent positions)
        if self._mode == self.MODE_BINANCE and self.binance_exec:
            n = len(self.binance_exec._positions)
            if n > 0:
                logger.info(f"💾 {n} ta pozitsiya Binance da ochiq — restart bo'lganda SW-SL restore qilinadi")

    def stop(self):
        self._running = False
        self._save_state()


if __name__ == "__main__":
    bot = UltraOrchestrator()
    asyncio.run(bot.start())
