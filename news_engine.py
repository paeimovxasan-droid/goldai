"""
GoldAI Ultra — News & Sentiment Engine
Savdo qarorlarini yangiliklar asosida boyitish:
  1. CryptoPanic  — Crypto yangiliklari (real-time)
  2. ForexFactory — Iqtisodiy takvim (NFP, FOMC, CPI...)
  3. Fear & Greed Index — Bozor hissiyoti
  4. RSS feeds    — Reuters, Bloomberg, CoinDesk

Muhim yangilik bo'lganda savdoni to'xtatadi yoki kuchaytiradi.
"""

import asyncio
import aiohttp
import json
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional
from core.logger import logger


@dataclass
class NewsItem:
    title:      str
    source:     str
    sentiment:  str      # positive | negative | neutral
    impact:     str      # low | medium | high | critical
    currencies: list     # ["BTC", "ETH", "USD"]
    url:        str
    published:  datetime
    score:      float    # -1.0 (very bearish) .. +1.0 (very bullish)


@dataclass
class EconEvent:
    title:      str
    currency:   str      # USD | EUR | GBP
    impact:     str      # Low | Medium | High
    datetime_utc: datetime
    forecast:   str
    previous:   str
    actual:     str
    minutes_away: int    # Qolgan daqiqalar (manfiy = o'tgan)


@dataclass
class MarketSentiment:
    fear_greed_index:  int       # 0=extreme fear, 100=extreme greed
    fear_greed_label:  str       # "Extreme Fear" | "Fear" | "Neutral" | "Greed" | "Extreme Greed"
    crypto_sentiment:  float     # -1 .. +1
    news_sentiment:    float     # -1 .. +1
    upcoming_events:   list      # Yaqin 2 soatdagi muhim hodisalar
    blackout_active:   bool      # Savdo to'xtatilsinmi?
    blackout_reason:   str


# Crypto yangiliklari sentiment so'zlari
BULLISH_WORDS = {
    "bullish", "surge", "rally", "breakout", "adoption", "partnership",
    "launch", "upgrade", "approval", "etf", "institutional", "record",
    "all-time high", "ath", "buy", "accumulate", "growth", "positive",
    "milestone", "integration", "listing", "mainnet"
}
BEARISH_WORDS = {
    "bearish", "crash", "dump", "hack", "exploit", "ban", "regulation",
    "lawsuit", "sec", "fraud", "scam", "delisting", "sell", "drop",
    "fall", "decline", "loss", "bankrupt", "shut down", "investigation",
    "warning", "fear", "panic", "liquidation"
}


class NewsEngine:
    """Multi-manba yangiliklar va sentiment tahlili"""

    CRYPTOPANIC_URL  = "https://cryptopanic.com/api/v1/posts/"
    FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FEAR_GREED_URL   = "https://api.alternative.me/fng/?limit=1"
    COINGECKO_TREND  = "https://api.coingecko.com/api/v3/search/trending"

    # Muhim iqtisodiy hodisalar — savdo to'xtatish uchun
    HIGH_IMPACT_EVENTS = {
        "Non-Farm Payroll", "NFP", "FOMC", "Federal Reserve",
        "Interest Rate Decision", "CPI", "Inflation", "GDP",
        "Unemployment", "Jackson Hole", "ECB", "BOE",
    }

    def __init__(self):
        self._news_cache: list[NewsItem] = []
        self._events_cache: list[EconEvent] = []
        self._sentiment_cache: Optional[MarketSentiment] = None
        self._last_news_fetch: Optional[datetime] = None
        self._last_calendar_fetch: Optional[datetime] = None
        self._last_fg_fetch: Optional[datetime] = None
        self._fear_greed: int = 50
        self._fg_label: str = "Neutral"

    # ─── ASOSIY TAHLIL ────────────────────────────────────────────

    async def get_sentiment(self, symbols: list = None) -> MarketSentiment:
        """To'liq bozor hissiyoti"""
        await asyncio.gather(
            self._fetch_fear_greed(),
            self._fetch_crypto_news(symbols or ["BTC", "ETH"]),
            self._fetch_economic_calendar(),
            return_exceptions=True
        )

        # Hissiyot hisoblash
        news_score = self._calc_news_sentiment()
        upcoming = self._get_upcoming_events(minutes=120)
        blackout, reason = self._check_blackout(upcoming)

        sentiment = MarketSentiment(
            fear_greed_index=self._fear_greed,
            fear_greed_label=self._fg_label,
            crypto_sentiment=news_score,
            news_sentiment=news_score,
            upcoming_events=upcoming,
            blackout_active=blackout,
            blackout_reason=reason
        )
        self._sentiment_cache = sentiment
        return sentiment

    def is_blackout(self) -> tuple[bool, str]:
        """Tezkor blackout tekshiruvi (cached)"""
        if self._sentiment_cache:
            return self._sentiment_cache.blackout_active, self._sentiment_cache.blackout_reason
        return False, ""

    def get_signal_modifier(self, symbol: str, direction: str) -> float:
        """
        Yangiliklar asosida signal kuchini o'zgartirish.
        1.0 = o'zgarsiz, 1.3 = kuchaytir, 0.7 = kamaytir
        """
        if not self._sentiment_cache:
            return 1.0

        fg = self._sentiment_cache.fear_greed_index
        news = self._sentiment_cache.news_sentiment

        # Extreme fear/greed kontrtrendga qarshi savdo
        if direction == "BUY" and fg < 20:
            return 1.2   # Extreme fear → buy signals stronger
        if direction == "SELL" and fg > 80:
            return 1.2   # Extreme greed → sell signals stronger

        # News sentiment bilan moslik
        if direction == "BUY" and news > 0.3:
            return 1.15
        if direction == "SELL" and news < -0.3:
            return 1.15

        # Qarama-qarshi bo'lsa — kamaytir
        if direction == "BUY" and news < -0.4:
            return 0.75
        if direction == "SELL" and news > 0.4:
            return 0.75

        return 1.0

    # ─── FEAR & GREED ─────────────────────────────────────────────

    async def _fetch_fear_greed(self):
        now = datetime.now(timezone.utc)
        if self._last_fg_fetch and (now - self._last_fg_fetch).seconds < 3600:
            return  # 1 soatda bir marta

        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(self.FEAR_GREED_URL,
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json()
                        idx = data["data"][0]
                        self._fear_greed = int(idx["value"])
                        self._fg_label   = idx["value_classification"]
                        self._last_fg_fetch = now
                        logger.info(f"😱 Fear&Greed: {self._fear_greed} ({self._fg_label})")
        except Exception as e:
            logger.debug(f"Fear&Greed fetch xato: {e}")

    # ─── CRYPTO YANGILIKLAR ───────────────────────────────────────

    async def _fetch_crypto_news(self, currencies: list):
        now = datetime.now(timezone.utc)
        if self._last_news_fetch and (now - self._last_news_fetch).seconds < 900:
            return  # 15 daqiqada bir marta

        cur_str = ",".join(currencies[:5])
        try:
            url = f"{self.CRYPTOPANIC_URL}?auth_token=free&currencies={cur_str}&kind=news&filter=important"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        self._parse_cryptopanic(data.get("results", []))
                        self._last_news_fetch = now
        except Exception as e:
            logger.debug(f"CryptoPanic fetch xato: {e}")
            # Fallback — CoinGecko trending
            await self._fetch_coingecko_trending()

    def _parse_cryptopanic(self, results: list):
        items = []
        for item in results[:20]:
            title = item.get("title", "")
            source = item.get("source", {}).get("title", "")
            score = self._score_title(title)
            sentiment = "positive" if score > 0.2 else ("negative" if score < -0.2 else "neutral")
            currencies = [c["code"] for c in item.get("currencies", [])]
            pub = item.get("published_at", "")
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                dt = datetime.now(timezone.utc)

            votes = item.get("votes", {})
            impact = "low"
            if votes.get("important", 0) > 50 or votes.get("negative", 0) > 30:
                impact = "high"
            elif votes.get("important", 0) > 20:
                impact = "medium"

            items.append(NewsItem(
                title=title, source=source, sentiment=sentiment,
                impact=impact, currencies=currencies, url="",
                published=dt, score=score
            ))
        self._news_cache = items

    async def _fetch_coingecko_trending(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(self.COINGECKO_TREND,
                                  timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        data = await r.json()
                        coins = [c["item"]["symbol"].upper()
                                 for c in data.get("coins", [])[:5]]
                        logger.info(f"📈 CoinGecko trending: {', '.join(coins)}")
        except Exception:
            pass

    def _score_title(self, title: str) -> float:
        title_low = title.lower()
        score = 0.0
        for w in BULLISH_WORDS:
            if w in title_low:
                score += 0.15
        for w in BEARISH_WORDS:
            if w in title_low:
                score -= 0.15
        return max(-1.0, min(1.0, score))

    def _calc_news_sentiment(self) -> float:
        if not self._news_cache:
            return 0.0
        now = datetime.now(timezone.utc)
        recent = [n for n in self._news_cache
                  if (now - n.published).seconds < 7200]  # 2 soat
        if not recent:
            return 0.0
        # Yangi yangiliklar ko'proq ta'sir qiladi
        weighted = sum(n.score * (1 if n.impact == "high" else 0.5)
                       for n in recent)
        return max(-1.0, min(1.0, weighted / max(1, len(recent))))

    # ─── IQTISODIY TAKVIM ─────────────────────────────────────────

    async def _fetch_economic_calendar(self):
        now = datetime.now(timezone.utc)
        if self._last_calendar_fetch and (now - self._last_calendar_fetch).seconds < 3600:
            return

        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(self.FOREX_FACTORY_URL,
                                  timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        events = await r.json()
                        self._parse_calendar(events)
                        self._last_calendar_fetch = now
        except Exception as e:
            logger.debug(f"ForexFactory fetch xato: {e}")

    def _parse_calendar(self, events: list):
        now = datetime.now(timezone.utc)
        parsed = []
        for ev in events:
            try:
                dt_str = ev.get("date", "") + " " + ev.get("time", "")
                dt_str = dt_str.strip()
                if not dt_str or "All Day" in ev.get("time", ""):
                    continue
                # FF format: "Dec 27 2024 8:30am"
                dt = datetime.strptime(dt_str, "%b %d %Y %I:%M%p")
                dt = dt.replace(tzinfo=timezone.utc)
                diff_min = int((dt - now).total_seconds() / 60)

                parsed.append(EconEvent(
                    title=ev.get("name", ""),
                    currency=ev.get("country", ""),
                    impact=ev.get("impact", "Low"),
                    datetime_utc=dt,
                    forecast=ev.get("forecast", ""),
                    previous=ev.get("previous", ""),
                    actual=ev.get("actual", ""),
                    minutes_away=diff_min
                ))
            except Exception:
                continue
        self._events_cache = sorted(parsed, key=lambda x: x.minutes_away)

    def _get_upcoming_events(self, minutes: int = 120) -> list:
        return [e for e in self._events_cache
                if 0 <= e.minutes_away <= minutes and e.impact in ("High", "Medium")]

    def _check_blackout(self, upcoming: list) -> tuple[bool, str]:
        """Yaqin davrdagi muhim hodisalar uchun savdo to'xtatish"""
        for ev in upcoming:
            is_high_impact = any(kw.lower() in ev.title.lower()
                                 for kw in self.HIGH_IMPACT_EVENTS)
            if is_high_impact and ev.impact == "High" and ev.minutes_away <= 30:
                return True, f"⏸️ {ev.title} ({ev.minutes_away} daqiqadan so'ng)"

        # Extreme fear — counter-trend savdoni to'xtatish emas, lekin ehtiyot
        # (bu yerda blackout emas, faqat modifier kamaytiradi)
        return False, ""

    # ─── HISOBOT ──────────────────────────────────────────────────

    def format_telegram_report(self) -> str:
        """Telegram uchun yangiliklar hisoboti"""
        lines = ["📰 <b>BOZOR HOLATI</b>", ""]

        # Fear & Greed
        fg = self._fear_greed
        fg_emoji = "😱" if fg < 25 else ("😰" if fg < 45 else
                    ("😐" if fg < 55 else ("😁" if fg < 75 else "🤑")))
        lines.append(f"{fg_emoji} Fear&Greed: <b>{fg}</b> — {self._fg_label}")

        # Sentiment
        if self._sentiment_cache:
            s = self._sentiment_cache.news_sentiment
            if s > 0.2:
                lines.append(f"📈 Yangiliklar: <b>Bullish</b> (+{s:.1f})")
            elif s < -0.2:
                lines.append(f"📉 Yangiliklar: <b>Bearish</b> ({s:.1f})")
            else:
                lines.append(f"➡️ Yangiliklar: Neytral")

        # Upcoming events
        upcoming = self._get_upcoming_events(240)
        if upcoming:
            lines.append("\n📅 <b>Yaqin hodisalar:</b>")
            for ev in upcoming[:3]:
                icon = "🔴" if ev.impact == "High" else "🟡"
                lines.append(f"{icon} {ev.title} ({ev.currency}) — {ev.minutes_away} daqiqa")

        # Hot news
        recent = sorted(self._news_cache, key=lambda x: abs(x.score), reverse=True)[:3]
        if recent:
            lines.append("\n🔥 <b>Muhim yangiliklar:</b>")
            for n in recent:
                icon = "📈" if n.score > 0 else "📉"
                lines.append(f"{icon} {n.title[:60]}...")

        return "\n".join(lines)

    def get_latest_news_for_symbol(self, symbol: str) -> list:
        """Bitta symbol uchun tegishli yangiliklar"""
        # Symbol → currency mapping
        sym_map = {
            "BTCUSD": ["BTC"], "ETHUSD": ["ETH"], "SOLUSD": ["SOL"],
            "BNBUSD": ["BNB"], "XRPUSD": ["XRP"],
            "EURUSD": ["EUR", "USD"], "GBPUSD": ["GBP", "USD"],
            "USDJPY": ["USD", "JPY"], "XAUUSD": ["XAU", "USD"],
        }
        currencies = sym_map.get(symbol, [])
        if not currencies:
            return []

        relevant = [n for n in self._news_cache
                    if any(c in n.currencies for c in currencies)]
        return sorted(relevant, key=lambda x: x.published, reverse=True)[:5]
