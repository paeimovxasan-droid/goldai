
"""GoldAI Ultra — DeepSeek AI Agent"""
import aiohttp
from core.config import config
from core.logger import logger


class DeepSeekAgent:
    """DeepSeek API orqali bozorni AI tahlil qilish"""

    def __init__(self):
        self.api_key = config.deepseek.api_key
        self.model = config.deepseek.model
        self.base_url = config.deepseek.base_url
        self.max_tokens = config.deepseek.max_tokens
        self.temperature = config.deepseek.temperature

    async def quick_review(self, scan_summary: dict, account: dict) -> str:
        """Bozor holatini tezkor AI tahlili"""
        if not self.api_key:
            logger.debug("DeepSeek API key yo'q — skip")
            return ""

        balance = account.get("balance", 0)
        equity = account.get("equity", 0)
        best_sym = scan_summary.get("best_symbol", "N/A")
        best_conf = scan_summary.get("best_confidence", 0)
        sentiment = scan_summary.get("sentiment", "N/A")
        scanned = scan_summary.get("scanned", 0)
        signals = scan_summary.get("signals", 0)
        by_type = scan_summary.get("market_types", {})

        prompt = (
            f"You are a professional trading analyst. Briefly analyze:\n\n"
            f"Account: Balance=${balance:.2f}, Equity=${equity:.2f}\n"
            f"Scan: {scanned} markets scanned, {signals} signals found\n"
            f"Best opportunity: {best_sym} ({best_conf:.1f}% confidence)\n"
            f"Market sentiment: {sentiment}\n"
            f"Signals by type: {by_type}\n\n"
            f"Give a 2–3 sentence risk-aware trading recommendation. "
            f"Should we trade now? What is the main risk?"
        )

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": self.temperature
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        review = data["choices"][0]["message"]["content"].strip()
                        logger.info(f"🤖 DeepSeek AI sharhi: {review[:120]}...")
                        return review
                    else:
                        body = await resp.text()
                        logger.debug(f"DeepSeek HTTP {resp.status}: {body[:100]}")
                        return ""

        except Exception as e:
            logger.debug(f"DeepSeek xatosi: {e}")
            return ""

    async def trading_chat(self, user_message: str, context: dict = None) -> str:
        """
        Foydalanuvchi bilan suhbat — faqat trading mavzulari.
        Telegram /ask buyrug'i yoki oddiy xabar orqali chaqiriladi.
        """
        if not self.api_key:
            return "⚠️ DeepSeek API kaliti yo'q — AI chat ishlamaydi."

        ctx = ""
        if context:
            balance = context.get("balance", 0)
            positions = context.get("positions", [])
            pos_text = ""
            for p in positions[:3]:
                pos_text += (
                    f"\n  • {p.get('symbol')} {p.get('type')} "
                    f"@ {p.get('open_price', 0):.4f} | "
                    f"P/L: {p.get('profit', 0):+.4f}"
                )
            ctx = (
                f"\nHozirgi holat:\n"
                f"  Balans: ${balance:.2f} USDT\n"
                f"  Ochiq pozitsiyalar: {len(positions)}{pos_text}\n"
            )

        system_prompt = (
            "You are GoldAI Ultra's AI trading assistant specialized in crypto futures trading.\n"
            "You ONLY answer questions about:\n"
            "- Cryptocurrency trading, technical analysis, price action\n"
            "- Risk management, position sizing, stop loss placement\n"
            "- Market trends, support/resistance, trading strategies\n"
            "- Portfolio management and current positions\n"
            "- Forex and commodity markets (gold, oil)\n\n"
            "RULES:\n"
            "1. For non-trading questions, respond ONLY: \"Men faqat trading savollariga javob beraman.\"\n"
            "2. Keep answers concise (3-5 sentences max)\n"
            "3. Answer in the SAME LANGUAGE as the user's question (Uzbek/Russian/English)\n"
            "4. Always mention risk management when suggesting trades\n"
            "5. Never guarantee profits — always say 'mumkin' or 'probability'\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{ctx}\nSavol: {user_message}"}
        ]

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 400,
                "temperature": 0.3
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers, json=payload,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        answer = data["choices"][0]["message"]["content"].strip()
                        return f"🤖 <b>GoldAI AI:</b>\n\n{answer}"
                    else:
                        return "⚠️ AI javob berolmadi, qayta urining."
        except Exception as e:
            logger.debug(f"DeepSeek chat xato: {e}")
            return "⚠️ AI bilan bog'lanishda xato."

    async def analyze_signal(self, signal_data: dict) -> dict:
        """Bitta signal uchun chuqur tahlil"""
        if not self.api_key:
            return {"approved": True, "reason": "AI tahlilsiz — approve"}

        prompt = (
            f"Signal: {signal_data.get('signal')} {signal_data.get('symbol')}\n"
            f"Confidence: {signal_data.get('confidence')}%\n"
            f"Entry: {signal_data.get('entry')}, SL: {signal_data.get('stop_loss')}, "
            f"TP: {signal_data.get('take_profit')}\n"
            f"R:R: {signal_data.get('rr_ratio')}\n"
            f"Reason: {signal_data.get('reason')}\n\n"
            f"Should this trade be executed? Reply JSON: "
            f'{"approved": true/false, "reason": "brief reason"}'
        )

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.1
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"].strip()
                        import json, re
                        match = re.search(r'\{.*\}', content, re.DOTALL)
                        if match:
                            return json.loads(match.group())
                    return {"approved": True, "reason": "AI javob berolmadi"}

        except Exception as e:
            logger.debug(f"DeepSeek signal tahlil xatosi: {e}")
            return {"approved": True, "reason": str(e)}
