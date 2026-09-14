"""
GoldAI Ultra — Signal Filter Engine
Libertex (ForexClub) Edition
Session + Funding rate (faqat Binance yoqilganda) filtrlari
"""

import asyncio
import aiohttp
from datetime import datetime, timezone
from core.logger import logger
from core.config import config


FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"


class SignalFilter:
    """
    Barcha qo'shimcha filtrlarni bir joyda boshqaradi.
    Libertex rejimida funding filtri o'chirilgan (CFD da funding yo'q, swap bor)
    """

    # Session — Libertex 24/5 (Forex), Crypto 24/7
    # Libertex da ham session filtrini yumshatdik: 00-23 (faqat 23-00 yopiq emas)
    ACTIVE_HOURS_UTC = set(range(0, 24))  # Libertex: 24 soat ochiq

    def __init__(self):
        self._funding_cache: dict[str, tuple[float, float]] = {}
        self._oi_cache:      dict[str, tuple[float, float]] = {}

    async def check(self, symbol: str, signal: str, market_type: str = "crypto") -> tuple[bool, str]:
        """
        symbol   : 'BTCUSD' (ichki format)
        signal   : 'BUY' | 'SELL'
        market_type: 'crypto' | 'forex' | ...
        Returns: (allowed: bool, reason: str)
        """

        # 1. Vaqt filtri — Libertex da yumshoq (24 soat)
        # Agar xohlasa config dan session ni qattiqlashtirish mumkin
        ok, msg = self._session_filter(market_type)
        if not ok:
            return False, msg

        # 2. Funding filtri — faqat Binance yoqilgan va crypto bo'lsa
        if config.enable_binance and market_type == "crypto":
            try:
                from engines.binance_executor import SYMBOL_MAP
                bn_sym = SYMBOL_MAP.get(symbol)
                if bn_sym:
                    ok, msg = await self._funding_filter(bn_sym, signal)
                    if not ok:
                        return False, msg
            except Exception:
                pass  # Binance yo'q bo'lsa o'tkazib yuborish

        return True, "OK"

    def _session_filter(self, market_type: str = "crypto") -> tuple[bool, str]:
        """Libertex session — aksariyat instrumentlar 24/5 ochiq"""
        # Forex: Dushanba-Juma 00:00-23:59, Crypto: 24/7
        # Shuning uchun blok yo'q, faqat dam olish kuni tekshiruvi
        now = datetime.now(timezone.utc)
        weekday = now.weekday()  # 0=Mon, 6=Sun
        hour = now.hour

        # Yakshanba — Forex yopiq (Libertex da ham)
        if weekday == 6 and market_type in ("forex", "commodity", "index", "stock"):
            return False, f"Session: Yakshanba — {market_type} bozori yopiq (Forex dam olish)"

        # Juma kechasi 22:00 dan keyin Forex yopiladi (NY close)
        if weekday == 4 and hour >= 22 and market_type in ("forex", "commodity", "index", "stock"):
            return False, f"Session: Juma 22:00 UTC dan keyin — {market_type} yopiq"

        return True, "OK"

    async def _funding_filter(self, bn_sym: str, signal: str) -> tuple[bool, str]:
        """Funding rate — faqat Binance yoqilganda"""
        if not config.enable_binance:
            return True, "OK (Libertex — funding yo'q)"
        try:
            rate = await self._get_funding(bn_sym)
            if rate is None:
                return True, "OK"
            if signal == "SELL" and rate < -0.0003:
                return False, f"Funding: {rate*100:.4f}% — shorts over-extended, SELL risky"
            if signal == "BUY" and rate > 0.0015:
                return False, f"Funding: {rate*100:.4f}% — longs over-extended, BUY risky"
            return True, f"Funding OK: {rate*100:.4f}%"
        except Exception as e:
            logger.debug(f"Funding filter xato ({bn_sym}): {e}")
            return True, "OK"

    async def _get_funding(self, bn_sym: str) -> float | None:
        if not config.enable_binance:
            return None
        import time
        now = time.time()
        cached = self._funding_cache.get(bn_sym)
        if cached and now - cached[1] < 300:
            return cached[0]
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    FUNDING_URL, params={"symbol": bn_sym},
                    timeout=aiohttp.ClientTimeout(total=4)
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        rate = float(d.get("lastFundingRate", 0))
                        self._funding_cache[bn_sym] = (rate, now)
                        return rate
        except Exception:
            pass
        return None

    async def get_funding_score(self, bn_sym: str, signal: str) -> float:
        if not config.enable_binance:
            return 0.0
        try:
            rate = await self._get_funding(bn_sym)
            if rate is None:
                return 0.0
            if signal == "SELL":
                if rate > 0.0005:    return 15.0
                if rate > 0.0001:    return 7.0
                if rate < -0.0001:   return -10.0
                return 0.0
            if signal == "BUY":
                if rate < -0.0003:   return 15.0
                if rate < -0.0001:   return 7.0
                if rate > 0.001:     return -10.0
                return 0.0
        except Exception:
            pass
        return 0.0
