"""
GoldAI Ultra — Enhanced Telegram Bot
Multi-market signal va whale alertlari + Interactive Command Handler
"""

import asyncio
import os
import ssl
import aiohttp
from datetime import datetime
from core.config import config
from core.logger import logger

# TLS verification is secure by default. Set TELEGRAM_VERIFY_SSL=false only
# for a controlled corporate proxy that replaces certificates.
_SSL_CTX = None
if os.getenv("TELEGRAM_VERIFY_SSL", "true").strip().lower() in {"0", "false", "no"}:
    _SSL_CTX = False


class TelegramBot:

    MARKET_EMOJI = {
        "forex": "💱", "crypto": "₿", "commodity": "🏅",
        "stock": "📈", "index": "📊", "precious_metal": "🥇"
    }

    COMMANDS_MENU = """
🤖 <b>GOLDAI ULTRA BOT — Premium</b>

📊 <b>Monitoring:</b>
/status — Bot holati va balans
/trades — Hozirgi ochiq savdolar (live P/L)
/positions — Ochiq pozitsiyalar
/history — So'nggi 10 ta savdo
/stats — To'liq statistika

🌐 <b>Tahlil:</b>
/market — Fear&amp;Greed, yangiliklar
/orderbook [SYMBOL] — Order book (default: BTC)
/cvd — Cumulative Volume Delta
/bigtrades [SYMBOL] — Katta savdolar $100k+ (default: BTC)
/scan [SYMBOL] — AI signal tahlili

🎮 <b>Savdo boshqaruvi:</b>
/buy SYMBOL — Qo'lda BUY signal
/sell SYMBOL — Qo'lda SELL signal
/auto — Avtonomiya rejimi on/off
/closeall — Barcha pozitsiyalarni yopish

🤖 <b>AI Suhbat:</b>
/ask [savol] — AI trading tahlil (DeepSeek/Gemini/OpenAI failover)
<i>Yoki oddiygina savol yozing — AI javob beradi</i>

ℹ️ <b>Boshqa:</b>
/help — Buyruqlar ro'yxati
/stop — Botni to'xtatish
"""

    def __init__(self):
        self.token = config.telegram.token
        self.chat_id = config.telegram.chat_id
        self.base = f"https://api.telegram.org/bot{self.token}"
        self._ok = bool(self.token and self.chat_id)
        self._last_update_id = 0
        self._orchestrator = None   # start_polling() da o'rnatiladi

    def _session(self):
        return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=_SSL_CTX))

    async def send(self, text: str) -> bool:
        if not self._ok:
            return False
        try:
            async with self._session() as s:
                async with s.post(f"{self.base}/sendMessage", json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    return r.status == 200
        except Exception as e:
            logger.debug(f"Telegram: {e}")
            return False

    # ─── POLLING LOOP ─────────────────────────────────────────────

    async def init_polling(self, orchestrator=None):
        """
        Ishga tushganda bir marta chaqiriladi:
        orchestrator'ni saqlaydi + eski xabarlarni o'tkazib yuboradi
        """
        self._orchestrator = orchestrator
        if not self._ok:
            return
        await self._skip_old_updates()
        logger.info(f"🤖 Telegram polling tayyor (offset={self._last_update_id})")

    async def poll_once(self):
        """
        Har siklda bir marta chaqiriladi — yangi buyruqlarni tekshiradi.
        Har bir xabar mustaqil try/except — biri xato bo'lsa qolganlar bajariladi.
        """
        if not self._ok:
            return
        try:
            updates = await self._get_updates()
        except Exception:
            return

        for upd in updates:
            # Update ID ni AVVAL yangilash — xato bo'lsa ham qayta kelmaydi
            uid = upd.get("update_id", 0)
            self._last_update_id = max(self._last_update_id, uid + 1)
            try:
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    await self._handle_message(msg)
            except Exception as e:
                logger.warning(f"Message handler xato (uid={uid}): {e}")

    async def start_polling(self, orchestrator=None):
        """Eski metod — orchestrator background task uchun (fallback)"""
        await self.init_polling(orchestrator)
        while True:
            await self.poll_once()
            await asyncio.sleep(2)

    async def _skip_old_updates(self):
        """Bot qayta ishga tushganda eski xabarlarni o'tkazib yuborish"""
        try:
            async with self._session() as s:
                async with s.get(
                    f"{self.base}/getUpdates",
                    params={"offset": -1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        results = data.get("result", [])
                        if results:
                            self._last_update_id = results[-1]["update_id"] + 1
        except Exception as e:
            logger.debug(f"Skip old updates xato: {e}")

    async def _get_updates(self) -> list:
        try:
            async with self._session() as s:
                async with s.get(
                    f"{self.base}/getUpdates",
                    params={"offset": self._last_update_id, "limit": 20, "timeout": 1},
                    timeout=aiohttp.ClientTimeout(total=4)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("result", [])
        except Exception:
            pass  # expected network noise — not logged to avoid flooding
        return []

    async def _handle_message(self, msg: dict):
        """Kelgan xabarni qayta ishlash"""
        text = msg.get("text", "").strip()
        from_id = str(msg.get("chat", {}).get("id", ""))
        username = msg.get("from", {}).get("username", "?")

        # Non-command xabar → AI chat (faqat ruxsatlangan foydalanuvchilardan)
        if not text.startswith("/"):
            if from_id == str(self.chat_id) and self._orchestrator:
                await self._cmd_ai_chat(msg, text)
            return

        logger.info(f"📨 Telegram buyruq: {text} (dan: @{username} / {from_id})")

        # Faqat ruxsatlangan chat_id dan
        if from_id != str(self.chat_id):
            logger.warning(f"Noma'lum foydalanuvchi: {from_id}")
            await self._reply(msg, "❌ Ruxsat yo'q")
            return

        cmd = text.split()[0].lower().split("@")[0]
        args = text.split()[1:]

        handlers = {
            "/start":      self._cmd_start,
            "/help":       self._cmd_start,
            "/status":     self._cmd_status,
            "/trades":     self._cmd_trades,
            "/positions":  self._cmd_positions,
            "/history":    self._cmd_history,
            "/stats":      self._cmd_stats,
            "/market":     self._cmd_market,
            "/orderbook":  self._cmd_orderbook,
            "/cvd":        self._cmd_cvd,
            "/bigtrades":  self._cmd_bigtrades,
            "/bigrades":   self._cmd_bigtrades,
            "/scan":       self._cmd_scan,
            "/buy":        self._cmd_manual_buy,
            "/sell":       self._cmd_manual_sell,
            "/auto":       self._cmd_auto,
            "/closeall":   self._cmd_closeall,
            "/stop":       self._cmd_stop,
            "/ask":        self._cmd_ask,
            "/ai":         self._cmd_ask,
        }

        handler = handlers.get(cmd)
        if handler:
            try:
                # 15 soniyadan ko'p davom etsa timeout
                await asyncio.wait_for(handler(msg, args), timeout=15)
                logger.info(f"✅ Buyruq bajarildi: {cmd}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout: {cmd}")
                await self._reply(msg, f"⏱️ {cmd} juda ko'p vaqt oldi, qayta urining")
            except Exception as e:
                logger.error(f"Handler xato [{cmd}]: {e}", exc_info=True)
                await self._reply(msg, f"⚠️ Xato: {type(e).__name__}: {e}")
        else:
            await self._reply(msg, f"❓ Noma'lum buyruq: {cmd}\n{self.COMMANDS_MENU}")

    def _normalize_symbol(self, raw: str) -> str:
        """ETH → ETHUSD, ETHUSDT → ETHUSD, ETHUSD → ETHUSD"""
        raw = raw.upper().replace("USDT", "USD").replace("/", "")
        known = ["BTCUSD","ETHUSD","SOLUSD","BNBUSD","XRPUSD",
                 "ADAUSD","DOTUSD","AVAXUSD","MATICUSD","LINKUSD",
                 "EURUSD","GBPUSD","USDJPY","XAUUSD"]
        if raw in known:
            return raw
        if not raw.endswith("USD"):
            return raw + "USD"
        return raw

    async def _reply(self, msg: dict, text: str):
        """Xabarga javob berish"""
        chat_id = msg.get("chat", {}).get("id")
        try:
            async with self._session() as s:
                await s.post(f"{self.base}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }, timeout=aiohttp.ClientTimeout(total=8))
        except Exception as e:
            logger.debug(f"Reply xato: {e}")

    # ─── COMMAND HANDLERS ─────────────────────────────────────────

    async def _cmd_start(self, msg, args):
        await self._reply(msg, self.COMMANDS_MENU)

    async def _cmd_status(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        try:
            account = await asyncio.wait_for(o._get_account(), timeout=4)
        except Exception:
            account = {}
        balance  = float(account.get("balance") or 0)
        equity   = float(account.get("equity") or balance)
        mode     = "🟢 Libertex MT5" if o._mode != "binance" else "🟡 Binance Mode"
        positions = o._get_positions()

        from core.config import config as cfg
        tier = cfg.risk.get_for_balance(balance).get("tier", "micro").upper()

        blackout, bl_reason = o.news.is_blackout()
        fg     = getattr(o.news, "_fear_greed", 50)
        fg_lbl = getattr(o.news, "_fg_label", "Unknown")

        text = (
            f"📊 <b>BOT HOLATI</b>\n\n"
            f"{mode}\n"
            f"💰 Balans: <code>${balance:.2f}</code>\n"
            f"📊 Equity: <code>${equity:.2f}</code>\n"
            f"🏅 Tier: <b>{tier}</b>\n"
            f"📈 Ochiq: <code>{len(positions)}</code> ta pozitsiya\n"
            f"🔄 Sikllar: <code>{o._cycle_count}</code>\n"
            f"📅 Bugungi savdolar: <code>{o._trades_today}</code>\n\n"
            f"😱 Fear&amp;Greed: <b>{fg}</b> — {fg_lbl}\n"
            f"⏸️ Blackout: {'🔴 ' + bl_reason if blackout else '🟢 Yoq'}\n\n"
            f"⏰ {datetime.utcnow().strftime('%H:%M UTC')}"
        )
        await self._reply(msg, text)

    async def _cmd_positions(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        positions = o._get_positions()
        if not positions:
            await self._reply(msg, "📭 Hozirda ochiq pozitsiyalar yo'q")
            return

        lines = ["📈 <b>OCHIQ POZITSIYALAR</b>", ""]
        for p in positions:
            side = p.get("side") or p.get("type", "?")
            icon = "🟢" if "BUY" in str(side).upper() else "🔴"
            profit = p.get("profit", 0)
            pnl_icon = "📈" if profit >= 0 else "📉"
            lines.append(
                f"{icon} <b>{p.get('symbol')}</b> {str(side).upper()}\n"
                f"   Entry: <code>{p.get('open_price', '?')}</code> | "
                f"Lot: <code>{p.get('lot', p.get('volume', '?'))}</code>\n"
                f"   P/L: {pnl_icon} <code>${profit:+.2f}</code>"
            )
        await self._reply(msg, "\n".join(lines))

    async def _cmd_history(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        records = await o.history.get_history(limit=10)
        if not records:
            await self._reply(msg, "📋 Savdolar tarixi bo'sh — hali savdo qilinmagan")
            return

        lines = ["📋 <b>SO'NGGI SAVDOLAR</b>", ""]
        total_pnl = 0
        for r in records:
            profit = float(r.get("profit") or 0)
            total_pnl += profit
            pnl_icon = "✅" if profit >= 0 else "❌"
            side = r.get("side", "")
            dir_icon = "📈" if side == "BUY" else "📉"
            reason_icons = {
                "TAKE_PROFIT": "🎯", "STOP_LOSS": "🛑", "MANUAL": "🔵"
            }
            reason_icon = reason_icons.get(r.get("close_reason", ""), "⚪")

            close_t = r.get("close_time", "")
            ts = close_t.strftime("%m/%d %H:%M") if hasattr(close_t, "strftime") else str(close_t)[:16]

            lines.append(
                f"{pnl_icon} {dir_icon} <b>{r.get('symbol')}</b> "
                f"{reason_icon} <code>${profit:+.2f}</code> "
                f"<i>{ts}</i>\n"
                f"   Entry:{r.get('entry_price','?')} → Close:{r.get('close_price','?')}"
            )

        pnl_icon = "📈" if total_pnl >= 0 else "📉"
        lines.append(f"\n{pnl_icon} <b>Jami P/L:</b> <code>${total_pnl:+.2f}</code>")
        await self._reply(msg, "\n".join(lines))

    async def _cmd_stats(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        await self._reply(msg, "⏳ Statistika yuklanmoqda...")
        stats = await o.history.get_stats()
        today = await o.history.get_today_stats()

        if stats is None:
            await self._reply(msg, "📊 Hali yetarli savdo ma'lumoti yo'q")
            return

        wr_icon = "🟢" if stats.win_rate >= 55 else ("🟡" if stats.win_rate >= 45 else "🔴")
        pnl_icon = "📈" if stats.total_profit >= 0 else "📉"

        today_pnl = float(today.get("pnl") or 0)
        today_total = int(today.get("total") or 0)
        today_wins  = int(today.get("wins") or 0)
        today_sl    = int(today.get("sl_hits") or 0)
        today_tp    = int(today.get("tp_hits") or 0)

        lines = [
            "📊 <b>TO'LIQ STATISTIKA</b>", "",
            f"📌 Jami savdolar: <code>{stats.total}</code>",
            f"{wr_icon} Win Rate: <code>{stats.win_rate:.1f}%</code>",
            f"✅ Yutish: <code>{stats.wins}</code>  ❌ Yo'qotish: <code>{stats.losses}</code>",
            "",
            f"{pnl_icon} Jami P/L: <code>${stats.total_profit:+.2f}</code>",
            f"📐 O'rtacha: <code>${stats.avg_profit:+.2f}</code>",
            f"🏆 Eng yaxshi: <code>${stats.best_trade:+.2f}</code>",
            f"💔 Eng yomon: <code>${stats.worst_trade:+.2f}</code>",
            "",
            f"📅 <b>Bugun:</b>",
            f"   Savdolar: {today_total} | Yutish: {today_wins}",
            f"   TP: {today_tp} | SL: {today_sl} | P/L: ${today_pnl:+.2f}",
        ]

        if stats.by_symbol:
            lines.append("\n🔝 <b>Symbol natijalari:</b>")
            for sym, d in list(stats.by_symbol.items())[:5]:
                wr = d.get("wr", 0)
                pr = d.get("profit", 0)
                icon = "📈" if pr >= 0 else "📉"
                lines.append(f"  {icon} {sym}: WR {wr:.0f}% | ${pr:+.2f}")

        lines.append(f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        await self._reply(msg, "\n".join(lines))

    async def _cmd_market(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        await self._reply(msg, "⏳ Bozor ma'lumotlari yuklanmoqda...")
        sent = await o.news.get_sentiment(["BTC", "ETH", "SOL"])

        fg = sent.fear_greed_index
        fg_icon = "😱" if fg < 25 else ("😰" if fg < 45 else ("😐" if fg < 55 else ("😁" if fg < 75 else "🤑")))

        ns = sent.news_sentiment
        ns_icon = "📈" if ns > 0.2 else ("📉" if ns < -0.2 else "➡️")

        lines = [
            "🌐 <b>BOZOR HOLATI</b>", "",
            f"{fg_icon} Fear &amp; Greed: <b>{fg}</b> — {sent.fear_greed_label}",
            f"{ns_icon} Yangiliklar: <code>{ns:+.2f}</code>",
            f"⏸️ Blackout: {'🔴 ' + sent.blackout_reason if sent.blackout_active else '🟢 Yoq'}",
        ]

        if sent.upcoming_events:
            lines.append("\n📅 <b>Yaqin iqtisodiy hodisalar:</b>")
            for ev in sent.upcoming_events[:4]:
                icon = "🔴" if ev.impact == "High" else "🟡"
                lines.append(f"  {icon} {ev.title} ({ev.currency}) — {ev.minutes_away} daqiqa")

        news_report = o.news.format_telegram_report()
        lines.append(f"\n{news_report}")
        await self._reply(msg, "\n".join(lines))

    async def _cmd_orderbook(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        # Libertex rejimida Binance order book yo'q — MT5 cluster ishlatiladi
        from core.config import config as _cfg
        if not _cfg.enable_binance:
            await self._reply(msg,
                "ℹ️ <b>Order Book — Libertex rejimi</b>\n\n"
                "Binance order book faqat <code>ENABLE_BINANCE=true</code> da ishlaydi.\n"
                "Libertex MT5 da buyruq stakani mavjud emas — o'rniga:\n"
                "• V3 Cluster (POC/VAH/VAL)\n"
                "• MT5 tick_volume tahlili\n"
                "ishlatiladi.\n\n"
                "Signal uchun: <code>/scan BTCUSD</code>"
            )
            return

        symbol = args[0].upper() if args else "BTCUSD"
        if "BTC" in symbol and "USD" not in symbol:
            symbol = symbol + "USD"

        await self._reply(msg, f"⏳ {symbol} order book yuklanmoqda...")

        try:
            # Joriy narxni olish — Binance faqat enable_binance da
            from engines.binance_executor import SYMBOL_MAP
            bn_sym = SYMBOL_MAP.get(symbol, "BTCUSDT")
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={bn_sym}",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    pdata = await r.json()
                    price = float(pdata.get("price", 0))

            ob_state = await o.orderbook.analyze(symbol, price)
            cvd = await o.orderbook.get_cvd(symbol)
            big = await o.orderbook.get_big_trades(symbol, 100_000)

            text = o.orderbook.format_ob_report(ob_state, cvd, big)
            await self._reply(msg, text)

        except Exception as e:
            await self._reply(msg, f"⚠️ OrderBook xato: {e}")

    async def _cmd_cvd(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        from core.config import config as _cfg
        if not _cfg.enable_binance:
            await self._reply(msg,
                "ℹ️ <b>CVD — Libertex rejimi</b>\n\n"
                "CVD (Binance aggTrades) faqat <code>ENABLE_BINANCE=true</code> da.\n"
                "Libertex da MT5 volume + V3 cluster CVD o'rnini bosadi.\n"
                "Tahlil uchun: <code>/scan BTCUSD</code>"
            )
            return

        symbols = ["BTCUSD", "ETHUSD"]
        lines = ["📊 <b>CUMULATIVE VOLUME DELTA</b>", ""]

        for sym in symbols:
            cvd = await o.orderbook.get_cvd(sym)
            trend_icon = "📈" if cvd.trend == "BULLISH" else ("📉" if cvd.trend == "BEARISH" else "➡️")
            lines.append(
                f"{trend_icon} <b>{sym}</b>: CVD <code>{cvd.cvd:+.0f}</code> | "
                f"1m:<code>{cvd.delta_1m:+.0f}</code> | "
                f"5m:<code>{cvd.delta_5m:+.0f}</code> | "
                f"{cvd.trend}"
            )

        lines.append(f"\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}")
        await self._reply(msg, "\n".join(lines))

    async def _cmd_bigtrades(self, msg, args):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        from core.config import config as _cfg
        if not _cfg.enable_binance:
            await self._reply(msg,
                "ℹ️ <b>Big Trades — Libertex rejimi</b>\n\n"
                "Binance $100k+ savdolar faqat <code>ENABLE_BINANCE=true</code> da.\n"
                "Libertex da whale tahlili MT5 tick volume + cluster orqali qilinadi.\n"
                "Tahlil uchun: <code>/scan BTCUSD</code>"
            )
            return

        # Ixtiyoriy symbol: /bigtrades ETHUSD yoki /bigtrades ETH
        raw = args[0].upper() if args else "BTCUSD"
        symbol = self._normalize_symbol(raw)
        await self._reply(msg, f"⏳ {symbol} katta savdolar yuklanmoqda...")
        big = await o.orderbook.get_big_trades(symbol, 100_000)

        if not big:
            await self._reply(msg, f"📭 {symbol} da $100k+ savdo topilmadi\n\nMavjud: BTCUSD ETHUSD SOLUSD BNBUSD XRPUSD")
            return

        total_buy  = sum(t.usd_value for t in big if t.side == "BUY")
        total_sell = sum(t.usd_value for t in big if t.side == "SELL")
        pressure = "🟢 BUY bosimi" if total_buy > total_sell * 1.3 else \
                   ("🔴 SELL bosimi" if total_sell > total_buy * 1.3 else "⚪ Teng")

        lines = [
            f"💥 <b>KATTA SAVDOLAR: {symbol}</b>",
            f"{pressure} | Buy: ${total_buy/1e6:.2f}M | Sell: ${total_sell/1e6:.2f}M",
            ""
        ]
        for t in big[:8]:
            icon = "🟢" if t.side == "BUY" else "🔴"
            ts = t.timestamp[11:16]
            lines.append(
                f"{icon} {t.side} <code>${t.usd_value/1e3:.0f}k</code> "
                f"@ <code>{t.price:,.2f}</code> {ts}"
            )
        lines.append(f"\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}")
        await self._reply(msg, "\n".join(lines))

    async def _cmd_trades(self, msg, args):
        """Hozirgi barcha ochiq savdolar — live P/L bilan"""
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        positions = o._get_positions()
        if not positions:
            mode_str = "📝 PAPER DEMO" if True else "💰 Real"
            auto_str = "🤖 AUTO" if getattr(o, '_auto_mode', True) else "🖐️ MANUAL"
            await self._reply(msg,
                f"📭 <b>Hozirda ochiq savdo yo'q</b>\n\n"
                f"Rejim: {mode_str} | {auto_str}\n"
                f"Sikllar: {o._cycle_count}"
            )
            return

        lines = [f"📈 <b>OCHIQ SAVDOLAR ({len(positions)} ta)</b>", ""]
        total_pnl = 0
        for p in positions:
            profit = float(p.get("profit") or 0)
            total_pnl += profit
            side = str(p.get("side") or "").upper()
            icon = "🟢" if "BUY" in side else "🔴"
            pnl_icon = "📈" if profit >= 0 else "📉"
            paper = " 📝" if p.get("is_paper") else ""
            entry = p.get("open_price") or p.get("entry_price", 0)
            cur = p.get("current_price", entry)
            sl = p.get("stop_loss", 0)
            tp = p.get("take_profit", 0)
            lines.append(
                f"{icon} <b>{p.get('symbol')}</b>{paper} {side}\n"
                f"   Entry: <code>{entry:,.4f}</code> → Now: <code>{cur:,.4f}</code>\n"
                f"   SL: <code>{sl:,.4f}</code> | TP: <code>{tp:,.4f}</code>\n"
                f"   {pnl_icon} P/L: <code>${profit:+.2f}</code>"
            )

        pnl_icon = "📈" if total_pnl >= 0 else "📉"
        auto_str = "🤖 AUTO" if getattr(o, '_auto_mode', True) else "🖐️ MANUAL"
        lines.append(f"\n{pnl_icon} <b>Jami P/L: ${total_pnl:+.2f}</b> | {auto_str}")
        await self._reply(msg, "\n".join(lines))

    async def _cmd_scan(self, msg, args):
        """AI signal tahlili — bitta symbol uchun"""
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        raw = args[0].upper() if args else "BTCUSD"
        symbol = self._normalize_symbol(raw)
        await self._reply(msg, f"⏳ {symbol} AI tahlil qilinmoqda...")

        try:
            df = await o.market.get_ohlc_async(symbol, "M15", 200)
            if df is None or len(df) < 50:
                await self._reply(msg, f"❌ {symbol} uchun ma'lumot yo'q")
                return

            # Scanner bilan tahlil
            from engines.market_scanner import MultiMarketScanner
            scanner = MultiMarketScanner()
            market_data = {symbol: df}
            account = await asyncio.wait_for(o._get_account(), timeout=8)
            balance = float(account.get("balance") or 10)
            scan = await scanner.scan_all(market_data, balance)

            if not scan.best_signals:
                await self._reply(msg, f"📊 <b>{symbol}</b>\n\n⚠️ Signal topilmadi — bozor aniq emas")
                return

            sig = scan.best_signals[0]
            ob = await o.orderbook.analyze(symbol, sig.entry)
            cvd = await o.orderbook.get_cvd(symbol)

            dir_icon = "🟢" if sig.signal == "BUY" else "🔴"
            cvd_icon = "📈" if cvd.trend == "BULLISH" else ("📉" if cvd.trend == "BEARISH" else "➡️")

            # Cluster info
            c_score = getattr(sig, "cluster_score", 0.0)
            c_type  = getattr(sig, "cluster_type", "")
            c_poc   = getattr(sig, "poc", 0.0)
            c_vah   = getattr(sig, "vah", 0.0)
            c_val   = getattr(sig, "val", 0.0)
            c_cvd   = getattr(sig, "cvd_trend", "")
            c_emoji = "🟢" if c_score > 10 else ("🔴" if c_score < -5 else "🟡")

            cluster_block = (
                f"\n📊 <b>V3 Klaster Analiz:</b>\n"
                f"├ Cluster Score: {c_emoji} <code>{c_score:+.0f}</code> ({c_type})\n"
                f"├ POC: <code>{c_poc:.4f}</code>\n"
                f"├ VAH: <code>{c_vah:.4f}</code>\n"
                f"├ VAL: <code>{c_val:.4f}</code>\n"
                f"└ CVD Trend: <code>{c_cvd}</code>"
            ) if c_poc > 0 else ""

            text = (
                f"🧠 <b>AI TAHLIL: {symbol}</b>\n\n"
                f"{dir_icon} Signal: <b>{sig.signal}</b> | Ishonch: <code>{sig.confidence:.1f}%</code>\n"
                f"💹 Entry: <code>{sig.entry:,.4f}</code>\n"
                f"🛑 SL: <code>{sig.stop_loss:,.4f}</code>\n"
                f"🎯 TP: <code>{sig.take_profit:,.4f}</code>\n"
                f"📐 R:R: <code>{abs(sig.take_profit-sig.entry)/max(abs(sig.entry-sig.stop_loss),1e-10):.2f}</code>\n"
                f"{cluster_block}\n\n"
                f"{cvd_icon} CVD: <code>{cvd.delta_5m:+.0f}</code> | {cvd.trend}\n"
                f"📊 OB: {ob.signal} ({ob.confidence:.0f}%) | Imbalance: {ob.imbalance:+.2f}\n\n"
                f"📝 {sig.reason[:120]}\n\n"
                f"💡 Savdo qilish uchun: /{sig.signal.lower()} {symbol}"
            )
            await self._reply(msg, text)

        except Exception as e:
            await self._reply(msg, f"⚠️ Tahlil xato: {e}")

    async def _cmd_manual_buy(self, msg, args):
        """Qo'lda BUY buyrug'i: /buy BTCUSD"""
        await self._manual_trade(msg, args, "BUY")

    async def _cmd_manual_sell(self, msg, args):
        """Qo'lda SELL buyrug'i: /sell BTCUSD"""
        await self._manual_trade(msg, args, "SELL")

    async def _manual_trade(self, msg, args, side: str):
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        if not args:
            await self._reply(msg,
                f"📝 Foydalanish:\n/{side.lower()} SYMBOL\n\n"
                f"Misol: /{side.lower()} BTCUSD\n"
                f"Mavjud: BTCUSD ETHUSD SOLUSD BNBUSD XRPUSD"
            )
            return

        symbol = self._normalize_symbol(args[0].upper())
        await self._reply(msg, f"⏳ {symbol} {side} tahlil va bajarilmoqda...")

        try:
            result_msg = await o.execute_manual_trade(symbol, side)
            await self._reply(msg, result_msg)
        except Exception as e:
            await self._reply(msg, f"❌ Xato: {e}")

    async def _cmd_auto(self, msg, args):
        """Avtonomiya rejimi toggle"""
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        current = getattr(o, '_auto_mode', True)
        o._auto_mode = not current
        new_state = o._auto_mode

        if new_state:
            text = (
                "🤖 <b>AVTONOMIYA YOQILDI</b>\n\n"
                "Bot endi:\n"
                "✅ Barcha bozorlarni o'zi skanerlaydi\n"
                "✅ AI tahlil asosida o'zi savdo qiladi\n"
                "✅ SL/TP ni o'zi boshqaradi\n\n"
                "O'chirish uchun: /auto"
            )
        else:
            text = (
                "🖐️ <b>MANUAL REJIM</b>\n\n"
                "Bot endi:\n"
                "🔵 Monitoring davom etadi\n"
                "🔵 Alertlar yuboriladi\n"
                "❌ O'zi savdo qilmaydi\n\n"
                "Savdo qilish uchun:\n"
                "/buy BTCUSD yoki /sell ETHUSD\n"
                "/scan SYMBOL — tahlil ko'rish\n\n"
                "Qayta yoqish: /auto"
            )
        await self._reply(msg, text)

    async def _cmd_closeall(self, msg, args):
        """Barcha pozitsiyalarni yopish"""
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return

        positions = o._get_positions()
        if not positions:
            await self._reply(msg, "📭 Yopish uchun ochiq pozitsiya yo'q")
            return

        await self._reply(msg, f"⏳ {len(positions)} ta pozitsiya yopilmoqda...")
        count = 0
        for pos in positions:
            try:
                ticket = pos.get("ticket")
                if pos.get("is_paper"):
                    # Paper pozitsiyani yopish
                    if ticket in o.paper._positions:
                        p = o.paper._positions[ticket]
                        p.closed = True
                        p.close_reason = "MANUAL"
                        del o.paper._positions[ticket]
                        count += 1
                elif o._mode == "binance":
                    await o.binance_exec.close_position(ticket)
                    count += 1
                else:
                    o.execution.close_position(ticket, "Manual close")
                    count += 1
            except Exception as e:
                logger.debug(f"Close {pos.get('symbol')}: {e}")

        await self._reply(msg, f"✅ {count} ta pozitsiya yopildi")

    async def _cmd_stop(self, msg, args):
        o = self._orchestrator
        await self._reply(msg, "⏸️ <b>Bot to'xtatilmoqda...</b>\n\nQayta ishga tushirish uchun: python run.py --bot")
        if o:
            o.stop()

    async def _cmd_ask(self, msg, args):
        """DeepSeek AI chat — faqat trading savollari"""
        o = self._orchestrator
        if not o:
            await self._reply(msg, "⚠️ Orchestrator ulanmagan")
            return
        question = " ".join(args).strip()
        if not question:
            await self._reply(msg, "📝 Savol yozing: /ask BTC bugun qanday ketadi?")
            return
        await self._ai_chat_respond(msg, question, o)

    async def _cmd_ai_chat(self, msg, text: str):
        """Slash buyruqsiz oddiy xabar → AI chat"""
        o = self._orchestrator
        if not o:
            return
        await self._ai_chat_respond(msg, text, o)

    async def _ai_chat_respond(self, msg, question: str, o):
        """AI javob berish — context bilan"""
        await self._reply(msg, "🤖 <i>AI tahlil qilmoqda...</i>")
        try:
            account = await asyncio.wait_for(o._get_account(), timeout=4)
        except Exception:
            account = {}
        positions = o._get_positions()
        context = {
            "balance": float(account.get("balance") or 0),
            "positions": positions[:5],
        }
        answer = await o.ai.trading_chat(question, context=context)
        await self._reply(msg, answer)

    async def send_startup_ultra(self, balance: float, server: str, tier: str, active_markets: int):
        tiers = {
            "micro":    "🔵 Mikro ($10–$100)",
            "mini":     "🟢 Mini ($100–$500)",
            "standard": "🟡 Standart ($500–$2K)",
            "advanced": "🟠 Advanced ($2K–$5K)",
            "pro":      "🔴 Pro ($5K–$10K)",
            "elite":    "💎 Elite ($10K–$50K)",
            "master":   "👑 Master ($50K–$200K)",
            "legend":   "🌟 Legend ($200K–$1M)",
        }
        risk_map = {
            "micro": "0.3%", "mini": "0.5%", "standard": "0.7%",
            "advanced": "1.0%", "pro": "1.2%",
            "elite": "1.5%", "master": "1.8%", "legend": "2.0%",
        }
        risk_pct = risk_map.get(tier, "0.5%")
        msg = f"""
🚀 <b>GOLDAI ULTRA — ISHGA TUSHDI!</b>

💰 Balans: <code>${balance:.2f}</code>
🏅 Tier: <b>{tiers.get(tier, tier)}</b>
🌐 Aktiv bozorlar: <code>{active_markets}</code> ta
🏦 Broker: {server}

📊 <b>Aktiv bozorlar:</b>
├ 💱 Forex majors
├ 🏅 Oltin, kumush, neft
├ ₿ Kripto (BTC, ETH, SOL...)
├ 📈 Aksiyalar (AAPL, NVDA...)
└ 📊 Indekslar (S&amp;P500, Nasdaq...)

🐋 Whale monitoring: <b>FAOL</b>
🛡️ SL himoya: <b>FAOL</b> (SLsiz savdo qilinmaydi)
💹 Risk: <code>{risk_pct}</code> per savdo

🎯 Maqsad: $10 → $1,000,000

⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""
        await self.send(msg)

    async def send_signal(
        self, signal: str, symbol: str, market_type: str,
        confidence: float, entry: float, sl: float, tp: float,
        lot: float, rr: float, tier: str, whale: bool, reason: str,
        cluster_score: float = 0.0, cluster_type: str = "",
        poc: float = 0.0, cvd_trend: str = ""
    ):
        emoji = self.MARKET_EMOJI.get(market_type, "📊")
        dir_icon = "📈" if signal == "BUY" else "📉"
        color = "🟢" if signal == "BUY" else "🔴"

        tier_labels = {"micro": "🔵", "mini": "🟢", "standard": "🟡", "advanced": "🟠", "pro": "🔴"}

        # Cluster info formatlash
        cluster_line = ""
        if cluster_score != 0.0:
            c_emoji = "🟢" if cluster_score > 10 else ("🔴" if cluster_score < -5 else "🟡")
            cvd_e = "↑" if cvd_trend == "BULLISH" else ("↓" if cvd_trend == "BEARISH" else "→")
            cluster_line = (
                f"\n📊 <b>V3 Klaster:</b>\n"
                f"├ Cluster: {c_emoji} <code>{cluster_score:+.0f}</code> ({cluster_type})\n"
                f"├ CVD: <code>{cvd_trend} {cvd_e}</code>\n"
                f"└ POC: <code>{poc:.4f}</code>"
            )

        msg = f"""
{color} <b>{signal} SIGNAL</b> {dir_icon}

{emoji} <b>{symbol}</b> | {market_type.upper()}
{tier_labels.get(tier, '⚪')} Tier: {tier.upper()}

💹 <b>Savdo:</b>
├ Entry: <code>{entry}</code>
├ Stop Loss: <code>{sl}</code>
├ Take Profit: <code>{tp}</code>
├ Lot: <code>{lot}</code>
└ R:R: <code>{rr:.2f}</code>

🧠 Ishonch: <code>{confidence:.1f}%</code>
🐋 Whale: {'✅ Ha' if whale else '❌ Yoq'}{cluster_line}

📝 {reason[:100]}

⏰ {datetime.utcnow().strftime('%H:%M UTC')}
"""
        await self.send(msg)

    async def send_whale_alert(self, symbol: str, signal: str, confidence: float,
                                description: str, institutional: bool):
        msg = f"""
🐋 <b>WHALE ALERT!</b>

💠 Symbol: <b>{symbol}</b>
📡 Signal: <b>{signal}</b>
💪 Ishonch: <code>{confidence:.1f}%</code>
🏛️ Institutional: {'✅ HA' if institutional else '❌ Yoq'}

📋 {description}

⚠️ <i>Katta o'yinchilar harakat qilmoqda!</i>
⏰ {datetime.utcnow().strftime('%H:%M UTC')}
"""
        await self.send(msg)

    async def send_risk_alert(self, message: str, daily_loss: float, drawdown: float):
        msg = f"""
⚠️ <b>RISK OGOHLANTIRISH!</b>

📊 Kunlik yo'qotish: <code>{daily_loss:.1f}%</code>
📉 Drawdown: <code>{drawdown:.1f}%</code>

❗ <b>{message}</b>

⏰ {datetime.utcnow().strftime('%H:%M UTC')}
"""
        await self.send(msg)

    async def send_daily_report(self, balance: float, equity: float, growth_pct: float,
                                 trades: int, win_rate: float, tier: str, next_target: dict):
        emoji = "📈" if growth_pct >= 0 else "📉"
        msg = f"""
📊 <b>GOLDAI ULTRA — KUNLIK HISOBOT</b>
📅 {datetime.utcnow().strftime('%Y-%m-%d')}

💰 <b>Hisob:</b>
├ Balans: <code>${balance:.2f}</code>
├ Equity: <code>${equity:.2f}</code>
└ Kapital o'sishi: {emoji} <code>{growth_pct:+.2f}%</code>

📈 <b>Statistika:</b>
├ Jami savdolar: <code>{trades}</code>
└ Yutish foizi: <code>{win_rate:.1f}%</code>

🏅 Tier: <b>{tier.upper()}</b>
🎯 Keyingi bosqich: <code>${next_target.get('target_amount', 0)}</code>
   Progress: <code>{next_target.get('progress_pct', 0):.1f}%</code>

🤖 GoldAI Ultra | Multi-Market System
"""
        await self.send(msg)

    async def send_tier_upgrade(self, old_tier: str, new_tier: str, balance: float):
        msg = f"""
🎉 <b>TIER YANGILANDI!</b>

{old_tier.upper()} → <b>{new_tier.upper()}</b>

💰 Yangi balans: <code>${balance:.2f}</code>
📊 Yangi imkoniyatlar:
├ Ko'proq bozorlar
├ Ko'proq risk (%)
└ Ko'proq ochiq pozitsiyalar

🚀 <b>Keyingi maqsadga davom!</b>
"""
        await self.send(msg)

    async def send_trade_close(self, symbol: str, side: str, entry: float,
                                close_price: float, profit: float,
                                reason: str, ticket: int):
        """Savdo yopilganda to'liq hisobot"""
        if reason == "TAKE_PROFIT":
            icon = "✅"
            result_label = "TAKE PROFIT olindi"
        elif reason == "STOP_LOSS":
            icon = "❌"
            result_label = "STOP LOSS ishladi"
        else:
            icon = "🔵"
            result_label = "Qo'lda yopildi"

        pnl_icon = "📈" if profit > 0 else "📉"
        dir_icon = "📈" if side == "BUY" else "📉"

        msg = f"""\
{icon} <b>{result_label}</b>

{dir_icon} <b>{symbol}</b> {side}

💹 <b>Natija:</b>
├ Entry: <code>{entry:.5f}</code>
├ Yopilish: <code>{close_price:.5f}</code>
├ Foyda/Zarar: {pnl_icon} <code>${profit:+.2f}</code>
└ Ticket: #{ticket}

⏰ {datetime.utcnow().strftime('%H:%M UTC')}"""
        await self.send(msg)

    async def send_trade_history(self, records: list):
        """So'nggi savdolar tarixi"""
        if not records:
            await self.send("📋 <b>Savdolar tarixi bo'sh</b>")
            return

        lines = ["📋 <b>SO'NGGI SAVDOLAR TARIXI</b>", ""]
        total_profit = 0

        for r in records[:10]:
            profit = float(r.get("profit") or 0)
            total_profit += profit
            pnl_icon = "✅" if profit > 0 else "❌"
            side = r.get("side", "")
            dir_icon = "📈" if side == "BUY" else "📉"
            reason_icon = {
                "TAKE_PROFIT": "🎯", "STOP_LOSS": "🛑", "MANUAL": "🔵"
            }.get(r.get("close_reason", ""), "⚪")

            ts = r.get("close_time", "")
            if hasattr(ts, "strftime"):
                ts_str = ts.strftime("%m/%d %H:%M")
            else:
                ts_str = str(ts)[:16]

            lines.append(
                f"{pnl_icon} {dir_icon} <b>{r.get('symbol')}</b> "
                f"{reason_icon} <code>${profit:+.2f}</code> "
                f"<i>{ts_str}</i>"
            )

        lines.append("")
        pnl_total_icon = "📈" if total_profit > 0 else "📉"
        lines.append(f"{pnl_total_icon} <b>Jami:</b> <code>${total_profit:+.2f}</code>")
        await self.send("\n".join(lines))

    async def send_full_stats(self, stats):
        """To'liq statistika hisoboti"""
        if stats is None:
            await self.send("📊 Statistika uchun yetarli ma'lumot yo'q")
            return

        wr_icon = "🟢" if stats.win_rate >= 55 else ("🟡" if stats.win_rate >= 45 else "🔴")
        pnl_icon = "📈" if stats.total_profit > 0 else "📉"

        lines = [
            "📊 <b>TO'LIQ STATISTIKA</b>",
            "",
            f"📌 Jami savdolar: <code>{stats.total}</code>",
            f"{wr_icon} Win Rate: <code>{stats.win_rate:.1f}%</code>",
            f"✅ Yutishlar: <code>{stats.wins}</code>  ❌ Yo'qotishlar: <code>{stats.losses}</code>",
            "",
            f"{pnl_icon} Jami P/L: <code>${stats.total_profit:+.2f}</code>",
            f"📐 O'rtacha: <code>${stats.avg_profit:+.2f}</code>",
            f"🏆 Eng yaxshi: <code>${stats.best_trade:+.2f}</code>",
            f"💔 Eng yomon: <code>${stats.worst_trade:+.2f}</code>",
        ]

        if stats.by_symbol:
            lines.append("\n🔝 <b>Symbol bo'yicha:</b>")
            for sym, d in list(stats.by_symbol.items())[:5]:
                wr = d.get("wr", 0)
                pr = d.get("profit", 0)
                icon = "📈" if pr > 0 else "📉"
                lines.append(f"  {icon} {sym}: WR {wr:.0f}% | ${pr:+.2f}")

        lines.append(f"\n⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        await self.send("\n".join(lines))

    async def send_orderbook_alert(self, symbol: str, ob_state):
        """Order book / Iceberg alertlari"""
        if not ob_state.icebergs and not ob_state.bid_walls and not ob_state.ask_walls:
            return

        lines = [f"🧊 <b>ORDER BOOK ALERT: {symbol}</b>", ""]

        if ob_state.icebergs:
            lines.append("🧊 <b>Iceberg orderlar aniqlandi:</b>")
            for ice in ob_state.icebergs[:2]:
                side_icon = "🟢" if ice.side == "BID" else "🔴"
                lines.append(
                    f"{side_icon} {ice.side} @ <code>${ice.price:,.0f}</code> | "
                    f"~${ice.usd_value/1e6:.2f}M | x{ice.refresh_count} refill"
                )

        if ob_state.bid_walls:
            w = ob_state.bid_walls[0]
            lines.append(f"\n🟢 Bid Wall: <code>${w.price:,.0f}</code> — ${w.usd_value/1e6:.2f}M")

        if ob_state.ask_walls:
            w = ob_state.ask_walls[0]
            lines.append(f"🔴 Ask Wall: <code>${w.price:,.0f}</code> — ${w.usd_value/1e6:.2f}M")

        imb = ob_state.imbalance
        imb_icon = "🟢" if imb > 0.2 else ("🔴" if imb < -0.2 else "⚪")
        lines.append(f"\n{imb_icon} Imbalance: <code>{imb:+.2f}</code>")
        lines.append(f"🎯 OB Signal: <b>{ob_state.signal}</b> ({ob_state.confidence:.0f}%)")
        lines.append(f"\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}")

        await self.send("\n".join(lines))

    async def send_news_alert(self, news_title: str, sentiment: str,
                               impact: str, currencies: list):
        """Muhim yangilik alerti"""
        impact_icons = {"high": "🔴", "medium": "🟡", "low": "🟢", "critical": "🚨"}
        sent_icons = {"positive": "📈", "negative": "📉", "neutral": "➡️"}

        msg = f"""\
📰 <b>YANGILIK OGOHLANTIRISH</b>

{impact_icons.get(impact, '⚪')} Muhimlik: <b>{impact.upper()}</b>
{sent_icons.get(sentiment, '➡️')} Sentiment: <b>{sentiment.upper()}</b>
💱 Valyutalar: {', '.join(currencies)}

📋 {news_title}

⏰ {datetime.utcnow().strftime('%H:%M UTC')}"""
        await self.send(msg)

    async def send_news_blackout(self, reason: str):
        """News blackout ogohlantirishi"""
        msg = f"""\
⏸️ <b>SAVDO TO'XTATILDI</b>

⚠️ Muhim iqtisodiy hodisa yaqinlashmoqda:
<code>{reason}</code>

ℹ️ Bot hodisadan so'ng avtomatik davom etadi.
⏰ {datetime.utcnow().strftime('%H:%M UTC')}"""
        await self.send(msg)

    async def send_market_overview(self, fear_greed: int, fg_label: str,
                                    news_sentiment: float, upcoming_events: list):
        """Bozor umumiy holati"""
        fg_icon = "😱" if fear_greed < 25 else ("😰" if fear_greed < 45 else
                   ("😐" if fear_greed < 55 else ("😁" if fear_greed < 75 else "🤑")))
        sent_icon = "📈" if news_sentiment > 0.2 else ("📉" if news_sentiment < -0.2 else "➡️")

        lines = [
            "🌐 <b>BOZOR HOLATI HISOBOTI</b>",
            "",
            f"{fg_icon} Fear &amp; Greed: <b>{fear_greed}</b> — {fg_label}",
            f"{sent_icon} Yangiliklar sentimenti: <code>{news_sentiment:+.2f}</code>",
        ]

        if upcoming_events:
            lines.append("\n📅 <b>Yaqin hodisalar (2 soat):</b>")
            for ev in upcoming_events[:3]:
                impact_icon = "🔴" if ev.impact == "High" else "🟡"
                lines.append(
                    f"{impact_icon} {ev.title} ({ev.currency}) "
                    f"— {ev.minutes_away} daqiqa"
                )

        lines.append(f"\n⏰ {datetime.utcnow().strftime('%H:%M UTC')}")
        await self.send("\n".join(lines))
