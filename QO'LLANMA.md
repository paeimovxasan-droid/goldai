# 📖 GoldAI Ultra — Libertex Edition | To'liq O'rnatish va Ishlatish Qo'llanmasi

> **Broker:** ForexClub / Libertex via MetaTrader 5  
> **Rejim:** Libertex MT5 — ASOSIY | Binance faqat `ENABLE_BINANCE=true` bo'lsa (ixtiyoriy)  
> **Maqsad:** $10 → $1,000,000 Capital Growth  
> **Versiya:** 2.1.0-libertex

---

## 📑 Mundarija

1. [Tizim talablari](#1-tizim-talablari)
2. [Libertex hisob ochish](#2-libertex-hisob-ochish)
3. [MT5 terminal o'rnatish (Windows)](#3-mt5-terminal-ornatish-windows)
4. [Loyihani yuklab olish](#4-loyihani-yuklab-olish)
5. [Python muhitini sozlash](#5-python-muhitini-sozlash)
6. [.env faylini to'ldirish](#6-env-faylini-toldirish)
7. [Telegram bot sozlash](#7-telegram-bot-sozlash)
8. [DeepSeek AI (ixtiyoriy)](#8-deepseek-ai-ixtiyoriy)
9. [Ma'lumotlar bazasi (ixtiyoriy)](#9-malumotlar-bazasi-ixtiyoriy)
10. [Test qilish](#10-test-qilish)
11. [Botni ishga tushirish](#11-botni-ishga-tushirish)
12. [Telegram buyruqlari](#12-telegram-buyruqlari)
13. [Kapital o'sishi tizimi](#13-kapital-osishi-tizimi)
14. [Xavfsizlik va maxfiylik](#14-xavfsizlik-va-maxfiylik)
15. [Loyiha tuzilmasi](#15-loyiha-tuzilmasi)
16. [Libertex vs Binance](#16-libertex-vs-binance)
17. [Tez-tez uchraydigan xatolar](#17-tez-tez-uchraydigan-xatolar)
18. [Foydali havolalar](#18-foydali-havolalar)

---

## 1. Tizim talablari

| Komponent | Talab | Izoh |
|-----------|-------|------|
| **OS** | Windows 10/11 (tavsiya) | MT5 faqat Windows da to'liq ishlaydi. Linux da import testi o'tadi, lekin savdo qilinmaydi |
| **Python** | 3.10+ (3.11 tavsiya) | https://python.org |
| **RAM** | 4 GB+ | 8 GB tavsiya |
| **Internet** | Barqaror | Telegram + MT5 + yangiliklar |
| **Libertex hisobi** | Real yoki Demo | https://libertex.org |
| **Telegram** | BotFather orqali bot | https://t.me/BotFather |

> ⚠️ **Linux / Mac** da `MetaTrader5` kutubxonasi o'rnatilmaydi — bu normal. Kod `MockMT5` bilan import o'tadi, lekin jonli savdo faqat Windows da MT5 terminal bilan ishlaydi.

---

## 2. Libertex hisob ochish

### 2.1 Ro'yxatdan o'tish
1. https://libertex.org ga kiring
2. "Ro'yxatdan o'tish" → Email / telefon → Parol
3. Shaxsni tasdiqlash (KYC) — pasport / ID karta
4. Hisob tasdiqlangandan keyin kirish

### 2.2 MT5 ma'lumotlarini olish
1. Libertex kabinetiga kiring → **"Mening hisoblarim"** yoki **"My Accounts"**
2. **MT5** yorlig'ini tanlang
3. Quyidagilarni **aniq** ko'chirib oling:
   - **Login** — masalan `227427278` (raqam)
   - **Parol** — MT5 paroli (Libertex parolidan farq qilishi mumkin)
   - **Server** — masalan `ForexClub-MT5 Real Server`

> 🚨 **DIQQAT:** Server nomini **100% aynan** ko'chirishingiz shart!  
> `ForexClub-MT5 Real Server` ≠ `ForexClub-MT5Real` ≠ `ForexClub-MT5 Demo Server`  
> Bitta harf / bo'shliq xatosi ham ulanishni buzadi.

### 2.3 ForexClub MT5 serverlari jadvali

| Hisob turi | Server nomi (aniq) | Manzil (texnik) |
|------------|--------------------|-----------------|
| **Real** | `ForexClub-MT5 Real Server` | `mt5-real-prim.fxclub.org` (213.108.251.212) |
| **Real 2** | `ForexClub-MT5 Real Server 2` | alternativ |
| **Demo** | `ForexClub-MT5 Demo Server` | `mt5-demo-prim.fxclub.org` |
| **Demo 2** | `ForexClub-MT5 Demo Server 2` | alternativ |

> 💡 **Tavsiya:** Avval Demo da test qiling, keyin Real ga o'ting.

---

## 3. MT5 terminal o'rnatish (Windows)

### 3.1 Yuklab olish
- To'g'ridan-to'g'ri Libertex kabinetidan: **MT5 ni yuklab olish** tugmasi
- Yoki ForexClub: https://www.fxclub.org → Platformalar → MetaTrader 5
- Yoki MetaQuotes: https://www.metatrader5.com

### 3.2 O'rnatish
1. `forexclub5setup.exe` ni ishga tushiring
2. Standart o'rnatish → `C:\Program Files\ForexClub MT5\`
3. Terminal ochilganda → **Fayl → Hisobga kirish**
4. Login / Parol / Server ni kiriting → **OK**
5. Pastki qismda **"Ulanish: ForexClub-MT5 Real Server"** va narxlar ko'rinsa — tayyor!

> ✅ **Tekshirish:** Terminalda `Bozor kuzatuvi` (Market Watch) da `EURUSD`, `XAUUSD`, `BTCUSD` ko'rinishi kerak. Agar ko'rinmasa, sichqoncha o'ng tugma → "Hammasini ko'rsatish".

### 3.3 MT5 yo'li (.env da MT5_PATH)
- Odatda kerak emas (avtomatik topiladi)
- Agar bir nechta MT5 o'rnatilgan bo'lsa:
  ```
  MT5_PATH=C:\Program Files\ForexClub MT5\terminal64.exe
  ```

---

## 4. Loyihani yuklab olish

```bash
# Git orqali
git clone https://github.com/paeimovxasan-droid/goldai.git
cd goldai

# Libertex branch (agar kerak bo'lsa)
git checkout arena/01a097a5-goldai

# Yoki ZIP yuklab → papkaga oching
```

---

## 5. Python muhitini sozlash

### 5.1 Windows

```powershell
# Python 3.11 o'rnating: https://python.org/downloads

# Loyiha papkasida
python -m venv venv
venv\Scripts\activate

# Kutubxonalarni o'rnatish
pip install --upgrade pip
pip install -r requirements.txt

# Agar requirements.txt bo'lmasa, qo'lda:
pip install MetaTrader5 python-dotenv aiohttp pandas numpy asyncpg fastapi uvicorn python-telegram-bot
```

### 5.2 Linux (faqat test / development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install python-dotenv aiohttp pandas numpy asyncpg fastapi uvicorn --break-system-packages
# MetaTrader5 Linux da o'rnatilmaydi — MockMT5 ishlatiladi (savdo yo'q, faqat test)
```

### 5.3 requirements.txt namunasi

Agar fayl bo'lmasa, yarating:

```
MetaTrader5
python-dotenv
aiohttp
pandas
numpy
asyncpg
fastapi
uvicorn
```

---

## 6. .env faylini to'ldirish

### 6.1 Nusxalash

```bash
cp .env.example .env
# Windows PowerShell:
copy .env.example .env
```

### 6.2 To'ldirish — barcha maydonlar

```ini
# ─── Libertex / ForexClub MT5 — ASOSIY ────────────────────────
# Libertex kabinetidan ANIQ ko'chiring!
MT5_LOGIN=227427278
MT5_PASSWORD=Buni090701@
MT5_SERVER=ForexClub-MT5 Real Server
MT5_PATH=
BROKER=ForexClub

# ─── Binance (Ixtiyoriy — O'CHIQ) ─────────────────────────────
# Libertex rejimida Binance kerak EMAS!
# Faqat qo'shimcha orderbook/funding ma'lumotlari uchun, yoqsangiz:
ENABLE_BINANCE=false
BINANCE_API_KEY=
BINANCE_SECRET_KEY=
BINANCE_TESTNET=true

# ─── DeepSeek AI ──────────────────────────────────────────────
# https://platform.deepseek.com → API Keys → Create
DEEPSEEK_API_KEY=sk-...

# ─── Telegram ─────────────────────────────────────────────────
# @BotFather → /newbot → token oling
# @userinfobot → chat_id oling
TELEGRAM_BOT_TOKEN=1234567890:AAH...
TELEGRAM_CHAT_ID=1234567890

# ─── Database (ixtiyoriy) ────────────────────────────────────
DB_URL=postgresql://ultra:ultra123@localhost:5432/goldai_ultra
REDIS_URL=redis://localhost:6379
API_PORT=8000
SECRET_KEY=ultra-secret-key-2025
DEBUG=false
```

### 6.3 Muhim eslatmalar

- `MT5_SERVER` ni **qo'shtirnoqsiz** yozing: `ForexClub-MT5 Real Server` (to'g'ri)
- `MT5_PASSWORD` da maxsus belgilar bo'lsa (`@`, `#`, `!`) — to'g'ridan-to'g'ri yozing, qochirish shart emas
- `ENABLE_BINANCE=false` qoldiring — Libertex yetarli! Faqat Binance ham kerak bo'lsa `true` qiling va API kalitlarni to'ldiring
- `.env` **hech qachon** git ga kirmaydi (`.gitignore` da). Faqat `.env.example` commit qilinadi

---

## 7. Telegram bot sozlash

### 7.1 Bot yaratish

1. Telegram da `@BotFather` ni oching
2. `/newbot` → nom: `GoldAI Ultra Bot` → username: `goldai_ultra_xxxx_bot`
3. Token ni oling: `1234567890:AAH...` → `.env` ga qo'ying

### 7.2 Chat ID olish

1. `@userinfobot` ni oching → `/start` → `Id: 1234567890` ni oling → `.env` ga `TELEGRAM_CHAT_ID` ga qo'ying
2. Yoki botga biror xabar yozing → `https://api.telegram.org/bot<TOKEN>/getUpdates` dan `chat.id` ni oling

### 7.3 Botni test qilish

```bash
python test_telegram.py
# Telegram da "Test xabar" kelishi kerak
```

---

## 8. DeepSeek AI (ixtiyoriy)

1. https://platform.deepseek.com → Ro'yxatdan o'tish
2. **API Keys** → **Create New** → `sk-...` ni nusxalash → `.env` ga
3. Bo'lmasa ham bot ishlaydi, faqat `/ask` va AI tahlil o'chadi

---

## 9. Ma'lumotlar bazasi (ixtiyoriy)

> **Majburiy emas!** `TradeHistory` DB ulanmasa — xotira rejimida ishlaydi (loglar `logs/` da saqlanadi).

### PostgreSQL o'rnatish (Windows)

1. https://www.postgresql.org/download/ → o'rnating
2. `init.sql` ni ishga tushiring:

```bash
psql -U postgres -f database/init.sql
# Yoki pgAdmin da database/init.sql ni ochib Run
```

3. `.env` da `DB_URL` ni to'g'rilang

### DBsiz ishlatish

- Hech narsa qilmasangiz ham bo'ladi — `TradeHistory: xotira rejimi` logi chiqadi
- Savdolar `logs/trades.log` va `goldai_state.json` da saqlanadi

---

## 10. Test qilish

### 10.1 Hamma narsani tekshirish

```bash
python run.py --test
```

**Muvaffaqiyatli natija:**

```
[OK] 1/5 .env fayli
[OK] 2/5 Telegram
[OK] 3/5 Libertex MT5: ForexClub-MT5 Real Server | Balans $123.45 | Leverage 1:500
[OK] 4/5 Strategiya: 45% ishonch + ADX≥20 + H1 EMA21/50 tekshirildi
[OK] 5/5 Simvollar: 5/6 yuklandi (EURUSD, XAUUSD, BTCUSD...)

✅ Hamma testlar o'tdi! Botni ishga tushiring: python run.py --bot
```

### 10.2 MT5 ulanmadi — nima qilish?

```
[FAIL] 3/5 Libertex MT5: MT5 initialize -10003 IPC not found
```

**Yechim:**
1. MT5 terminal ochiqmi? → Ochib qo'ying, login qiling
2. `.env` da server nomi 100% to'g'rimi? → Libertex kabinetidan qayta nusxalang
3. `MT5_PATH` ni to'g'rilang: `C:\Program Files\ForexClub MT5\terminal64.exe`
4. Antivirus / Firewall MT5 ni bloklamayaptimi?

Agar `ENABLE_BINANCE=false` bo'lsa, bot **demo rejimda** davom etadi (savdo qilmaydi, faqat signal tahlili).

### 10.3 Python import testi

```bash
python -c "from core.config import config; print(config.mt5.broker, config.mt5.server, config.enable_binance)"
# ForexClub ForexClub-MT5 Real Server False  ← to'g'ri

python -c "from core.orchestrator import UltraOrchestrator; print('OK')"
# OK  ← hamma import ishlaydi
```

---

## 11. Botni ishga tushirish

### 11.1 Asosiy ishga tushirish

```bash
python run.py --bot
```

**Log:**

```
🚀 GoldAI Ultra — Libertex Edition
   Broker: ForexClub | Server: ForexClub-MT5 Real Server
✅ Rejim: LIBERTEX MT5 MODE (ForexClub | Forex + Crypto + Stocks)
🏦 Libertex hisob: Login=227427278 | Server=ForexClub-MT5 Real Server | Leverage 1:500
💰 Balans: $123.45 | Tier: MINI
📊 Aktiv bozorlar (7): EURUSD, XAUUSD, BTCUSD, ETHUSD, GBPUSD, USDJPY, XAGUSD
🔄 Multi-Market loop boshlandi [Libertex MT5 (ForexClub)]...
🤖 Telegram polling tayyor
```

Telegram da:

```
🚀 GOLDAI ULTRA — ISHGA TUSHDI!
💰 Balans: $123.45
🏅 Tier: 🟢 Mini ($100–$500)
🌐 Aktiv bozorlar: 7 ta
🏦 Broker: ForexClub-MT5 Real Server
```

### 11.2 Boshqa rejimlar

```bash
python run.py --bot --dry-run   # Paper trading (real savdo yo'q)
python run.py --api             # Faqat FastAPI server (port 8000)
python run.py --help            # Barcha parametrlar
```

### 11.3 To'xtatish

- `Ctrl+C` → state `goldai_state.json` ga saqlanadi → keyingi safar davom etadi
- Telegram: `/stop`

### 11.4 Avtomatik ishga tushirish (Windows)

**Task Scheduler:**

1. `taskschd.msc` → "Vazifa yaratish"
2. Trigger: "Kompyuter yoqilganda"
3. Action: `python C:\path\to\goldai\run.py --bot`
4. "Foydalanuvchi tizimga kirgan-kirmaganidan qat'iy nazar" + "Eng yuqori huquqlar"

Yoki **.bat** fayl:

```bat
@echo off
cd /d C:\path\to\goldai
call venv\Scripts\activate
python run.py --bot
pause
```

---

## 12. Telegram buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start`, `/help` | Buyruqlar ro'yxati |
| `/status` | Bot holati, balans, tier, blackout |
| `/trades` | Ochiq savdolar live P/L |
| `/positions` | MT5 pozitsiyalari |
| `/history` | So'nggi 10 savdo |
| `/stats` | To'liq statistika (WR, P/L) |
| `/market` | Fear&Greed + yangiliklar |
| `/scan BTCUSD` | AI signal tahlili (M15 + cluster) |
| `/buy BTCUSD` | Qo'lda BUY |
| `/sell EURUSD` | Qo'lda SELL |
| `/auto` | Avtonomiya on/off |
| `/closeall` | Barcha pozitsiyalarni yopish |
| `/ask BTC qanday?` | DeepSeek AI chat |
| `/stop` | Botni to'xtatish |

> **Libertex eslatmasi:**
> - `/orderbook`, `/cvd`, `/bigtrades` — **faqat `ENABLE_BINANCE=true` da** ishlaydi. Libertex da `ℹ️ Libertex rejimida o'chiq — o'rniga V3 Cluster ishlatiladi` deb javob beradi.
> - Tahlil uchun `/scan SYMBOL` ni ishlating — u MT5 + cluster + whale ni birlashtiradi.

### Oddiy yozish → AI chat

Telegram da slash siz yozing: `BTC bugun ko'tariladimi?` → DeepSeek javob beradi (faqat sizning `chat_id` dan).

---

## 13. Kapital o'sishi tizimi

| Balans | Tier | Risk/savdo | Max pozitsiya | Bozorlar |
|--------|------|------------|---------------|----------|
| $10–100 | 🔵 Mikro | 0.3% | 1 | 5 (EURUSD, XAUUSD, BTCUSD, ETHUSD, GBPUSD) |
| $100–500 | 🟢 Mini | 0.5% | 2 | 7 |
| $500–2K | 🟡 Standart | 0.7% | 3 | 10 |
| $2K–5K | 🟠 Advanced | 1.0% | 4 | 18 |
| $5K–10K | 🔴 Pro | 1.2% | 5 | 30+ |
| $10K–50K | 💎 Elite | 1.5% | 6 | 30+ |
| $50K–200K | 👑 Master | 1.8% | 7 | 30+ |
| $200K–1M | 🌟 Legend | 2.0% | 8 | 30+ |

- **Lot** avtomatik hisoblanadi: `risk / SL masofa`
- **SL/TP** — ATR + swing-point + smart SL (stop-hunt himoyasi)
- **Signal filtri:** 45% ishonch, ADX≥20, H1 EMA21/50 trend, session, funding (Binance da)
- **Cooldown:** SL olgandan keyin 30 daqiqa o'sha symbol da savdo yo'q

---

## 14. Xavfsizlik va maxfiylik

### 14.1 .env himoyasi

- `.env` **git ga kirmaydi** — `.gitignore` da `*.env` bor
- Commit qilinadigan faqat `.env.example` (bo'sh namuna)
- Agar tasodifan commit qilsangiz:

```bash
git rm --cached .env
echo ".env" >> .gitignore
git commit -m "Remove secret .env"
# Parollarni ALMASHTIRING! (Libertex, Telegram, DeepSeek)
```

### 14.2 Secret xavfi

- GitHub ga push qilingan secret — **darhol almashtirish** kerak (history da qoladi)
- Libertex MT5 parolini kabinetdan o'zgartiring
- Telegram tokenni @BotFather → `/revoke` bilan yangilang
- DeepSeek API key ni qayta yarating

### 14.3 Fayllar

| Fayl | Saqlanadi | Git da |
|------|-----------|--------|
| `.env` | Mahalliy, himoyalangan | ❌ Yo'q |
| `.env.example` | Namuna | ✅ Ha |
| `goldai_state.json` | State (cycle, balance) | ❌ Yo'q |
| `logs/` | Trade loglari | ❌ Yo'q |
| `__pycache__/` | Kesh | ❌ Yo'q |

---

## 15. Loyiha tuzilmasi

```
goldai/
├── core/
│   ├── config.py          # Libertex MT5 + risk + symbol config
│   ├── logger.py
│   └── orchestrator.py    # Asosiy loop — Libertex primary
├── engines/
│   ├── market_data.py     # MT5 OHLC + MockMT5 (Linux)
│   ├── execution_engine.py# MT5 savdo (buy/sell/SL/TP)
│   ├── risk_engine.py     # Lot, SL, tier
│   ├── market_scanner.py  # Signal (MT5 H1, cluster)
│   ├── cluster_engine.py  # V3 POC/VAH/VAL + CVD
│   ├── whale_monitor.py   # Libertex da guard (Binance faqat enable)
│   ├── orderbook_engine.py# Guard (Binance faqat enable)
│   ├── signal_filter.py   # Session + funding guard
│   ├── news_engine.py
│   ├── trade_history.py   # asyncpg guard
│   ├── paper_trading.py
│   └── trade_log.py
├── bot/
│   └── telegram_bot.py    # Libertex mode + /scan etc
├── api/
│   └── main.py            # FastAPI Libertex Edition v2.1.0
├── agents/
│   └── deepseek_agent.py
├── database/
│   └── init.sql
├── run.py                 # Libertex Edition entry point
├── config.py              # core/config sync (legacy)
├── .env.example           # Namuna
├── .gitignore
├── README.md              # Qisqa
└── QO'LLANMA.md           # Siz o'qiyotgan batafsil qo'llanma
```

> **Eslatma:** Ildizdagi `market_data.py`, `orchestrator.py` va hokazo — `engines/` va `core/` ning sync nusxalari (legacy kompatibilitet).

---

## 16. Libertex vs Binance

|  | Libertex (ForexClub) MT5 — ASOSIY | Binance (Ixtiyoriy) |
|--|-----------------------------------|---------------------|
| **Broker** | ForexClub / Libertex | Binance |
| **Server** | `ForexClub-MT5 Real/Demo Server` | `fapi.binance.com` |
| **Yoqish** | `ENABLE_BINANCE=false` (default) | `ENABLE_BINANCE=true` + API key |
| **Bozorlar** | Forex + Crypto CFD + Stocks + Commodities + Indices (30+) bitta hisobda | Faqat Crypto Futures |
| **Order book** | Yo'q → o'rniga **V3 Cluster + tick_volume** | Bor (depth, iceberg) |
| **Funding rate** | Yo'q → 0 | Bor (premiumIndex) |
| **Whale** | MT5 volume profile + cluster | Binance WS + OI + liquidations |
| **CVD** | Sham strukturasidan (MT5 OHLC) | Binance aggTrades dan |
| **SL/TP** | MT5 exchange SL (real) | Software SL (monitor_sl_tp) |
| **24/5 vs 24/7** | Forex 24/5, Crypto 24/7 (MT5 CFD) | 24/7 |
| **Kod** | `if not config.enable_binance: return 0/neutral` | `if config.enable_binance: fetch Binance` |

**Nega Libertex?**
- Bitta hisobda hamma bozor — diversifikatsiya
- Regulyatsiya (ForexClub) + tanish MT5 terminal
- Exchange SL — ishonchli (Binance software SL dan ko'ra)
- Lot va kredit elkalari Libertex qoidalari bo'yicha

**Binance qachon kerak?**
- Faqat qo'shimcha tahlil uchun: order book, funding, CVD, whale WS
- Yoqsangiz `.env` da `ENABLE_BINANCE=true` + `BINANCE_API_KEY/SECRET` ni to'ldiring
- Bot avtomatik Binance scan ni ham qiladi (lekin savdo baribir MT5 da)

---

## 17. Tez-tez uchraydigan xatolar

### `ModuleNotFoundError: No module named 'MetaTrader5'`
- **Sabab:** Linux da — normal, MockMT5 ishlaydi
- **Windows da:** `pip install MetaTrader5` va MT5 terminal o'rnatilgan bo'lsin

### `MT5 initialize -10003 IPC not found`
- MT5 terminal yopiq → oching va login qiling
- `MT5_PATH` ni tekshiring

### `MT5 login failed: Invalid account`
- Login/parol/server xato → Libertex kabinetidan qayta nusxalang
- Server nomida bo'shliq bor: `ForexClub-MT5 Real Server` (aynan)

### `Telegram:  Unauthorized`
- `TELEGRAM_BOT_TOKEN` xato → @BotFather dan qayta oling

### `Trade History DB ulana olmadi`
- PostgreSQL o'chirilgan → ixtiyoriy, xotira rejimida ishlaydi
- `python -m engines.trade_history` test qiling yoki DB ni o'rnating

### `Balans: $0.00 — monitoring davom etadi`
- Libertex hisobingizda mablag' yo'q → depozit qiling yoki Demo da test qiling

### `Signal yo'q`
- Bozor yon (yakshanba) yoki barcha signallar <45% / ADX<20 → normal, kuting

---

## 18. Foydali havolalar

- Libertex: https://libertex.org
- ForexClub: https://www.fxclub.org
- MT5: https://www.metatrader5.com
- Telegram BotFather: https://t.me/BotFather
- DeepSeek: https://platform.deepseek.com
- GitHub repo: https://github.com/paeimovxasan-droid/goldai

---

### 🚀 Tayyor!

```bash
python run.py --test   # Hamma yashil bo'lsa
python run.py --bot    # Botni yoqing va Telegram da /status ni tekshiring
```

Savollaringiz bo'lsa — Telegram da `/ask` orqali yoki kod ichidagi `core/logger.py` loglarini `logs/` dan tekshiring.

**Omadli savdo!** 💰 Libertex MT5 + GoldAI Ultra = $10 → $1M
