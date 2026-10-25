import os
import json
import time
import requests
import random
from typing import List, Dict, Optional, Union
from openai import OpenAI, AsyncOpenAI
from django.conf import settings
from apps.ai.services.claude_client import ClaudeClient, ClaudeUnavailable, claude_usage
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class OpenAIDisabled(RuntimeError):
    """AI_OPENAI_ENABLED=false: запрос к OpenAI не отправляется."""


def _ensure_openai_enabled(purpose: str) -> None:
    if not getattr(settings, "AI_OPENAI_ENABLED", True):
        raise OpenAIDisabled(f"OpenAI выключен (AI_OPENAI_ENABLED=false): {purpose} не выполняется")


class LLMClient:
    """
    Унифицированный клиент для LLM операций.

    Текст генерирует Claude, если задан ANTHROPIC_API_KEY (generate_content),
    при его сбое — OpenAI. Картинки, эмбеддинги и Batch API — OpenAI.
    """
    def __init__(self, async_mode: bool = False):
        self.openai_model = settings.AI_CONFIG.get('MODEL', 'gpt-4o-mini')
        self.claude = ClaudeClient() if getattr(settings, "ANTHROPIC_API_KEY", "") and not async_mode else None
        # Модель, которая отвечает по умолчанию; фактическая — в результате generate_content["model"].
        self.model = self.claude.model if self.claude else self.openai_model
        self.vision_model = settings.AI_CONFIG.get('VISION_MODEL', 'gpt-4o-mini')
        self.embedding_model = settings.AI_CONFIG.get('EMBEDDING_MODEL', 'text-embedding-3-small')
        
        client_class = AsyncOpenAI if async_mode else OpenAI
        self.client = client_class(api_key=settings.OPENAI_API_KEY)
        
        # USD за 1M токенов из settings.AI_CONFIG["PRICING"] (env AI_PRICING_JSON).
        self.pricing = settings.AI_CONFIG.get('PRICING') or {}

    def _usage_and_cost(self, model: str, usage) -> tuple[Dict, float]:
        """Токены и стоимость вызова с учётом кэшированной части промпта."""
        details = getattr(usage, "prompt_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        tokens = {
            'prompt': usage.prompt_tokens,
            'completion': usage.completion_tokens,
            'total': usage.total_tokens,
            'cached': cached,
        }
        price = self.pricing.get(model)
        if price is None:
            logger.warning("No AI pricing for model %s; cost_usd recorded as 0", model)
            return tokens, 0.0
        cost = (
            (tokens['prompt'] - cached) * price.get('input', 0)
            + cached * price.get('cached_input', price.get('input', 0))
            + tokens['completion'] * price.get('output', 0)
        ) / 1_000_000
        return tokens, cost

    def _notify_admin_quota_error(self):
        """Оповещение админа в Telegram об исчерпании лимита (с антиспам кэшем на 1 час)."""
        bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
        
        if not bot_token or not chat_id:
            return
            
        cache_key = "openai_quota_alert_sent"
        if not cache.get(cache_key):
            text = (
                "⚠️ *Внимание!*\n\n"
                "На аккаунте OpenAI закончились средства (Insufficient Quota) или превышен лимит.\n"
                "Генерация контента (AI) временно остановлена.\n\n"
                "Пожалуйста, пополните баланс на platform.openai.com."
            )
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=5
                )
                cache.set(cache_key, True, 3600)  # Раз в час
            except Exception:
                # The requests exception can contain Telegram's tokenized URL.
                logger.error("Failed to send Telegram quota alert")

    def get_embedding(self, text: str) -> List[float]:
        """Получить векторное представление текста."""
        _ensure_openai_enabled("эмбеддинг")
        text = text[:8000]  # Лимит токенов
        
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        
        return response.data[0].embedding

    def _parse_json_response(self, raw: str):
        """Парсинг JSON из ответа; поддерживает обёртку в ```json ... ```."""
        if not raw or not raw.strip():
            return {}
        text = raw.strip()
        if text.startswith("```"):
            idx = text.find("\n")
            first_line = text[: idx + 1] if idx >= 0 else text
            if "json" in first_line.lower():
                text = text[len(first_line) :].lstrip()
            else:
                text = text[3:].lstrip()
            if text.endswith("```"):
                text = text[:-3].rstrip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("LLM JSON parse error: %s, snippet: %s", e, raw[:400])
            return {}

    def generate_content(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        max_retries: int = 10,
        initial_backoff_ms: int = 250
    ) -> Dict:
        """
        Генерация текста с полным логированием.
        
        Returns:
            {
                'content': str или dict (если json_mode),
                'tokens': {'prompt': int, 'completion': int, 'total': int},
                'cost_usd': float,
                'processing_time_ms': int,
                'raw_response': dict,
                'finish_reason': str,
                'truncated': bool,   # ответ обрезан по max_tokens
                'json_error': bool,  # json_mode, но ответ не разобрался как JSON
                'model': str,        # модель, которая ответила (Claude или запасной OpenAI)
            }
        """
        start_time = time.time()
        if self.claude:
            try:
                return self._generate_with_claude(system_prompt, user_prompt, json_mode, max_tokens, start_time)
            except ClaudeUnavailable:
                if not getattr(settings, "AI_OPENAI_ENABLED", True):
                    raise
        _ensure_openai_enabled("генерация текста")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        attempt = 0
        backoff = initial_backoff_ms / 1000.0
        response = None
        content = None
        json_error = False
        while attempt <= max_retries:
            try:
                if json_mode:
                    response = self.client.chat.completions.create(
                        model=self.openai_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"}
                    )
                    raw_text = response.choices[0].message.content or ""
                    content = self._parse_json_response(raw_text)
                    json_error = not content and bool(raw_text.strip())
                else:
                    response = self.client.chat.completions.create(
                        model=self.openai_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    content = response.choices[0].message.content
                break
            except Exception as e:
                msg = str(e).lower()
                is_quota_error = "insufficient_quota" in msg
                is_rate_limit = "rate limit" in msg or "too many requests" in msg or "429" in msg
                is_server_busy = "try again" in msg or "overloaded" in msg
                
                # Не пытаемся повторить запрос, если кончились деньги на балансе
                if is_quota_error:
                    logger.error(f"OpenAI Insufficient Quota: {e}")
                    self._notify_admin_quota_error()
                    raise
                    
                logger.warning(f"LLM generation retry {attempt + 1}/{max_retries}: {e}")
                if attempt >= max_retries or not (is_rate_limit or is_server_busy):
                    logger.error(f"LLM generation error: {e}")
                    raise
                
                # При rate limit увеличиваем паузу и добавляем рандомный jitter (анти-спам)
                sleep_time = backoff + (random.uniform(0, 1))
                time.sleep(sleep_time)
                
                # Экспоненциальное увеличение задержки
                backoff = min(backoff * 2, 15.0)
                attempt += 1

        processing_time = int((time.time() - start_time) * 1000)
        tokens, cost = self._usage_and_cost(self.openai_model, response.usage)

        finish_reason = getattr(response.choices[0], "finish_reason", None) or ""
        if finish_reason == "length":
            logger.warning("LLM response truncated by max_tokens=%s", max_tokens)
        return {
            'content': content,
            'tokens': tokens,
            'cost_usd': round(cost, 6),
            'processing_time_ms': processing_time,
            'raw_response': response.model_dump(),
            'finish_reason': finish_reason,
            'truncated': finish_reason == "length",
            'json_error': json_error,
            'model': self.openai_model,
        }

    def _generate_with_claude(self, system_prompt, user_prompt, json_mode, max_tokens, start_time) -> Dict:
        """Ответ Claude в формате generate_content; непригодный → ClaudeUnavailable (уйдёт в OpenAI)."""
        raw_text, response = self.claude.create(
            system_prompt, user_prompt, json_mode=json_mode, max_tokens=max_tokens
        )
        truncated = response.stop_reason == "max_tokens"
        content = self._parse_json_response(raw_text) if json_mode else raw_text
        if json_mode and not content:
            logger.warning("Claude: ответ не разобрался как JSON (stop_reason=%s) — запрос уходит в OpenAI", response.stop_reason)
            raise ClaudeUnavailable("json")
        prompt_tokens, cached, completion_tokens = claude_usage(response.usage)
        tokens = {
            'prompt': prompt_tokens,
            'completion': completion_tokens,
            'total': prompt_tokens + completion_tokens,
            'cached': cached,
        }
        price = self.pricing.get(self.claude.model)
        cost = 0.0
        if price is None:
            logger.warning("No AI pricing for model %s; cost_usd recorded as 0", self.claude.model)
        else:
            cost = (
                (prompt_tokens - cached) * price.get('input', 0)
                + cached * price.get('cached_input', price.get('input', 0))
                + completion_tokens * price.get('output', 0)
            ) / 1_000_000
        return {
            'content': content,
            'tokens': tokens,
            'cost_usd': round(cost, 6),
            'processing_time_ms': int((time.time() - start_time) * 1000),
            'raw_response': response.to_dict(),
            # «length» — как у OpenAI: по нему пайплайн узнаёт обрезанный ответ.
            'finish_reason': "length" if truncated else (response.stop_reason or ""),
            'truncated': truncated,
            'json_error': False,
            'model': self.claude.model,
        }


    def analyze_images(
        self,
        images: List[Dict],  # Из R2MediaProcessor.get_product_images_batch
        prompt: str,
        json_mode: bool = True,
        max_retries: int = 10,
        initial_backoff_ms: int = 250
    ) -> Dict:
        """
        Анализ изображений через Vision API.
        
        Args:
            images: список обработанных изображений с base64
            prompt: текстовый промпт для анализа
        """
        _ensure_openai_enabled("анализ изображений")
        start_time = time.time()
        
        # Формируем content для API
        content = [{"type": "text", "text": prompt}]
        
        for img in images:
            if img.get('base64'):
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": img['base64'],
                        "detail": "auto"  # или "low" для экономии
                    }
                })
        
        messages = [
            {
                "role": "user",
                "content": content
            }
        ]
        
        attempt = 0
        backoff = initial_backoff_ms / 1000.0
        response = None
        result_content = None
        while attempt <= max_retries:
            try:
                if json_mode:
                    response = self.client.chat.completions.create(
                        model=self.vision_model,
                        messages=messages,
                        max_tokens=1000,
                        response_format={"type": "json_object"}
                    )
                    result_content = json.loads(response.choices[0].message.content)
                else:
                    response = self.client.chat.completions.create(
                        model=self.vision_model,
                        messages=messages,
                        max_tokens=1000
                    )
                    result_content = response.choices[0].message.content
                break
            except Exception as e:
                msg = str(e).lower()
                is_quota_error = "insufficient_quota" in msg
                is_rate_limit = "rate limit" in msg or "too many requests" in msg or "429" in msg
                is_server_busy = "try again" in msg or "overloaded" in msg
                
                # Не пытаемся повторить запрос, если кончились деньги на балансе
                if is_quota_error:
                    logger.error(f"OpenAI Insufficient Quota: {e}")
                    self._notify_admin_quota_error()
                    raise
                    
                logger.warning(f"Vision API retry {attempt + 1}/{max_retries}: {e}")
                if attempt >= max_retries or not (is_rate_limit or is_server_busy):
                    logger.error(f"Vision API error: {e}")
                    raise
                
                # При rate limit увеличиваем паузу и добавляем рандомный jitter
                sleep_time = backoff + (random.uniform(0, 1))
                time.sleep(sleep_time)
                
                backoff = min(backoff * 2, 15.0)
                attempt += 1

        processing_time = int((time.time() - start_time) * 1000)
        tokens, cost = self._usage_and_cost(self.vision_model, response.usage)

        return {
            'content': result_content,
            'tokens': tokens,
            'cost_usd': round(cost, 6),
            'processing_time_ms': processing_time,
            'analyzed_images_count': len(images),
            'raw_response': response.model_dump()
        }
