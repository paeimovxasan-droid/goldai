"""
GoldAI Ultra — Multi-Market Data Engine
Libertex (ForexClub) MT5 Edition — Asosiy manba MT5, Binance ixtiyoriy
"""

import asyncio
import aiohttp
import os
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    class _MockMT5:
        TIMEFRAME_M1 = 1; TIMEFRAME_M5 = 5; TIMEFRAME_M15 = 15; TIMEFRAME_M30 = 30
        TIMEFRAME_H1 = 60; TIMEFRAME_H4 = 240; TIMEFRAME_D1 = 1440
        def __getattr__(self, name):
            return 0
        def initialize(self, *a, **kw): return False
        def login(self, *a, **kw): return False
        def last_error(self): return "MT5 not available (Linux — Windows da ishlaydi)"
        def shutdown(self): pass
        def account_info(self): return None
        def positions_get(self, *a, **kw): return None
        def symbols_get(self): return None
        def symbol_info(self, *a, **kw): return None
        def symbol_info_tick(self, *a, **kw): return None
        def symbol_select(self, *a, **kw): return False
        def copy_rates_from_pos(self, *a, **kw): return None
    mt5 = _MockMT5()

from core.config import config, MARKETS, LIBERTEX_SYMBOL_ALIASES
from core.logger import logger


class MultiMarketDataEngine:
    """Libertex MT5 orqali barcha bozorlardan ma'lumot olish"""

    MT5_TIMEFRAMES = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }

    BINANCE_INTERVALS = {
        "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
        "H1": "1h", "H4": "4h", "D1": "1d"
    }

    BINANCE_API = "https://api.binance.com/api/v3"

    def __init__(self):
        self.mt5_connected = False
        self.connected_server = ""
        self.last_connection_error = ""
        self._price_cache: dict = {}
        self._ohlc_cache: dict = {}
        self._last_update: dict = {}
        self._actual_symbols: dict = {}  # BTCUSD -> MT5 dagi haqiqiy nom (masalan BTCUSD.)

    @staticmethod
    def _terminal_paths() -> list[str]:
        """Return existing MT5 terminal paths plus the configured path.

        MT5's Python bridge can start a terminal only when the executable path
        is correct.  The old code first initialized with MT5_PATH and then
        initialized a second time without a path, which caused IPC failures.
        """
        configured = os.path.expandvars(config.mt5.path.strip().strip('"')) if config.mt5.path else ""
        candidates = [configured] if configured else []
        env_roots = [os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LOCALAPPDATA")]
        relative = [
            "ForexClub MT5\\terminal64.exe",
            "Libertex MT5\\terminal64.exe",
            "MetaTrader 5\\terminal64.exe",
            "MetaTrader 5\\terminal64.exe",
        ]
        for root in env_roots:
            if root:
                candidates.extend(os.path.join(root, item) for item in relative)
        # Keep a configured missing path in the list so the log explains it.
        result = []
        for path in candidates:
            if path and path not in result:
                result.append(path)
        return result

    def _initialize_terminal(self) -> bool:
        """Initialize the MT5 IPC bridge exactly once per attempt."""
        paths = self._terminal_paths()
        if config.mt5.path and not os.path.isfile(paths[0] if paths else config.mt5.path):
            logger.warning("MT5_PATH topilmadi: %s; ochiq terminalga ulanish sinab ko'riladi", config.mt5.path)

        # Try an explicitly configured/existing executable first.  A normal
        # initialize() is also needed when the terminal is already running.
        for path in [p for p in paths if os.path.isfile(p)]:
            try:
                if mt5.initialize(path=path, timeout=config.mt5.timeout):
                    logger.info("MT5 terminal topildi: %s", path)
                    return True
                logger.warning("MT5 initialize (path=%s) xatosi: %s", path, mt5.last_error())
                mt5.shutdown()
            except Exception as exc:
                logger.warning("MT5 path initialize xatosi (%s): %s", path, type(exc).__name__)
                try:
                    mt5.shutdown()
                except Exception:
                    pass

        try:
            if mt5.initialize(timeout=config.mt5.timeout):
                logger.info("MT5 terminalga odatiy IPC ulanishi muvaffaqiyatli")
                return True
            self.last_connection_error = str(mt5.last_error())
        except Exception as exc:
            self.last_connection_error = f"{type(exc).__name__}: {exc}"
        logger.error("MT5 initialize xatosi: %s", self.last_connection_error)
        return False

    def connect_mt5(self) -> bool:
        """Connect to ForexClub/Libertex MT5 with clear diagnostics."""
        self.mt5_connected = False
        self.connected_server = ""
        self._actual_symbols.clear()

        if not MT5_AVAILABLE:
            self.last_connection_error = "MetaTrader5 Python paketi o'rnatilmagan (Windows + MT5 terminali kerak)"
            logger.error("❌ %s", self.last_connection_error)
            return False
        if config.mt5.login <= 0 or not config.mt5.password or not config.mt5.server:
            self.last_connection_error = "MT5_LOGIN, MT5_PASSWORD va MT5_SERVER to'liq kiritilmagan"
            logger.error("❌ %s", self.last_connection_error)
            return False
        if not self._initialize_terminal():
            logger.error("❌ MT5 terminal IPC ishga tushmadi. MT5 ni bir marta qo'lda ochib login qiling.")
            return False

        last_error = None
        for srv in config.mt5.fallback_servers:
            logger.info("🔌 MT5 login urinishi: %s (login=%s)", srv, config.mt5.login)
            try:
                result = mt5.login(
                    login=config.mt5.login,
                    password=config.mt5.password,
                    server=srv,
                )
            except Exception as exc:
                result = False
                last_error = f"{type(exc).__name__}: {exc}"
            if result:
                info = mt5.account_info()
                if info and int(getattr(info, "login", 0)) == config.mt5.login:
                    self.connected_server = str(getattr(info, "server", srv) or srv)
                    self.mt5_connected = True
                    terminal = getattr(mt5, "terminal_info", lambda: None)()
                    if terminal is not None and getattr(terminal, "trade_allowed", True) is False:
                        logger.warning("⚠️ MT5 terminal AutoTrading o'chiq — ma'lumot bor, orderlar bloklanadi")
                    logger.info(
                        "✅ MT5 Ulandi: %s | Login=%s | Balans=$%.2f %s | Leverage 1:%s",
                        self.connected_server, info.login, info.balance, info.currency, info.leverage,
                    )
                    self._discover_symbols()
                    return True
            try:
                last_error = str(mt5.last_error())
            except Exception:
                last_error = "unknown MT5 error"
            logger.warning("MT5 login muvaffaqiyatsiz (%s): %s", srv, last_error)

        self.last_connection_error = str(last_error or "server/login rad etdi")
        logger.error("❌ MT5 ulanib bo'lmadi: %s", self.last_connection_error)
        logger.info(
            "💡 MT5 terminali ochiq/login qilinganini, AutoTrading yoqilganini va "
            "kabinetdagi server nomi MT5_SERVER bilan aynan bir xil ekanini tekshiring"
        )
        try:
            mt5.shutdown()
        except Exception:
            pass
        return False

    def _discover_symbols(self):
        """MT5 dagi mavjud symbollardan haqiqiy nomlarni topish (suffix bilan)"""
        try:
            # Barcha mavjud symollarni olish
            symbols = mt5.symbols_get()
            if not symbols:
                return
            available = {str(s.name): s for s in symbols if getattr(s, "name", None)}
            normalized = {
                "".join(ch for ch in name.upper() if ch.isalnum()): name
                for name in available
            }
            for std_symbol in MARKETS.keys():
                aliases = LIBERTEX_SYMBOL_ALIASES.get(std_symbol, [std_symbol])
                found = next((alias for alias in aliases if alias in available), None)
                if not found:
                    std_key = "".join(ch for ch in std_symbol.upper() if ch.isalnum())
                    found = normalized.get(std_key)
                if not found:
                    # Handles broker suffixes/prefixes such as EURUSD.a,
                    # EURUSDm and FX_EURUSD without guessing an unrelated symbol.
                    std_key = "".join(ch for ch in std_symbol.upper() if ch.isalnum())
                    for key, name in normalized.items():
                        if key.startswith(std_key) or key.endswith(std_key):
                            found = name
                            break
                if found:
                    self._actual_symbols[std_symbol] = found
                    mt5.symbol_select(found, True)
                    if found != std_symbol:
                        logger.info(f"📊 Symbol mapping: {std_symbol} → {found} (Libertex)")
                else:
                    logger.debug(f"Symbol topilmadi MT5 da: {std_symbol}")
        except Exception as e:
            logger.debug(f"Symbol discovery xato: {e}")

    def _resolve_symbol(self, symbol: str) -> str:
        """Standart symbol → MT5 dagi haqiqiy nom"""
        return self._actual_symbols.get(symbol, symbol)

    def get_tick(self, symbol: str) -> Optional[dict]:
        """Joriy narx — AVVAL MT5 (Libertex), keyin Binance cache"""
        # Libertex rejimida har doim MT5 dan
        if self.mt5_connected:
            actual = self._resolve_symbol(symbol)
            tick = self._get_mt5_tick(actual)
            if tick:
                tick["symbol"] = symbol  # standart nom qaytariladi
                tick["mt5_symbol"] = actual
                return tick

        # MT5 ulanmagan va Binance yoqilgan bo'lsa
        if config.enable_binance:
            market = MARKETS.get(symbol, {})
            if market.get("type") == "crypto":
                return self._get_binance_tick_cached(symbol)

        return self._get_mt5_tick(self._resolve_symbol(symbol)) if self.mt5_connected else None

    def _get_mt5_tick(self, symbol: str) -> Optional[dict]:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            # Symbol tanlanmagan bo'lishi mumkin
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
        return {
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": round((tick.ask - tick.bid) / tick.bid * 100, 4) if tick.bid else 0,
            "time": datetime.fromtimestamp(tick.time).isoformat(),
            "source": f"MT5/{config.mt5.broker}"
        }

    def _get_binance_tick_cached(self, symbol: str) -> Optional[dict]:
        """Cache'dan narx (WebSocket bilan yangilanadi) — faqat Binance yoqilganda"""
        if not config.enable_binance:
            return None
        cached = self._price_cache.get(symbol)
        if cached:
            return cached
        if self.mt5_connected:
            return self._get_mt5_tick(self._resolve_symbol(symbol))
        return None

    def update_price_cache(self, symbol: str, bid: float, ask: float):
        """WebSocket dan narxni yangilash"""
        self._price_cache[symbol] = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": round((ask - bid) / bid * 100, 4) if bid else 0,
            "time": datetime.utcnow().isoformat(),
            "source": "Binance WS" if config.enable_binance else "MT5"
        }

    def get_ohlc(self, symbol: str, timeframe: str = "M15", bars: int = 300) -> Optional[pd.DataFrame]:
        """OHLC — AVVAL MT5 (Libertex), Binance faqat ixtiyoriy fallback"""
        if self.mt5_connected:
            actual = self._resolve_symbol(symbol)
            df = self._get_mt5_ohlc(actual, timeframe, bars)
            if df is not None and len(df) > 20:
                return df
        # MT5 dan olinmasa va Binance yoqilgan bo'lsa
        if config.enable_binance and MARKETS.get(symbol, {}).get("type") == "crypto":
            return self._get_binance_ohlc_sync(symbol, timeframe, bars)
        # Oxirgi fallback: MT5 ga yana urinish
        return self._get_mt5_ohlc(self._resolve_symbol(symbol), timeframe, bars) if self.mt5_connected else None

    def _get_mt5_ohlc(self, symbol: str, timeframe: str, bars: int) -> Optional[pd.DataFrame]:
        actual = self._resolve_symbol(symbol)
        tf = self.MT5_TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_M15)
        # Symbol tanlanganligini ta'minlash
        mt5.symbol_select(actual, True)
        rates = mt5.copy_rates_from_pos(actual, tf, 0, bars)
        if rates is None or len(rates) == 0:
            logger.debug(f"MT5 OHLC yo'q: {actual} {timeframe} — {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df = df[["open", "high", "low", "close", "tick_volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        return self._add_indicators(df)

    def _get_binance_ohlc_sync(self, symbol: str, timeframe: str, bars: int) -> Optional[pd.DataFrame]:
        """Binance OHLC (synchronous wrapper) — faqat ENABLE_BINANCE=true da"""
        if not config.enable_binance:
            return None
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self._get_binance_ohlc_async(symbol, timeframe, bars))
            loop.close()
            return result
        except Exception:
            if self.mt5_connected:
                return self._get_mt5_ohlc(self._resolve_symbol(symbol), timeframe, bars)
            return None

    async def get_ohlc_async(self, symbol: str, timeframe: str = "M15", bars: int = 300) -> Optional[pd.DataFrame]:
        """Async OHLC — Libertex MT5 birinchi"""
        if self.mt5_connected:
            df = self._get_mt5_ohlc(symbol, timeframe, bars)
            if df is not None and len(df) > 20:
                return df
        # Binance faqat crypto va yoqilgan bo'lsa
        market = MARKETS.get(symbol, {})
        if config.enable_binance and market.get("type") == "crypto":
            df = await self._get_binance_ohlc_async(symbol, timeframe, bars)
            if df is not None:
                return df
            # Binance ham ishlamasa MT5 fallback
        return self._get_mt5_ohlc(self._resolve_symbol(symbol), timeframe, bars) if self.mt5_connected else None

    async def _get_binance_ohlc_async(self, symbol: str, timeframe: str, bars: int) -> Optional[pd.DataFrame]:
        """Binance REST API dan OHLC — faqat ixtiyoriy"""
        if not config.enable_binance:
            return None
        binance_symbol = symbol.replace("USD", "USDT")
        interval = self.BINANCE_INTERVALS.get(timeframe, "15m")
        url = f"{self.BINANCE_API}/klines?symbol={binance_symbol}&interval={interval}&limit={bars}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            if not data:
                return None

            df = pd.DataFrame(data, columns=[
                "time", "open", "high", "low", "close", "volume",
                "close_time", "quote_vol", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore"
            ])
            df["time"] = pd.to_datetime(df["time"], unit="ms")
            df.set_index("time", inplace=True)
            df = df[["open", "high", "low", "close", "volume"]].astype(float)

            return self._add_indicators(df)

        except Exception as e:
            logger.debug(f"Binance OHLC xato ({symbol}): {e}")
            return None

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Universal texnik indikatorlar"""
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # EMA
        for period in [9, 20, 50, 100, 200]:
            df[f"ema{period}"] = c.ewm(span=period, adjust=False).mean()

        # ATR
        tr = pd.concat([
            h - l,
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.ewm(span=14, adjust=False).mean()
        df["atr_pct"] = df["atr"] / c * 100

        # RSI
        delta = c.diff()
        gain = delta.clip(lower=0).ewm(span=14).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14).mean()
        df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

        # MACD
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Bollinger Bands
        df["bb_mid"] = c.rolling(20).mean()
        bb_std = c.rolling(20).std()
        df["bb_upper"] = df["bb_mid"] + 2 * bb_std
        df["bb_lower"] = df["bb_mid"] - 2 * bb_std
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
        df["bb_pct"] = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-10)

        # Stochastic
        low14 = l.rolling(14).min()
        high14 = h.rolling(14).max()
        df["stoch_k"] = (c - low14) / (high14 - low14 + 1e-10) * 100
        df["stoch_d"] = df["stoch_k"].rolling(3).mean()

        # Volume
        df["volume_ma"] = v.rolling(20).mean()
        df["volume_ratio"] = v / (df["volume_ma"] + 1e-10)

        # VWAP (intraday)
        typical = (h + l + c) / 3
        df["vwap"] = (typical * v).cumsum() / v.cumsum()

        # Volatility
        df["volatility"] = c.pct_change().rolling(20).std() * 100

        # Candle analysis
        df["body"] = (c - df["open"]).abs()
        df["upper_wick"] = h - df[["open", "close"]].max(axis=1)
        df["lower_wick"] = df[["open", "close"]].min(axis=1) - l
        df["is_bullish"] = c > df["open"]
        df["body_pct"] = df["body"] / (h - l + 1e-10)

        # Trend strength
        df["adx_trend"] = (df["ema20"] - df["ema50"]) / df["ema50"] * 100

        return df.dropna(subset=["ema200", "atr"])

    def get_account_info(self) -> dict:
        if not self.mt5_connected:
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
            "server": info.server,
            "broker": getattr(info, 'company', config.mt5.broker),
        }

    def get_all_positions(self) -> list:
        if not self.mt5_connected:
            return []
        positions = mt5.positions_get()
        if positions is None:
            return []
        result = []
        for p in positions:
            # Standart nomga qaytarish
            std_symbol = p.symbol
            for k, v in self._actual_symbols.items():
                if v == p.symbol:
                    std_symbol = k
                    break
            result.append({
                "ticket": p.ticket,
                "symbol": std_symbol,
                "mt5_symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "sl": p.sl, "tp": p.tp,
                "profit": p.profit,
                "open_time": datetime.fromtimestamp(p.time).isoformat(),
                "comment": p.comment,
                "magic": p.magic,
                "market_type": MARKETS.get(std_symbol, {}).get("type", "unknown")
            })
        return result

    def get_symbol_info(self, symbol: str) -> dict:
        actual = self._resolve_symbol(symbol)
        if not self.mt5_connected:
            return MARKETS.get(symbol, {})
        info = mt5.symbol_info(actual)
        if info is None:
            # Fallback — symbol ro'yxatdan qidirib ko'rish
            mt5.symbol_select(actual, True)
            info = mt5.symbol_info(actual)
            if info is None:
                return MARKETS.get(symbol, {})
        return {
            "symbol": actual,
            "std_symbol": symbol,
            "digits": info.digits,
            "point": info.point,
            "trade_contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_tick_value": info.trade_tick_value,
            "trade_tick_size": info.trade_tick_size,
            "type": MARKETS.get(symbol, {}).get("type", "forex"),
        }

    async def scan_all_markets(self, balance: float) -> dict:
        """Barcha aktiv bozorlardagi ma'lumotlarni yig'ish"""
        active_symbols = config.get_active_symbols(balance)
        return await self.scan_all_markets_list(active_symbols)

    async def scan_all_markets_list(self, symbols: list) -> dict:
        """Berilgan symbollar ro'yxatini skanerlash"""
        results = {}
        tasks = {symbol: self.get_ohlc_async(symbol, "M15", 200)
                 for symbol in symbols}

        for symbol, task in tasks.items():
            try:
                df = await task
                if df is not None and len(df) > 50:
                    results[symbol] = df
                else:
                    logger.debug(f"OHLC yo'q: {symbol}")
            except Exception as e:
                logger.debug(f"Market scan xato ({symbol}): {e}")

        logger.info(f"📡 Libertex MT5 scan: {len(results)}/{len(symbols)} symbol tayyor")
        return results

    def disconnect_mt5(self):
        """MT5 ulanishini uzish"""
        try:
            import MetaTrader5 as mt5
            mt5.shutdown()
            self.mt5_connected = False
            logger.info("MT5 ulanishi uzildi")
        except Exception:
            pass
