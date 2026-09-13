# GoldAI Ultra — ForexClub / Libertex MT5

GoldAI Ultra MT5 terminal orqali ForexClub/Libertex hisobidan bozor ma'lumotlarini oladi, risk bilan signal yaratadi va sozlangan rejimda order yuboradi. **Bu foyda kafolati emas. Avval Demo hisobda tekshiring.**

## 1. Birgina `.bat` bilan ishga tushirish

Windows 10/11 kompyuterida:

1. ForexClub/Libertex MT5 terminalini o'rnating.
2. Repo papkasidan `START_GOLDAI.bat` ni ikki marta bosing.
3. Birinchi ishga tushishda u `.venv` va paketlarni o'rnatadi, `.env` yaratadi va to'xtaydi.
4. `.env` ni tahrirlang, keyin yana `START_GOLDAI.bat` ni bosing.
5. Bat fayli bot + FastAPI serverni ishga tushiradi. Bot xato bilan chiqsa, 15 soniyadan keyin xavfsiz qayta urinadi.

`setup_autologin.bat` endi registry'ga auto-login yozmaydi; u faqat asosiy launcher'ga yo'naltiradi. Windows parolsiz auto-login qilish xavfsiz emas.

## 2. `.env` sozlamalari

`.env.example` to'liq namuna. Asosiy qiymatlar:

```env
MT5_LOGIN=12345678
MT5_PASSWORD=MT5_HISOB_PAROLI
MT5_SERVER=ForexClub-MT5 Demo Server
MT5_PATH=C:\Program Files\ForexClub MT5\terminal64.exe
TRADING_MODE=live

AI_PROVIDER_ORDER=deepseek,gemini,openai
DEEPSEEK_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
```

- `MT5_PASSWORD` — MT5 hisob paroli; Libertex web-kabinet paroli bo'lmasligi mumkin.
- `MT5_SERVER` ni MT5 login oynasi yoki kabinetdagi qiymat bilan **aynan** bir xil yozing. `Demo` va `Real` serverlari almashmaydi.
- `MT5_PATH` bo'sh bo'lsa, dastur ochiq MT5 terminaliga ulanadi. Noto'g'ri yo'l bo'lsa, launcher baribir odatiy IPC ulanishini sinaydi.
- `TRADING_MODE=live` orderlarni MT5 ga yuboradi, `paper` real order yubormaydi, `auto` balans $5 dan kam bo'lsa paper rejimga o'tadi.
- Gemini uchun hozir `GEMINI_MODEL=gemini-2.5-flash` ishlating; eski `gemini-2.0-flash` modeliga yangi so'rovlar 404 qaytarishi mumkin.
- Birinchi test uchun `MT5_SERVER=ForexClub-MT5 Demo Server` va `TRADING_MODE=live` ishlating — orderlar Demo hisobda qoladi.

## 3. AI kalitlari va failover

DeepSeek kodi avval faqat DeepSeek'ni chaqirgan. Endi `DeepSeekAgent` uchta HTTP provider'ni qo'llaydi:

1. `AI_PROVIDER_ORDER` dagi tartibda DeepSeek.
2. Quota, 401/402, rate-limit, server yoki network xatosida Gemini.
3. Keyin OpenAI.

Provider javob bermasa, bot har bir siklda qayta-qayta urilmaydi — vaqtinchalik cooldown ishlaydi. AI ishlamasa texnik signal/risk tizimi ishlashda davom etadi; AI foyda yoki order kafolati emas.

Kamida bittasi yetarli:

```env
# DeepSeek: https://platform.deepseek.com
DEEPSEEK_API_KEY=...

# Gemini: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash

# OpenAI: https://platform.openai.com/api-keys
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
```

API kalitlarini GitHub, Telegram, screenshot yoki chatga yubormang. Eski repository nusxasida kalitlar bo'lgan; ular bekor qilinib, yangilari yaratilishi kerak.

## 4. MT5 ulanmaslik bo'yicha tekshiruv

`START_GOLDAI.bat` paketlarni o'zi o'rnatadi. Tashxisni qo'lda ko'rish kerak bo'lsa:

```bat
.venv\Scripts\python.exe run.py --test
```

MT5 uchun quyidagilar bajarilgan bo'lsin:

- Windows va 64-bit MT5 terminali o'rnatilgan;
- terminal bir marta qo'lda ochilgan va aynan kerakli login/server bilan kirilgan;
- `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` to'g'ri;
- MT5 ichida **Algo Trading/AutoTrading** yoqilgan;
- hisob savdo qilishga ruxsatli va bozor/sessiya ochiq;
- ForexClub symbol oynasida kerakli symbol ko'rinadi.

Dastur broker suffixlarini (`EURUSD.a`, `EURUSDm`, `BTCUSD.` va hokazo) avtomatik izlaydi. Ulanishdan keyin `/api/v2/health` quyidagilarni ko'rsatadi:

- `mt5_connected`;
- haqiqiy server;
- oxirgi MT5 xatosi;
- AI providerlar holati.

Bot boshlang'ich ulanish muvaffaqiyatsiz bo'lsa, soxta real trade qilmaydi: diagnostik/degraded rejimda qoladi va keyingi siklda MT5'ga qayta ulanadi.

## 5. Ishlash rejimi va xavfsizlik

- Har bir orderda SL majburiy.
- Risk tier balansga qarab hisoblanadi.
- MT5 `SymbolInfo` ning `trade_mode` va broker qo'llaydigan filling mode qiymatlari tekshiriladi.
- Position sizing symbol contract size, volume min/max/step va tick qiymatiga moslashtiriladi.
- Bot restart bo'lganda MT5 pozitsiyalarini qayta ko'radi.
- Tizim bozor yopiq, symbol yo'q, AutoTrading o'chiq yoki margin yetarli emas bo'lsa order yubormaydi.
- Brokerning minimal loti hisoblangan risk lotidan katta bo'lsa, `live` trade xavfsizlik uchun bloklanadi; kichik hisobda majburan ortiqcha risk olinmaydi.

Forex leverage va CFD juda yuqori xavfga ega. `$10 → $1,000,000` loyiha shiori, moliyaviy natija va'dasi emas.

## 6. API

Launcher default rejimda bot bilan birga `API_PORT` (standart `8000`) da server ochadi:

| Endpoint | Vazifa |
|---|---|
| `GET /api/v2/health` | MT5, bot va AI provider diagnostikasi |
| `GET /api/v2/dashboard` | Hisob, risk, pozitsiyalar, AI holati |
| `GET /api/v2/markets` | Aktiv marketlar va tier |
| `GET /api/v2/scan` | MT5 OHLC asosida skanerlash |
| `GET /api/v2/market/EURUSD/tick` | Tick |
| `POST /api/v2/trade/close-all` | Barcha pozitsiyalarni yopish |
| `POST /api/v2/system/stop` | Botni to'xtatish |

API default authentication'siz. Uni internetga port-forward qilmang; lokal kompyuterda ishlating yoki reverse proxy/auth qo'shing.

## 7. Ixtiyoriy komponentlar

- Telegram: `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID` bo'lsa alert/command ishlaydi.
- PostgreSQL/Redis: bo'lmasa bot memory mode'da ishlaydi. `setup_db.py` faqat ixtiyoriy.
- Binance: `ENABLE_BINANCE=true` bo'lsa crypto fallback; asosiy ijrochi baribir MT5.

## 8. Tuzatilgan asosiy muammolar

- Upload paytida yo'qolgan `core/`, `engines/`, `agents/`, `bot/`, `api/` package tuzilmasi qayta tiklandi.
- API lifespan'dagi `async initialize()` await qilinmasligi va bot/API uchun ikki orchestrator yaratilishi tuzatildi.
- MT5 ikki marta initialize qilinmasligi, terminal path fallback'i va reconnect loop qo'shildi.
- Hozirgi MT5 build'larida mavjud bo'lmagan `info.trade_allowed` murojaati `trade_mode` bilan moslashtirildi.
- Broker filling flags va `DONE_PARTIAL` order javobi to'g'ri ishlanadi.
- DeepSeek HTTP 402/quota muammosida Gemini/OpenAI failover qo'shildi.
- Hard-coded DB parollari va generated log/cache fayllari repository'dan chiqarildi.

## 9. Qo'lda ishga tushirish

```bash
python run.py --test       # diagnostika
python run.py --bot        # bot loop
python run.py --api        # faqat API
python run.py              # bot + API
```

MT5 live savdoni Linux/Mac'da ishlatish mo'ljallanmagan: MT5 Python bridge uchun Windows terminali kerak. Linux'da source/import testlari ishlashi mumkin, lekin order yuborilmaydi.
