from abc import ABC, abstractmethod
from typing import List, Dict
import asyncio
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.logging import StructuredLogger


class BaseAIClient(ABC):
    def __init__(self, provider_name: str):
        self.provider_name = provider_name
        self.logger = StructuredLogger(f"{provider_name}_client")

    async def generate_response_safe(self, messages: List[Dict], max_tokens: int = 500,
                                     temperature: float = 0.7) -> str:
        """Безопасная генерация ответа с ретраями и fallback"""

        max_retries = 2
        fallback_responses = [
            "Привет! Как твои дела? 😊",
            "Извини, я немного занята. Расскажи, что у тебя нового? 🌟",
            "Привет! Что интересного произошло? 🎯",
            "Здравствуй! Как твое настроение сегодня? 💫"
        ]

        import random

        for attempt in range(max_retries):
            try:
                return await self.generate_response(messages, max_tokens, temperature)

            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    self.logger.error(f"All attempts failed, using fallback: {e}")
                    # Возвращаем случайный fallback ответ
                    return random.choice(fallback_responses)

    @abstractmethod
    async def generate_response(self, messages: List[Dict], max_tokens: int = None, temperature: float = None) -> str:
        pass

    async def close(self):
        pass