"""GoldAI Ultra launcher and diagnostics.

Windows users should normally double-click ``START_GOLDAI.bat``.  The Python
entry point remains useful for logs, CI and manual troubleshooting:

    python run.py --test
    python run.py --bot
    python run.py                 # bot + API
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Windows console encoding; do not fail if stdout is already wrapped.
if hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _load_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        # config.py contains a dependency-free fallback for the first run.
        from core.config import load_dotenv
    load_dotenv(BASE_DIR / ".env")


def _configured(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() not in {"CHANGE_ME", "your-key-here"})


def check_env() -> bool:
    """Print a safe configuration summary without ever printing secrets."""
    _load_env()
    required = {
        "MT5_LOGIN": os.getenv("MT5_LOGIN"),
        "MT5_PASSWORD": os.getenv("MT5_PASSWORD"),
        "MT5_SERVER": os.getenv("MT5_SERVER"),
    }
    optional = {
        "MT5_PATH": os.getenv("MT5_PATH"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ENABLE_BINANCE": os.getenv("ENABLE_BINANCE", "false"),
        "TRADING_MODE": os.getenv("TRADING_MODE", "paper"),
    }

    print("=" * 68)
    print("  GoldAI Ultra — ForexClub / Libertex MT5 konfiguratsiya testi")
    print("=" * 68)
    print(f"  Broker: {os.getenv('BROKER', 'ForexClub')}")
    print(f"  Server: {os.getenv('MT5_SERVER', '[kiritilmagan]')}")
    print(f"  AI tartibi: {os.getenv('AI_PROVIDER_ORDER', 'deepseek,gemini,openai')}")
    print("=" * 68)

    all_ok = True
    for key, value in required.items():
        ok = _configured(value)
        if key == "MT5_LOGIN":
            try:
                ok = ok and int(str(value)) > 0
            except (TypeError, ValueError):
                ok = False
        print(f"  {'[OK]' if ok else '[!!]'} {key}: {'kiritilgan' if ok else 'KIRITILMAGAN'}")
        all_ok = all_ok and ok

    for key, value in optional.items():
        if key == "ENABLE_BINANCE":
            label = "yoqilgan" if str(value).lower() == "true" else "o'chiq"
            print(f"  [OK] {key}: {label} (ixtiyoriy)")
        elif key == "TRADING_MODE":
            print(f"  [OK] {key}: {value} (live/paper/auto)")
        else:
            print(f"  {'[OK]' if _configured(value) else '[ -]'} {key}: {'kiritilgan' if _configured(value) else 'kiritilmagan'}")

    print("\n  Eslatma: Telegram va AI kalitlari ixtiyoriy; MT5 login/parol/server bot savdosi uchun kerak.")
    return all_ok


async def run_system_test() -> bool:
    """Run local imports and safe network/MT5 diagnostics."""
    _load_env()
    from core.config import config

    print("\n" + "=" * 68)
    print("  GoldAI Ultra — to'liq tizim diagnostikasi")
    print("=" * 68)
    errors: list[str] = []

    print("\n[1] Python paketlari va modullar:")
    modules = [
        ("core.config", "AppConfig"),
        ("core.orchestrator", "UltraOrchestrator"),
        ("engines.market_data", "MultiMarketDataEngine"),
        ("engines.execution_engine", "ExecutionEngine"),
        ("engines.market_scanner", "MultiMarketScanner"),
        ("agents.deepseek_agent", "DeepSeekAgent"),
        ("bot.telegram_bot", "TelegramBot"),
        ("api.main", "app"),
    ]
    for module_name, attribute in modules:
        try:
            module = __import__(module_name, fromlist=[attribute])
            getattr(module, attribute)
            print(f"    [OK] {module_name}.{attribute}")
        except Exception as exc:
            message = f"{module_name}: {type(exc).__name__}: {exc}"
            print(f"    [!!] {message}")
            errors.append(message)

    print("\n[2] AI providerlar:")
    try:
        from agents.deepseek_agent import DeepSeekAgent
        ai = DeepSeekAgent()
        providers = ai.configured_providers
        def _provider_key_status(provider: str) -> str:
            key = ai.settings.api_key_for(provider)
            return f"{provider}=bor ({len(key)} belgi)" if key else f"{provider}=yo'q"
        key_status = ", ".join(
            _provider_key_status(provider) for provider in ("deepseek", "gemini", "openai")
        )
        provider_order = ", ".join(providers) if providers else "yo'q"
        print(f"    Provider tartibi: {provider_order}")
        print(f"    Key holati: {key_status}")
        if not providers:
            print("    [ -] API key yo'q — .env da GEMINI_API_KEY, OPENAI_API_KEY yoki DEEPSEEK_API_KEY kiriting")
        else:
            result = await ai.quick_review(
                {"scanned": 1, "signals": 0, "best_symbol": "EURUSD",
                 "best_confidence": 0, "sentiment": "NEUTRAL", "market_types": {}},
                {"balance": 0, "equity": 0},
            )
            if result:
                print(f"    [OK] AI javobi olindi ({ai.active_provider})")
            else:
                print("    [!!] Barcha AI providerlar javob bermadi (key/quota/internetni tekshiring)")
                errors.append("AI: all configured providers failed")
    except Exception as exc:
        print(f"    [!!] AI: {type(exc).__name__}: {exc}")
        errors.append(f"AI: {exc}")

    print("\n[3] Telegram:")
    if _configured(config.telegram.token) and _configured(config.telegram.chat_id):
        try:
            from bot.telegram_bot import TelegramBot
            ok = await TelegramBot().send("<b>[TEST]</b> GoldAI Ultra ulanish testi")
            print(f"    [{'OK' if ok else '!!'}] Telegram: {'xabar yuborildi' if ok else 'yuborilmadi'}")
            if not ok:
                errors.append("Telegram: message failed")
        except Exception as exc:
            print(f"    [!!] Telegram: {type(exc).__name__}: {exc}")
            errors.append(f"Telegram: {exc}")
    else:
        print("    [ -] Telegram kaliti/chat ID kiritilmagan (ixtiyoriy)")

    print("\n[4] ForexClub MT5:")
    mt5_ok = False
    try:
        from engines.market_data import MultiMarketDataEngine
        market = MultiMarketDataEngine()
        mt5_ok = market.connect_mt5()
        if mt5_ok:
            account = market.get_account_info()
            print(
                f"    [OK] MT5: Login={account.get('login')} | "
                f"Server={market.connected_server or account.get('server')} | "
                f"Balans={account.get('balance', 0):.2f} {account.get('currency', '')}"
            )
            print(f"         Aniqlangan symbol: {len(market._actual_symbols)}/{len(config.markets)}")
            market.disconnect_mt5()
        else:
            print(f"    [!!] MT5: {market.last_connection_error or 'ulanish amalga oshmadi'}")
            print("         MT5 terminalini oching, login qiling, AutoTrading ni yoqing va server nomini tekshiring.")
            errors.append("MT5: connection failed")
    except Exception as exc:
        print(f"    [!!] MT5: {type(exc).__name__}: {exc}")
        errors.append(f"MT5: {exc}")

    print("\n" + "=" * 68)
    if errors:
        print(f"[!!] {len(errors)} muammo topildi. Yuqoridagi aniq xatolarni tuzating.")
    else:
        print("[OK] Barcha tekshiruvlar muvaffaqiyatli o'tdi.")
    print("=" * 68)
    return not errors and mt5_ok


async def run_bot_only():
    from core.orchestrator import UltraOrchestrator
    bot = UltraOrchestrator()
    loop = asyncio.get_running_loop()

    def _shutdown_handler():
        print("\n[!!] To'xtatish signali qabul qilindi...")
        loop.create_task(bot.stop_async())

    for sig_name in ("SIGINT", "SIGTERM"):
        try:
            import signal
            loop.add_signal_handler(getattr(signal, sig_name), _shutdown_handler)
        except (AttributeError, NotImplementedError):
            pass
    await bot.start()


async def run_api_and_bot():
    import uvicorn
    from api.main import app
    from core.orchestrator import UltraOrchestrator

    bot = UltraOrchestrator()
    # API lifespan reuses this exact object; it must not create a second MT5
    # session, second Telegram poller or second trading loop.
    app.state.orchestrator = bot
    uv_config = uvicorn.Config(
        app, host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")),
        log_level="warning", proxy_headers=True,
    )
    server = uvicorn.Server(uv_config)
    await asyncio.gather(bot.start(), server.serve())


def main() -> None:
    parser = argparse.ArgumentParser(description="GoldAI Ultra — ForexClub MT5")
    parser.add_argument("--bot", action="store_true", help="Faqat trading loop")
    parser.add_argument("--api", action="store_true", help="Faqat FastAPI")
    parser.add_argument("--test", action="store_true", help="Diagnostika")
    args = parser.parse_args()

    if not check_env() and not args.test:
        print("\n[!!] MT5 majburiy konfiguratsiya to'liq emas. .env.example asosida .env ni to'ldiring.")
        raise SystemExit(1)
    if args.test:
        raise SystemExit(0 if asyncio.run(run_system_test()) else 1)
    if args.bot:
        print("\n[>>] ForexClub MT5 trading bot ishga tushmoqda...")
        asyncio.run(run_bot_only())
    elif args.api:
        print("\n[>>] FastAPI server ishga tushmoqda...")
        import uvicorn
        uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.getenv("API_PORT", "8000")), reload=False)
    else:
        print("\n[>>] Trading bot + API server ishga tushmoqda...")
        asyncio.run(run_api_and_bot())


if __name__ == "__main__":
    main()
