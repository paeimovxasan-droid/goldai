# GoldAI Ultra — Windows / ForexClub MT5 o'rnatish

Ushbu paketda haqiqiy API key, MT5 parol yoki Telegram token yo'q. Ularni faqat lokal `.env` fayliga kiriting.

## 1. Faylni joylashtirish

1. ZIP faylni Windows kompyuterga yuklab oling.
2. Masalan, `C:\Users\HP\Desktop\goldai` papkasiga extract qiling.
3. ForexClub MT5 terminalini o'rnating va Demo hisobga login qiling.
4. MT5 ichida **Algo Trading / AutoTrading** ni yoqing.

## 2. `.env` yaratish

`START_GOLDAI.bat` ni birinchi marta ishga tushiring. U `.env.example` dan lokal `.env` yaratadi va dependencylarni o'rnatadi.

Keyin aynan `goldai\.env` faylini ochib to'ldiring. `.env.example` ni emas:

```env
MT5_LOGIN=500372121
MT5_PASSWORD=MT5_ACCOUNT_PASSWORD
MT5_SERVER=ForexClub-MT5 Demo Server
MT5_PATH=C:\Program Files\ForexClub MT5\terminal64.exe

# Xavfsiz boshlang'ich rejim
TRADING_MODE=paper

# AI ixtiyoriy. Ishlatmasangiz bo'sh qoldiring.
AI_PROVIDER_ORDER=gemini,openai,deepseek
DEEPSEEK_API_KEY=
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1

# Telegram ixtiyoriy
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Google AI Studio ba'zan `GOOGLE_API_KEY` nomini ko'rsatadi. Dastur uni ham taniydi, lekin `GEMINI_API_KEY` nomidan foydalanish tavsiya qilinadi.

## 3. Tekshirish

CMD oching:

```cmd
cd /d C:\Users\HP\Desktop\goldai
python run.py --test
```

Tekshiruvda quyidagilar ko'rinishi kerak:

```text
[OK] MT5_LOGIN: kiritilgan
[OK] MT5_PASSWORD: kiritilgan
[OK] MT5_SERVER: kiritilgan
[OK] MT5: Login=... | Server=ForexClub-MT5 Demo Server
```

AI bo'lmasa ham MT5 signal va risk engine ishlaydi. `/ask` Telegram AI chat ishlamaydi, xolos.

## 4. Demo order testi

Avval `TRADING_MODE=paper` bilan ishlatib, loglarni kuzating.

Demo account'ga haqiqiy demo order yuborish uchun `.env` da:

```env
TRADING_MODE=live
```

Bu real pul degani emas, chunki `ForexClub-MT5 Demo Server` demo hisobdir. Keyin `START_GOLDAI.bat` ni qayta ishga tushiring.

Telegram bot orqali demo manual test:

```text
/buy EURUSD
```

Bot signal/risk/SL tekshiruvlaridan o'tgandan keyin MT5 demo order yuboradi. AutoTrading o'chiq, symbol mavjud emas, signal/risk mos emas yoki broker minimum loti riskdan katta bo'lsa order xavfsizlik uchun bloklanadi.

Logni ko'rish:

```cmd
type logs\goldai_ultra.log | findstr /I /C:"SAVDO" /C:"order" /C:"blok" /C:"signal"
```

## 5. AI sozlamalari

### Gemini

```env
AI_PROVIDER_ORDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
```

`gemini-2.0-flash` eski model bo'lib, 404 berishi mumkin. Dastur eski qiymatni avtomatik `gemini-2.5-flash` ga almashtiradi.

### OpenAI

```env
AI_PROVIDER_ORDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

HTTP 429 quota/rate-limit/billing muammosini bildiradi.

### AI'siz ishlash

```env
AI_PROVIDER_ORDER=
DEEPSEEK_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
```

Bu holda MT5 trading engine ishlaydi; faqat AI chat va AI review o'chadi.

### Lokal Ollama alternativasi

Ollama o'rnatilgandan keyin:

```cmd
ollama pull llama3.2
```

`.env`:

```env
AI_PROVIDER_ORDER=openai
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://127.0.0.1:11434/v1
OPENAI_MODEL=llama3.2
```

Bunda cloud API key kerak emas.

## 6. Xavfsizlik

- `.env` ni hech qachon GitHub, Telegram yoki screenshotga yubormang.
- Eski ochilgan keylarni revoke/rotate qiling.
- Avval Demo serverda sinang.
- `TRADING_MODE=live` faqat nima qilayotganingiz aniq bo'lganda yoqilsin.
- `START_GOLDAI.bat` Windows registry yoki auto-login sozlamalarini o'zgartirmaydi.
