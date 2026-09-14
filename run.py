"""
GoldAI Ultra — Asosiy ishga tushirish skripti
Libertex (ForexClub) Edition

Foydalanish:
    python run.py           # Bot + API server birga
    python run.py --bot     # Faqat trading bot (Libertex MT5)
    python run.py --api     # Faqat FastAPI server
    python run.py --test    # Tizim tekshiruvi (Libertex)
"""

import sys
import os
import asyncio
import argparse

# Encoding fix for Windows
import io
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def check_env():
    """Muhit o'zgaruvchilarini tekshirish — Libertex"""
    from dotenv import load_dotenv
    load_dotenv()

    required = {
        "MT5_LOGIN": os.getenv("MT5_LOGIN"),
        "MT5_PASSWORD": os.getenv("MT5_PASSWORD"),
        "MT5_SERVER": os.getenv("MT5_SERVER"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
    }
    optional = {
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
        "ENABLE_BINANCE": os.getenv("ENABLE_BINANCE", "false"),
        "DB_URL": os.getenv("DB_URL"),
    }

    print("=" * 55)
    print("  GoldAI Ultra — Libertex Edition — Muhit tekshiruvi")
    print("=" * 55)
    print(f"  Broker: {os.getenv('BROKER', 'ForexClub')} | Server: {os.getenv('MT5_SERVER', '?')}")
    print("=" * 55)

    all_ok = True
    for key, val in required.items():
        status = "OK" if val else "MISSING"
        mark = "[OK]" if val else "[!!]"
        print(f"  {mark} {key}: {status}")
        if not val:
            all_ok = False

    for key, val in optional.items():
        status = "OK" if val else "not set"
        mark = "[OK]" if val else "[ -]"
        # ENABLE_BINANCE uchun maxsus
        if key == "ENABLE_BINANCE":
            status = "YOQILGAN" if val and val.lower() == "true" else "O'CHIQ (Libertex rejimi)"
            mark = "[ -]" if val and val.lower() == "true" else "[OK]"
        print(f"  {mark} {key}: {status} (optional)")

    # Libertex eslatmasi
    print("\n  💡 Libertex kabinetida MT5 ma'lumotlarini tekshiring:")
    print("     Libertex → Mening hisoblarim → MT5 → Login/Parol/Server")
    return all_ok


async def run_system_test():
    """Tizim komponentlarini test qilish — Libertex"""
    from dotenv import load_dotenv
    load_dotenv()

    print("=" * 55)
    print("  GoldAI Ultra — Libertex Tizim Testi")
    print("=" * 55)

    errors = []

    # 1. Import test
    print("\n[1] Modullar:")
    modules = [
        ("core.config", "AppConfig"),
        ("core.logger", "logger"),
        ("engines.liquidity_engine", "LiquidityEngine"),
        ("engines.smc_engine", "SMCEngine"),
        ("agents.deepseek_agent", "DeepSeekAgent"),
        ("bot.telegram_bot", "TelegramBot"),
        ("engines.market_data", "MultiMarketDataEngine"),
        ("engines.risk_engine", "DynamicRiskEngine"),
        ("engines.execution_engine", "ExecutionEngine"),
        ("engines.whale_monitor", "WhaleMonitor"),
        ("engines.market_scanner", "MultiMarketScanner"),
    ]
    for mod, cls in modules:
        try:
            m = __import__(mod, fromlist=[cls])
            getattr(m, cls)
            print(f"    [OK] {mod}.{cls}")
        except Exception as e:
            print(f"    [!!] {mod}.{cls}: {e}")
            errors.append(f"{mod}: {e}")

    # 2. Telegram test
    print("\n[2] Telegram:")
    try:
        from bot.telegram_bot import TelegramBot
        bot = TelegramBot()
        ok = await bot.send(
            "<b>[TEST]</b> GoldAI Ultra Libertex testi... \n"
            "Agar bu xabarni ko'rsangiz, Telegram ishlaydi!"
        )
        print(f"    [{'OK' if ok else '!!'}] Telegram: {'xabar yuborildi' if ok else 'yuborilmadi'}")
        if not ok:
            errors.append("Telegram: xabar yuborilmadi")
    except Exception as e:
        print(f"    [!!] Telegram: {e}")
        errors.append(f"Telegram: {e}")

    # 3. DeepSeek API test
    print("\n[3] DeepSeek AI:")
    try:
        from agents.deepseek_agent import DeepSeekAgent
        ai = DeepSeekAgent()
        if ai.api_key:
            result = await ai.quick_review(
                {"scanned": 5, "signals": 2, "best_symbol": "EURUSD",
                 "best_confidence": 78.5, "sentiment": "RISK_ON", "market_types": {}},
                {"balance": 1000, "equity": 1010}
            )
            print(f"    [OK] DeepSeek: {'javob olindi' if result else 'javob yoq (lekin ulandi)'}")
        else:
            print("    [ -] DeepSeek: API key yo'q (optional)")
    except Exception as e:
        print(f"    [ -] DeepSeek: {e}")

    # 4. MT5 test — Libertex ASOSIY
    print("\n[4] Libertex MT5:")
    mt5_ok = False
    try:
        import MetaTrader5 as mt5
        from core.config import config
        # MT5_PATH berilgan bo'lsa
        if config.mt5.path:
            mt5.initialize(path=config.mt5.path)
        else:
            mt5.initialize()
        # Login sinash
        login_ok = mt5.login(login=config.mt5.login, password=config.mt5.password, server=config.mt5.server)
        if login_ok:
            info = mt5.account_info()
            print(f"    [OK] Libertex MT5: {config.mt5.server}")
            print(f"         Login={info.login} | Balans=${info.balance:.2f} {info.currency} | Leverage 1:{info.leverage}")
            # Symbol tekshiruvi
            symbols = [s.name for s in (mt5.symbols_get() or [])[:5]]
            print(f"         Simvollar: {', '.join(symbols)}...")
            mt5.shutdown()
            mt5_ok = True
        else:
            err = mt5.last_error()
            print(f"    [!!] MT5 login xato: {err}")
            print(f"         Server: {config.mt5.server} | Login: {config.mt5.login}")
            print("         Libertex kabinetidagi server nomini 100% aniq ko'chiring!")
            # Fallback serverlar
            print(f"         Fallback: {config.mt5.fallback_servers[:3]}")
            mt5.shutdown()
            errors.append(f"MT5 login: {err}")
    except ImportError as e:
        print(f"    [!!] MetaTrader5 kutubxonasi topilmadi: {e}")
        print("         pip install MetaTrader5")
        errors.append(f"MT5 lib: {e}")
    except Exception as e:
        print(f"    [!!] MT5: {e}")
        errors.append(f"MT5: {e}")

    # 5. Binance (faqat yoqilgan bo'lsa)
    print("\n[5] Binance (ixtiyoriy):")
    from core.config import config as cfg2
    if cfg2.enable_binance:
        try:
            from engines.binance_executor import BinanceExecutor
            be = BinanceExecutor()
            acct = await be.get_account_info()
            bal = acct.get("balance", 0)
            src = acct.get("source", "?")
            print(f"    [OK] Binance {src} | Balans: ${bal:.2f} USDT")
        except Exception as e:
            print(f"    [!!] Binance: {e}")
            errors.append(f"Binance: {e}")
    else:
        print("    [ -] O'CHIQ (Libertex rejimi — kerak emas)")

    print("\n" + "=" * 55)
    if mt5_ok:
        mode = f"LIBERTEX MT5 ({config.mt5.broker})"
    elif cfg2.enable_binance:
        mode = "BINANCE MODE (fallback)"
    else:
        mode = "DEMO (MT5 ulanmadi)"
    print(f"[>>] Aktiv rejim: {mode}")
    if errors:
        print(f"[!!] {len(errors)} muammo topildi:")
        for e in errors:
            print(f"     - {e}")
        if not mt5_ok:
            print("\n💡 Libertex MT5 ni sozlash:")
            print("   1. Libertex kabinetiga kiring → MT5 hisob → Login/Parol/Server ni ko'chiring")
            print("   2. .env da MT5_SERVER ni aynan kabinetdagidek yozing")
            print("   3. MT5 terminal o'rnatilganligini tekshiring")
    else:
        print("[OK] Barcha testlar o'tdi! Libertex MT5 ishga tayyor. 🚀")
    print("=" * 55)
    return len(errors) == 0 and mt5_ok


async def run_bot_only():
    """Faqat trading bot — Libertex"""
    import signal
    from dotenv import load_dotenv
    load_dotenv()
    from core.orchestrator import UltraOrchestrator
    bot = UltraOrchestrator()

    loop = asyncio.get_event_loop()

    def _shutdown_handler():
        print("\n[!!] Signal qabul qilindi — bot to'xtatilmoqda...")
        loop.create_task(bot.stop_async())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown_handler)
        except Exception:
            pass

    await bot.start()


async def run_api_and_bot():
    """Bot + FastAPI server parallel"""
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()

    from api.main import app
    from core.orchestrator import UltraOrchestrator

    bot = UltraOrchestrator()

    config = uvicorn.Config(
        app, host="0.0.0.0", port=int(os.getenv("API_PORT", 8000)),
        log_level="warning"
    )
    server = uvicorn.Server(config)

    await asyncio.gather(
        bot.start(),
        server.serve()
    )


def main():
    parser = argparse.ArgumentParser(description="GoldAI Ultra — Libertex Edition")
    parser.add_argument("--bot", action="store_true", help="Faqat trading bot (Libertex MT5)")
    parser.add_argument("--api", action="store_true", help="Faqat API server")
    parser.add_argument("--test", action="store_true", help="Tizim testi (Libertex)")
    args = parser.parse_args()

    if not check_env():
        print("\n[!!] Muhim o'zgaruvchilar topilmadi! .env faylini tekshiring.")
        if not args.test:
            sys.exit(1)

    if args.test:
        ok = asyncio.run(run_system_test())
        sys.exit(0 if ok else 1)

    elif args.bot:
        print("\n[>>] Libertex MT5 Trading Bot ishga tushmoqda...")
        asyncio.run(run_bot_only())

    elif args.api:
        print("\n[>>] Faqat FastAPI server ishga tushmoqda...")
        import uvicorn
        from dotenv import load_dotenv
        load_dotenv()
        uvicorn.run("api.main:app", host="0.0.0.0",
                    port=int(os.getenv("API_PORT", 8000)), reload=False)

    else:
        print("\n[>>] Bot (Libertex) + API server birga ishga tushmoqda...")
        asyncio.run(run_api_and_bot())


if __name__ == "__main__":
    main()
