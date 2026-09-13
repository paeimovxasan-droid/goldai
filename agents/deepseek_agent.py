"""GoldAI Ultra AI agent with DeepSeek, Gemini and OpenAI failover.

The class keeps its historic ``DeepSeekAgent`` name so Telegram and older
integrations continue to work.  It does not use provider SDKs: all three
providers are called through their documented HTTP APIs, which keeps the
Windows launcher small and avoids SDK version conflicts.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

try:
    import aiohttp
except ImportError:  # The launcher installs it; diagnostics should still import.
    aiohttp = None

from core.config import config
from core.logger import logger


class AIProviderError(RuntimeError):
    """An AI provider returned an unusable response."""

    def __init__(self, provider: str, status: int | None = None):
        self.provider = provider
        self.status = status
        super().__init__(f"{provider} request failed" + (f" (HTTP {status})" if status else ""))


class DeepSeekAgent:
    """Trading AI with automatic provider failover.

    Provider order is controlled with ``AI_PROVIDER_ORDER``.  A provider that
    returns an authentication, quota, rate-limit or server error is cooled
    down temporarily, so a depleted DeepSeek account cannot stall the bot on
    every scan.  The technical strategy and risk engine remain the execution
    authority; AI is an advisor and chat interface, never a profit guarantee.
    """

    def __init__(self):
        self.settings = config.ai
        self._disabled_until: dict[str, float] = {}
        self.active_provider = ""

        # Backwards-compatible attributes used by the old diagnostics.
        self.api_key = self.settings.api_key_for("deepseek")
        self.model = self.settings.deepseek_model
        self.base_url = self.settings.deepseek_base_url
        self.max_tokens = 1500
        self.temperature = 0.2

        providers = self.settings.enabled_providers()
        if providers:
            logger.info("🤖 AI providerlar: %s (failover yoqilgan)", ", ".join(providers))
        else:
            logger.warning("⚠️ AI provider API key topilmadi — AI chat/review o'chiq")

    @property
    def configured_providers(self) -> list[str]:
        return self.settings.enabled_providers()

    def provider_status(self) -> dict[str, Any]:
        """Safe status for health endpoints; never returns an API key."""
        now = time.monotonic()
        providers = []
        for name in ("deepseek", "gemini", "openai"):
            has_key = bool(self.settings.api_key_for(name))
            disabled_for = max(0, int(self._disabled_until.get(name, 0) - now))
            providers.append({
                "provider": name,
                "configured": has_key,
                "cooldown_seconds": disabled_for,
            })
        return {
            "active": self.active_provider or None,
            "order": self.configured_providers,
            "providers": providers,
        }

    def _available_providers(self) -> list[str]:
        now = time.monotonic()
        return [
            provider for provider in self.configured_providers
            if self._disabled_until.get(provider, 0) <= now
        ]

    def _mark_failed(self, provider: str, status: int | None = None) -> None:
        # Quota/auth errors are particularly noisy.  All provider failures get
        # a short cooldown; the next configured provider is tried immediately.
        cooldown = max(30, self.settings.cooldown_seconds)
        self._disabled_until[provider] = time.monotonic() + cooldown
        if status:
            logger.warning("AI %s ishlamadi (HTTP %s); %ss failover cooldown", provider, status, cooldown)
        else:
            logger.warning("AI %s ishlamadi; %ss failover cooldown", provider, cooldown)

    @staticmethod
    def _openai_messages_to_gemini(messages: list[dict]) -> list[dict]:
        """Translate chat messages to Gemini's contents format."""
        system = "\n\n".join(
            str(message.get("content", ""))
            for message in messages if message.get("role") == "system"
        )
        contents = []
        for message in messages:
            role = message.get("role", "user")
            if role == "system":
                continue
            gemini_role = "model" if role == "assistant" else "user"
            text = str(message.get("content", ""))
            if system and not contents:
                text = f"System instructions:\n{system}\n\n{text}"
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
        if not contents:
            contents = [{"role": "user", "parts": [{"text": system or "Analyze the market."}]}]
        return contents

    @staticmethod
    def _extract_openai_text(data: dict) -> str:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict)).strip()
        return str(content).strip()

    @staticmethod
    def _extract_gemini_text(data: dict) -> str:
        parts = []
        for candidate in data.get("candidates") or []:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                if isinstance(part, dict) and part.get("text"):
                    parts.append(str(part["text"]))
            if parts:
                break
        return "\n".join(parts).strip()

    async def _post_json(self, provider: str, messages: list[dict], max_tokens: int,
                         temperature: float, response_json: bool = False) -> str:
        if aiohttp is None:
            raise AIProviderError(provider)

        key = self.settings.api_key_for(provider)
        timeout = aiohttp.ClientTimeout(total=max(5, self.settings.request_timeout))
        headers = {"Content-Type": "application/json"}

        if provider in {"deepseek", "openai"}:
            if provider == "deepseek":
                base_url = self.settings.deepseek_base_url
                model = self.settings.deepseek_model
            else:
                base_url = self.settings.openai_base_url
                model = self.settings.openai_model
            url = f"{base_url}/chat/completions"
            headers["Authorization"] = f"Bearer {key}"
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_json and provider == "openai":
                # Supported by current OpenAI-compatible endpoints; DeepSeek
                # is intentionally left on plain text because compatibility
                # varies between its model versions.
                payload["response_format"] = {"type": "json_object"}
        else:
            model = self.settings.gemini_model
            # Google shut down Gemini 2.0 Flash; transparently migrate old
            # template values so an existing .env does not keep returning 404.
            if model in {"gemini-2.0-flash", "gemini-2.0-flash-001"}:
                model = "gemini-2.5-flash"
            url = (
                f"{self.settings.gemini_base_url}/models/{model}:generateContent"
                f"?key={key}"
            )
            payload = {
                "contents": self._openai_messages_to_gemini(messages),
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature,
                    **({"responseMimeType": "application/json"} if response_json else {}),
                },
            }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                    if response.status < 200 or response.status >= 300:
                        # Do not log response text: upstream errors can echo
                        # request details and must never expose credentials.
                        raise AIProviderError(provider, response.status)
                    data = await response.json(content_type=None)
        except AIProviderError:
            raise
        except Exception as exc:
            logger.debug("AI %s network error: %s", provider, type(exc).__name__)
            raise AIProviderError(provider) from exc

        text = self._extract_gemini_text(data) if provider == "gemini" else self._extract_openai_text(data)
        if not text:
            raise AIProviderError(provider)
        return text

    async def _complete(self, messages: list[dict], max_tokens: int = 300,
                        temperature: float = 0.2, response_json: bool = False) -> str:
        providers = self._available_providers()
        if not providers:
            return ""
        for provider in providers:
            try:
                result = await self._post_json(
                    provider, messages, max_tokens, temperature, response_json=response_json
                )
                self.active_provider = provider
                logger.debug("AI javob olindi: %s", provider)
                return result
            except AIProviderError as exc:
                self._mark_failed(provider, exc.status)
            except Exception as exc:
                logger.debug("AI %s unexpected error: %s", provider, type(exc).__name__)
                self._mark_failed(provider)
        logger.error("❌ Barcha sozlangan AI providerlar ishlamadi")
        return ""

    async def quick_review(self, scan_summary: dict, account: dict) -> str:
        """Bozor holatini tezkor AI tahlili."""
        balance = float(account.get("balance") or 0)
        equity = float(account.get("equity") or 0)
        prompt = (
            "You are a professional trading analyst. Briefly analyze:\n\n"
            f"Account: Balance=${balance:.2f}, Equity=${equity:.2f}\n"
            f"Scan: {scan_summary.get('scanned', 0)} markets scanned, "
            f"{scan_summary.get('signals', 0)} signals found\n"
            f"Best opportunity: {scan_summary.get('best_symbol', 'N/A')} "
            f"({float(scan_summary.get('best_confidence', 0) or 0):.1f}% confidence)\n"
            f"Market sentiment: {scan_summary.get('sentiment', 'N/A')}\n"
            f"Signals by type: {scan_summary.get('market_types', {})}\n\n"
            "Give a 2–3 sentence risk-aware trading recommendation. "
            "Should we trade now? What is the main risk?"
        )
        review = await self._complete(
            [{"role": "user", "content": prompt}], max_tokens=300, temperature=0.2
        )
        if review:
            logger.info("🤖 %s AI sharhi: %s...", self.active_provider, review[:120])
        return review

    async def trading_chat(self, user_message: str, context: dict | None = None) -> str:
        """Telegram /ask uchun trading mavzusidagi chat."""
        if not self.configured_providers:
            return "⚠️ AI API kalitlari sozlanmagan. .env faylida GEMINI_API_KEY, OPENAI_API_KEY yoki DEEPSEEK_API_KEY kiriting."

        ctx = ""
        if context:
            balance = float(context.get("balance") or 0)
            positions = context.get("positions", [])
            pos_text = "".join(
                f"\n  • {p.get('symbol')} {p.get('type')} @ {float(p.get('open_price', 0) or 0):.4f}"
                f" | P/L: {float(p.get('profit', 0) or 0):+.4f}"
                for p in positions[:3]
            )
            ctx = f"\nHozirgi holat:\n  Balans: ${balance:.2f}\n  Ochiq pozitsiyalar: {len(positions)}{pos_text}\n"

        system_prompt = (
            "You are GoldAI Ultra's AI trading assistant. You ONLY answer questions about "
            "crypto, forex, gold, oil, technical analysis, risk management, position sizing, "
            "stop loss, portfolio management and current positions.\n"
            "For non-trading questions respond only: Men faqat trading savollariga javob beraman.\n"
            "Keep answers concise (3-5 sentences), use the same language as the user, "
            "mention risk management, and never guarantee profit."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{ctx}\nSavol: {user_message}"},
        ]
        answer = await self._complete(messages, max_tokens=400, temperature=0.3)
        if not answer:
            return "⚠️ AI providerlar javob bermadi. Kalit, balans/limit va internet ulanishini tekshiring."
        return f"🤖 <b>GoldAI AI ({self.active_provider}):</b>\n\n{answer}"

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        cleaned = text.strip().replace("```json", "").replace("```", "").strip()
        try:
            value = json.loads(cleaned)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                value = json.loads(match.group())
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None

    async def analyze_signal(self, signal_data: dict) -> dict:
        """Ask AI for an optional signal opinion.

        Missing AI must not silently turn into a trade approval.  The current
        orchestrator does not use this as a hard gate; if an integration does,
        it gets an explicit ``ai_unavailable`` result instead.
        """
        prompt = (
            f"Signal: {signal_data.get('signal')} {signal_data.get('symbol')}\n"
            f"Confidence: {signal_data.get('confidence')}%\n"
            f"Entry: {signal_data.get('entry')}, SL: {signal_data.get('stop_loss')}, "
            f"TP: {signal_data.get('take_profit')}\n"
            f"R:R: {signal_data.get('rr_ratio')}\n"
            f"Reason: {signal_data.get('reason')}\n\n"
            'Should this trade be executed? Reply only JSON: '
            '{"approved": true/false, "reason": "brief reason"}'
        )
        content = await self._complete(
            [{"role": "user", "content": prompt}],
            max_tokens=180, temperature=0.1, response_json=True
        )
        result = self._parse_json(content) if content else None
        if result and isinstance(result.get("approved"), bool):
            return {"approved": result["approved"], "reason": str(result.get("reason", ""))[:300]}
        return {"approved": None, "ai_unavailable": True, "reason": "AI javob bermadi"}
