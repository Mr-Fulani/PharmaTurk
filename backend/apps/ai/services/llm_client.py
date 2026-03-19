import os
import json
import time
from typing import List, Dict, Optional, Union
from openai import OpenAI, AsyncOpenAI
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Унифицированный клиент для LLM операций.
    Поддержка OpenAI и локальных моделей (через настройку).
    """
    def __init__(self, async_mode: bool = False):
        self.model = settings.AI_CONFIG.get('MODEL', 'gpt-4o-mini')
        self.vision_model = settings.AI_CONFIG.get('VISION_MODEL', 'gpt-4o-mini')
        self.embedding_model = settings.AI_CONFIG.get('EMBEDDING_MODEL', 'text-embedding-3-small')
        
        client_class = AsyncOpenAI if async_mode else OpenAI
        self.client = client_class(api_key=settings.OPENAI_API_KEY)
        
        # Pricing для подсчета стоимости (обновлять по мере изменений OpenAI)
        self.pricing = {
            'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006},  # per 1K tokens
            'gpt-4o': {'input': 0.005, 'output': 0.015},
            'text-embedding-3-small': {'input': 0.00002, 'output': 0},
        }

    def get_embedding(self, text: str) -> List[float]:
        """Получить векторное представление текста."""
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
        max_retries: int = 6,
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
                'raw_response': dict
            }
        """
        start_time = time.time()
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        attempt = 0
        backoff = initial_backoff_ms / 1000.0
        response = None
        content = None
        while attempt <= max_retries:
            try:
                if json_mode:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"}
                    )
                    raw_text = response.choices[0].message.content or ""
                    content = self._parse_json_response(raw_text)
                else:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    content = response.choices[0].message.content
                break
            except Exception as e:
                msg = str(e).lower()
                is_rate_limit = "rate limit" in msg or "too many requests" in msg or "429" in msg
                is_server_busy = "try again" in msg or "overloaded" in msg
                logger.warning(f"LLM generation retry {attempt + 1}/{max_retries}: {e}")
                if attempt >= max_retries or not (is_rate_limit or is_server_busy):
                    logger.error(f"LLM generation error: {e}")
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
                attempt += 1

        processing_time = int((time.time() - start_time) * 1000)
        tokens = {
            'prompt': response.usage.prompt_tokens,
            'completion': response.usage.completion_tokens,
            'total': response.usage.total_tokens
        }
        
        model_pricing = self.pricing.get(self.model, self.pricing.get('gpt-4o-mini'))
        cost = (tokens['prompt'] * model_pricing['input'] + 
               tokens['completion'] * model_pricing['output']) / 1000
        
        return {
            'content': content,
            'tokens': tokens,
            'cost_usd': round(cost, 6),
            'processing_time_ms': processing_time,
            'raw_response': response.model_dump()
        }
        

    def analyze_images(
        self,
        images: List[Dict],  # Из R2MediaProcessor.get_product_images_batch
        prompt: str,
        json_mode: bool = True,
        max_retries: int = 6,
        initial_backoff_ms: int = 250
    ) -> Dict:
        """
        Анализ изображений через Vision API.
        
        Args:
            images: список обработанных изображений с base64
            prompt: текстовый промпт для анализа
        """
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
                is_rate_limit = "rate limit" in msg or "too many requests" in msg or "429" in msg
                is_server_busy = "try again" in msg or "overloaded" in msg
                logger.warning(f"Vision API retry {attempt + 1}/{max_retries}: {e}")
                if attempt >= max_retries or not (is_rate_limit or is_server_busy):
                    logger.error(f"Vision API error: {e}")
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
                attempt += 1

        processing_time = int((time.time() - start_time) * 1000)
        tokens = {
            'prompt': response.usage.prompt_tokens,
            'completion': response.usage.completion_tokens,
            'total': response.usage.total_tokens
        }
        
        model_pricing = self.pricing.get(self.vision_model, self.pricing.get('gpt-4o-mini'))
        cost = (tokens['prompt'] * model_pricing['input'] + 
               tokens['completion'] * model_pricing['output']) / 1000
        
        return {
            'content': result_content,
            'tokens': tokens,
            'cost_usd': round(cost, 6),
            'processing_time_ms': processing_time,
            'analyzed_images_count': len(images),
            'raw_response': response.model_dump()
        }
