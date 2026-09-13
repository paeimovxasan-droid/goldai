"""
GoldAI Ultra — Multi-Market Professional Config
Libertex (ForexClub) MT5 Edition
Forex + Crypto + Stocks + Commodities | $10 → $1,000,000 Capital Growth System

Broker: ForexClub / Libertex via MetaTrader 5
Serverlar: ForexClub-MT5 Real Server / ForexClub-MT5 Demo Server
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Allows the diagnostic command to run before dependencies are installed.
    def load_dotenv(dotenv_path=None, override=False):
        """Small .env fallback used only when python-dotenv is not installed."""
        path = Path(dotenv_path or Path(__file__).resolve().parents[1] / ".env")
        if not path.is_file():
            return False
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
                value = value[1:-1]
            if override or key not in os.environ:
                os.environ[key] = value
        return True

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
# Always load the repository's .env, even when the launcher is started from a
# different working directory. Existing process environment variables win.
load_dotenv(_ENV_FILE)


def _env_first(*names: str, default: str = "") -> str:
    """Read the first non-empty environment variable and normalize quotes."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value.strip('\\"\\\'')
    return default


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


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _server_candidates() -> list[str]:
    """Build unique server candidates without trying unrelated account types first."""
    configured = os.getenv("MT5_SERVER", "ForexClub-MT5 Real Server").strip()
    raw_fallbacks = os.getenv("MT5_FALLBACK_SERVERS", "").strip()
    if raw_fallbacks:
        fallbacks = [item.strip() for item in raw_fallbacks.split(",") if item.strip()]
    else:
        fallbacks = [
            "ForexClub-MT5 Real Server",
            "ForexClub-MT5 Demo Server",
            "ForexClub-MT5 Real Server 2",
            "ForexClub-MT5 Demo Server 2",
            "mt5-real-prim.fxclub.org",
            "mt5-demo-prim.fxclub.org",
        ]
    result = []
    for value in [configured, *fallbacks]:
        if value and value not in result:
            result.append(value)
    return result


@dataclass
class BinanceConfig:
    """Binance — faqat ENABLE_BINANCE=true bo'lsa ishlatiladi."""
    api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", "").strip())
    secret_key: str = field(default_factory=lambda: os.getenv("BINANCE_SECRET_KEY", "").strip())
    testnet: bool = field(default_factory=lambda: _as_bool(os.getenv("BINANCE_TESTNET", "true"), True))
    enabled: bool = field(default_factory=lambda: _as_bool(os.getenv("ENABLE_BINANCE", "false")))
    ws_url: str = "wss://stream.binance.com:9443/ws"


@dataclass
class MT5Config:
    """ForexClub / Libertex MT5 ulanish parametrlari."""
    login: int = field(default_factory=lambda: _as_int(os.getenv("MT5_LOGIN", "0")))
    password: str = field(default_factory=lambda: os.getenv("MT5_PASSWORD", ""))
    server: str = field(default_factory=lambda: os.getenv("MT5_SERVER", "ForexClub-MT5 Real Server").strip())
    fallback_servers: list = field(default_factory=lambda: _server_candidates())
    magic_number: int = field(default_factory=lambda: _as_int(os.getenv("MT5_MAGIC_NUMBER", "999001"), 999001))
    timeout: int = field(default_factory=lambda: _as_int(os.getenv("MT5_TIMEOUT_MS", "60000"), 60000))
    path: str = field(default_factory=lambda: os.getenv("MT5_PATH", "").strip().strip('\"'))
    broker: str = field(default_factory=lambda: os.getenv("BROKER", "ForexClub").strip())


@dataclass
class AIProviderConfig:
    """OpenAI-compatible providers used by the AI agent."""
    provider_order: str = field(default_factory=lambda: os.getenv(
        "AI_PROVIDER_ORDER", "deepseek,gemini,openai"
    ))
    request_timeout: int = field(default_factory=lambda: _as_int(
        os.getenv("AI_TIMEOUT_SECONDS", "20"), 20
    ))
    cooldown_seconds: int = field(default_factory=lambda: _as_int(
        os.getenv("AI_PROVIDER_COOLDOWN_SECONDS", "300"), 300
    ))
    deepseek_api_key: str = field(default_factory=lambda: _env_first("DEEPSEEK_API_KEY", "DEEPSEEK_KEY"))
    deepseek_model: str = field(default_factory=lambda: _env_first("DEEPSEEK_MODEL", default="deepseek-chat"))
    deepseek_base_url: str = field(default_factory=lambda: _env_first(
        "DEEPSEEK_BASE_URL", default="https://api.deepseek.com/v1"
    ).rstrip("/"))
    openai_api_key: str = field(default_factory=lambda: _env_first("OPENAI_API_KEY", "OPENAI_KEY"))
    openai_model: str = field(default_factory=lambda: _env_first("OPENAI_MODEL", default="gpt-4o-mini"))
    openai_base_url: str = field(default_factory=lambda: _env_first(
        "OPENAI_BASE_URL", default="https://api.openai.com/v1"
    ).rstrip("/"))
    gemini_api_key: str = field(default_factory=lambda: _env_first(
        "GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY", "GOOGLE_API_KEY"
    ))
    gemini_model: str = field(default_factory=lambda: _env_first("GEMINI_MODEL", default="gemini-2.0-flash"))
    gemini_base_url: str = field(default_factory=lambda: _env_first(
        "GEMINI_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/"))

    def enabled_providers(self) -> list[str]:
        """Return configured providers in the requested failover order."""
        aliases = {"google": "gemini", "google-gemini": "gemini"}
        requested = [aliases.get(p.strip().lower(), p.strip().lower())
                     for p in self.provider_order.split(",") if p.strip()]
        known = ("deepseek", "gemini", "openai")
        ordered = [p for p in requested if p in known and self.api_key_for(p)]
        # A stale .env may contain AI_PROVIDER_ORDER=deepseek from the old
        # DeepSeek-only version. Keep the requested priority, but append any
        # configured fallback so a valid new key is never silently ignored.
        for provider in known:
            if self.api_key_for(provider) and provider not in ordered:
                ordered.append(provider)
        return ordered

    def api_key_for(self, provider: str) -> str:
        return {
            "deepseek": self.deepseek_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
        }.get(provider, "")

    # Compatibility fields used by older external integrations.
    @property
    def api_key(self) -> str:
        return self.deepseek_api_key

    @property
    def model(self) -> str:
        return self.deepseek_model

    @property
    def base_url(self) -> str:
        return self.deepseek_base_url

    @property
    def max_tokens(self) -> int:
        return 1500

    @property
    def temperature(self) -> float:
        return 0.2


# Kept as a compatibility alias for integrations importing DeepSeekConfig.
DeepSeekConfig = AIProviderConfig


@dataclass
class DatabaseConfig:
    url: str = field(default_factory=lambda: os.getenv(
        "DB_URL", "postgresql://ultra:ultra_secure_2025@localhost:5432/goldai_ultra"
    ))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))


@dataclass
class TelegramConfig:
    token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "").strip())


class AppConfig:
    def __init__(self):
        self.mt5 = MT5Config()
        self.binance = BinanceConfig()
        self.libertex = LibertexConfig()
        self.risk = RiskConfig()
        self.whale = WhaleConfig()
        self.deepseek = DeepSeekConfig()
        self.ai = self.deepseek  # Clearer name; old integrations use config.deepseek.
        self.database = DatabaseConfig()
        self.telegram = TelegramConfig()
        self.markets = MARKETS
        self.market_tiers = MARKET_TIERS
        # Broker nomi
        self.broker_name = self.mt5.broker  # ForexClub / Libertex
        self.enable_binance = self.binance.enabled
        self.trading_mode = os.getenv("TRADING_MODE", "paper").strip().lower()
        if self.trading_mode not in {"live", "paper", "auto"}:
            self.trading_mode = "paper"

    def get_active_symbols(self, balance: float) -> list:
        """Balansga qarab aktiv symbollar"""
        params = self.risk.get_for_balance(balance)
        tier = params["tier"]
        return self.market_tiers[tier]["symbols"]

    def is_libertex_mode(self) -> bool:
        """Libertex rejimi faolmi?"""
        return self.libertex.enabled and not self.enable_binance


config = AppConfig()
