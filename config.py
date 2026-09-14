"""
GoldAI Ultra — Multi-Market Professional Config
Libertex (ForexClub) MT5 Edition
Forex + Crypto + Stocks + Commodities | $10 → $1,000,000 Capital Growth System

Broker: ForexClub / Libertex via MetaTrader 5
Serverlar: ForexClub-MT5 Real Server / ForexClub-MT5 Demo Server
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


# ─── BOZORLAR — Libertex MT5 orqali ─────────────────────────────────
# Barcha instrumentlar Libertex MT5 (ForexClub) orqali CFD sifatida savdo qilinadi.
# Binance endi ixtiyoriy (ENABLE_BINANCE=true bo'lsa faqat qo'shimcha ma'lumot uchun)

MARKETS = {

    # ── FOREX / COMMODITIES (Libertex MT5) ───────────────────────
    "XAUUSD":  {"type": "commodity", "pip": 0.1,   "contract": 100,  "min_lot": 0.01, "category": "precious_metal"},
    "XAGUSD":  {"type": "commodity", "pip": 0.001, "contract": 5000, "min_lot": 0.01, "category": "precious_metal"},
    "EURUSD":  {"type": "forex",     "pip": 0.0001,"contract": 100000,"min_lot": 0.01,"category": "major"},
    "GBPUSD":  {"type": "forex",     "pip": 0.0001,"contract": 100000,"min_lot": 0.01,"category": "major"},
    "USDJPY":  {"type": "forex",     "pip": 0.01,  "contract": 100000,"min_lot": 0.01,"category": "major"},
    "USDCHF":  {"type": "forex",     "pip": 0.0001,"contract": 100000,"min_lot": 0.01,"category": "major"},
    "AUDUSD":  {"type": "forex",     "pip": 0.0001,"contract": 100000,"min_lot": 0.01,"category": "major"},
    "USDCAD":  {"type": "forex",     "pip": 0.0001,"contract": 100000,"min_lot": 0.01,"category": "major"},
    "NZDUSD":  {"type": "forex",     "pip": 0.0001,"contract": 100000,"min_lot": 0.01,"category": "major"},
    "USOIL":   {"type": "commodity", "pip": 0.01,  "contract": 1000, "min_lot": 0.01, "category": "energy"},
    "UKOIL":   {"type": "commodity", "pip": 0.01,  "contract": 1000, "min_lot": 0.01, "category": "energy"},
    "USTEC":   {"type": "index",     "pip": 0.1,   "contract": 1,    "min_lot": 0.1,  "category": "index"},
    "US500":   {"type": "index",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "index"},
    "US30":    {"type": "index",     "pip": 0.1,   "contract": 1,    "min_lot": 0.1,  "category": "index"},
    "GER40":   {"type": "index",     "pip": 0.1,   "contract": 1,    "min_lot": 0.1,  "category": "index"},

    # ── CRYPTO (Libertex MT5 CFD) ──────────────────────────────────
    # Libertex MT5 da crypto CFD sifatida mavjud (BTCUSD, ETHUSD va boshqalar)
    # Agar Binance yoqilgan bo'lsa, qo'shimcha ma'lumot uchun ishlatiladi
    "BTCUSD":  {"type": "crypto",    "pip": 1,     "contract": 1,    "min_lot": 0.01,"category": "crypto_major"},
    "ETHUSD":  {"type": "crypto",    "pip": 0.1,   "contract": 1,    "min_lot": 0.01,"category": "crypto_major"},
    "BNBUSD":  {"type": "crypto",    "pip": 0.01,  "contract": 1,    "min_lot": 0.01,"category": "crypto_alt"},
    "SOLUSD":  {"type": "crypto",    "pip": 0.01,  "contract": 1,    "min_lot": 0.1, "category": "crypto_alt"},
    "XRPUSD":  {"type": "crypto",    "pip": 0.0001,"contract": 1,    "min_lot": 1,   "category": "crypto_alt"},
    "ADAUSD":  {"type": "crypto",    "pip": 0.0001,"contract": 1,    "min_lot": 1,   "category": "crypto_alt"},
    "DOTUSD":  {"type": "crypto",    "pip": 0.001, "contract": 1,    "min_lot": 0.1, "category": "crypto_alt"},
    "AVAXUSD": {"type": "crypto",    "pip": 0.01,  "contract": 1,    "min_lot": 0.1, "category": "crypto_alt"},

    # ── STOCKS (CFD via Libertex) ──────────────────────────────────
    "AAPL":    {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
    "TSLA":    {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
    "NVDA":    {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
    "MSFT":    {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
    "GOOGL":   {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
    "AMZN":    {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
    "META":    {"type": "stock",     "pip": 0.01,  "contract": 1,    "min_lot": 0.1,  "category": "tech"},
}

# Libertex MT5 da mavjud bo'lmagan symbol lar uchun fallback mapping
# (ba'zi brokerlarda BTCUSD = BTCUSD, ba'zilarida BTCUSDT)
LIBERTEX_SYMBOL_ALIASES = {
    "BTCUSD": ["BTCUSD", "BTCUSD.", "BITCOIN", "BTCUSDT"],
    "ETHUSD": ["ETHUSD", "ETHUSD.", "ETHEREUM", "ETHUSDT"],
    "BNBUSD": ["BNBUSD", "BNBUSD."],
    "SOLUSD": ["SOLUSD", "SOLUSD."],
    "XRPUSD": ["XRPUSD", "XRPUSD."],
    "ADAUSD": ["ADAUSD", "ADAUSD."],
    "DOTUSD": ["DOTUSD", "DOTUSD."],
    "AVAXUSD": ["AVAXUSD", "AVAXUSD."],
}

# Balans bosqichlariga ko'ra aktiv bozorlar — Libertex uchun moslashtirilgan
# Micro da ham Forex + Gold qo'shildi (Libertex da komissiya past)
MARKET_TIERS = {
    "micro":    {"min": 10,     "max": 100,     "symbols": ["EURUSD", "XAUUSD", "BTCUSD", "ETHUSD", "GBPUSD"]},
    "mini":     {"min": 100,    "max": 500,     "symbols": ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "ETHUSD", "SOLUSD", "US500"]},
    "standard": {"min": 500,    "max": 2000,    "symbols": ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "ETHUSD", "SOLUSD", "US500", "USTEC"]},
    "advanced": {"min": 2000,   "max": 5000,    "symbols": list(MARKETS.keys())[:18]},
    "pro":      {"min": 5000,   "max": 10000,   "symbols": list(MARKETS.keys())},
    "elite":    {"min": 10000,  "max": 50000,   "symbols": list(MARKETS.keys())},
    "master":   {"min": 50000,  "max": 200000,  "symbols": list(MARKETS.keys())},
    "legend":   {"min": 200000, "max": 1000000, "symbols": list(MARKETS.keys())},
}


@dataclass
class RiskConfig:
    """Dinamik risk — balansga qarab moslashadi ($10 → $1,000,000)"""

    # $10–$100 (Micro)
    micro_risk_pct: float = 0.003         # 0.3%
    micro_daily_limit: float = 0.02       # 2%
    micro_max_positions: int = 1

    # $100–$500 (Mini)
    mini_risk_pct: float = 0.005          # 0.5%
    mini_daily_limit: float = 0.03        # 3%
    mini_max_positions: int = 2

    # $500–$2000 (Standard)
    standard_risk_pct: float = 0.007      # 0.7%
    standard_daily_limit: float = 0.04    # 4%
    standard_max_positions: int = 3

    # $2000–$5000 (Advanced)
    advanced_risk_pct: float = 0.01       # 1%
    advanced_daily_limit: float = 0.05    # 5%
    advanced_max_positions: int = 4

    # $5000–$10000 (Pro)
    pro_risk_pct: float = 0.012           # 1.2%
    pro_daily_limit: float = 0.05         # 5%
    pro_max_positions: int = 5

    # $10000–$50000 (Elite)
    elite_risk_pct: float = 0.015         # 1.5%
    elite_daily_limit: float = 0.06       # 6%
    elite_max_positions: int = 6

    # $50000–$200000 (Master)
    master_risk_pct: float = 0.018        # 1.8%
    master_daily_limit: float = 0.07      # 7%
    master_max_positions: int = 8

    # $200000–$1000000 (Legend)
    legend_risk_pct: float = 0.02         # 2%
    legend_daily_limit: float = 0.08      # 8%
    legend_max_positions: int = 10

    # Universal
    max_weekly_loss: float = 0.10         # 10%
    max_drawdown: float = 0.20            # 20%
    min_rr_ratio: float = 1.5             # R:R min 1:1.5
    min_confidence: float = 45.0          # Signal min ishonch
    max_spread_pct: float = 0.05          # Max spread 0.05%

    def get_for_balance(self, balance: float) -> dict:
        """Balansga mos risk parametrlari"""
        if balance < 100:
            return {"risk_pct": self.micro_risk_pct, "daily_limit": self.micro_daily_limit,
                    "max_positions": self.micro_max_positions, "tier": "micro"}
        elif balance < 500:
            return {"risk_pct": self.mini_risk_pct, "daily_limit": self.mini_daily_limit,
                    "max_positions": self.mini_max_positions, "tier": "mini"}
        elif balance < 2000:
            return {"risk_pct": self.standard_risk_pct, "daily_limit": self.standard_daily_limit,
                    "max_positions": self.standard_max_positions, "tier": "standard"}
        elif balance < 5000:
            return {"risk_pct": self.advanced_risk_pct, "daily_limit": self.advanced_daily_limit,
                    "max_positions": self.advanced_max_positions, "tier": "advanced"}
        elif balance < 10000:
            return {"risk_pct": self.pro_risk_pct, "daily_limit": self.pro_daily_limit,
                    "max_positions": self.pro_max_positions, "tier": "pro"}
        elif balance < 50000:
            return {"risk_pct": self.elite_risk_pct, "daily_limit": self.elite_daily_limit,
                    "max_positions": self.elite_max_positions, "tier": "elite"}
        elif balance < 200000:
            return {"risk_pct": self.master_risk_pct, "daily_limit": self.master_daily_limit,
                    "max_positions": self.master_max_positions, "tier": "master"}
        else:
            return {"risk_pct": self.legend_risk_pct, "daily_limit": self.legend_daily_limit,
                    "max_positions": self.legend_max_positions, "tier": "legend"}


@dataclass
class WhaleConfig:
    """Whale (Kit) monitoring sozlamalari"""
    btc_whale_threshold: float = 500.0
    eth_whale_threshold: float = 5000.0
    forex_large_order_pips: float = 50.0
    volume_spike_multiplier: float = 3.0
    institutional_threshold_pct: float = 0.5
    check_interval_seconds: int = 60


@dataclass
class LibertexConfig:
    """Libertex / ForexClub MT5 sozlamalari — ASOSIY BROKER"""
    enabled: bool = True  # Libertex — asosiy rejim
    # Qo'shimcha Libertex parametrlari
    leverage_default: int = 100  # Libertex leverage


@dataclass
class BinanceConfig:
    """Binance — ENDI IXTISORIY, faqat ENABLE_BINANCE=true bo'lsa"""
    api_key: str = os.getenv("BINANCE_API_KEY", "")
    secret_key: str = os.getenv("BINANCE_SECRET_KEY", "")
    testnet: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    enabled: bool = os.getenv("ENABLE_BINANCE", "false").lower() == "true"
    ws_url: str = "wss://stream.binance.com:9443/ws"


@dataclass
class MT5Config:
    """ForexClub / Libertex MT5"""
    login: int = int(os.getenv("MT5_LOGIN", "0"))
    password: str = os.getenv("MT5_PASSWORD", "")
    # ForexClub serverlari: ForexClub-MT5 Real Server / Demo Server
    # Libertex kabinetida ko'rsatilgan aniq server nomini kiriting
    server: str = os.getenv("MT5_SERVER", "ForexClub-MT5 Real Server")
    # Alternativ serverlar (agar asosiysi ishlamasa avtomatik sinab ko'radi)
    fallback_servers: list = field(default_factory=lambda: [
        "ForexClub-MT5 Real Server",
        "ForexClub-MT5 Demo Server",
        "ForexClub-MT5 Real Server 2",
        "mt5-real-prim.fxclub.org",
        "mt5-real-sec.fxclub.org",
    ])
    magic_number: int = 999001
    timeout: int = 60000
    path: str = os.getenv("MT5_PATH", "")  # MT5 terminal yo'li (Windows da kerak bo'lishi mumkin)
    broker: str = os.getenv("BROKER", "ForexClub")  # ForexClub / Libertex


@dataclass
class DeepSeekConfig:
    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    max_tokens: int = 1500
    temperature: float = 0.2


@dataclass
class DatabaseConfig:
    url: str = os.getenv("DB_URL", "postgresql://ultra:ultra123@localhost:5432/goldai_ultra")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")


@dataclass
class TelegramConfig:
    token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")


class AppConfig:
    def __init__(self):
        self.mt5 = MT5Config()
        self.binance = BinanceConfig()
        self.libertex = LibertexConfig()
        self.risk = RiskConfig()
        self.whale = WhaleConfig()
        self.deepseek = DeepSeekConfig()
        self.database = DatabaseConfig()
        self.telegram = TelegramConfig()
        self.markets = MARKETS
        self.market_tiers = MARKET_TIERS
        # Broker nomi
        self.broker_name = self.mt5.broker  # ForexClub / Libertex
        self.enable_binance = self.binance.enabled

    def get_active_symbols(self, balance: float) -> list:
        """Balansga qarab aktiv symbollar"""
        params = self.risk.get_for_balance(balance)
        tier = params["tier"]
        return self.market_tiers[tier]["symbols"]

    def is_libertex_mode(self) -> bool:
        """Libertex rejimi faolmi?"""
        return self.libertex.enabled and not self.enable_binance


config = AppConfig()
