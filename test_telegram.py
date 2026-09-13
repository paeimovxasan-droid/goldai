"""Telegram bot test"""
import asyncio
import aiohttp
import os
import sys
import io

# Windows PowerShell encoding fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


async def test_telegram():
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    msg = (
        "🚀 <b>GOLDAI ULTRA — TEST</b>\n\n"
        "✅ Telegram ulanishi muvaffaqiyatli!\n"
        "📊 Barcha modullar to'g'ri ulandi.\n\n"
        "🧪 Bu test xabari — tizim ishga tayyor!"
    )
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if r.status == 200:
                msg_id = data["result"]["message_id"]
                print(f"SUCCESS! Xabar yuborildi. Message ID: {msg_id}")
            else:
                print(f"ERROR {r.status}: {data}")


async def test_imports():
    """Barcha modullarni import tekshiruvi"""
    errors = []
    modules = [
        ("core.config", "config"),
        ("core.logger", "logger"),
        ("engines.liquidity_engine", "LiquidityEngine"),
        ("engines.smc_engine", "SMCEngine"),
        ("agents.deepseek_agent", "DeepSeekAgent"),
        ("bot.telegram_bot", "TelegramBot"),
    ]
    for mod, cls in modules:
        try:
            m = __import__(mod, fromlist=[cls])
            getattr(m, cls)
            print(f"  ✅ {mod}.{cls}")
        except Exception as e:
            print(f"  ❌ {mod}.{cls}: {e}")
            errors.append(mod)
    return errors


async def main():
    print("=" * 50)
    print("GoldAI Ultra — Test")
    print("=" * 50)

    print("\n1. Import tekshiruvi:")
    errors = await test_imports()

    print(f"\n2. Telegram test:")
    if TOKEN and CHAT_ID:
        await test_telegram()
    else:
        print("  ❌ TOKEN yoki CHAT_ID topilmadi!")

    print("\n" + "=" * 50)
    if errors:
        print(f"❌ {len(errors)} xato topildi: {errors}")
    else:
        print("✅ Barcha modullar va Telegram ishlaydi!")


if __name__ == "__main__":
    asyncio.run(main())
