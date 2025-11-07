import os
import asyncio
import aiohttp
from typing import List, Dict
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.ai.base_ai_client import BaseAIClient


class DeepSeekClient(BaseAIClient, AIClientInterface):
    def __init__(self):
        super().__init__("deepseek")
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.logger = StructuredLogger("deepseek_client")
        self._session = None
        self._session_lock = asyncio.Lock()

        if not self.api_key:
            self.logger.warning("DEEPSEEK_API_KEY not set - DeepSeek client will not work")

    async def get_session(self) -> aiohttp.ClientSession:
        """Получить или создать aiohttp сессию (потокобезопасно)"""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                timeout = aiohttp.ClientTimeout(total=60)
                self._session = aiohttp.ClientSession(timeout=timeout)
            return self._session

    @trace_span("deepseek.generate_response", attributes={"component": "ai"})
    async def generate_response(self, messages: List[Dict], max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Сгенерировать ответ с помощью DeepSeek API"""

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")

        session = await self.get_session()

        try:
            import time
            start_time = time.time()

            # Подготавливаем сообщения для DeepSeek API
            api_messages = self._prepare_messages(messages)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "messages": api_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }

            async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
            ) as response:

                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"DeepSeek API error {response.status}: {error_text}")
                    raise Exception(f"DeepSeek API error {response.status}: {error_text}")

                result = await response.json()

            duration = time.time() - start_time
            metrics_collector.record_processing_time("deepseek_api_call", duration)
            metrics_collector.record_openai_request("success")

            bot_response = result['choices'][0]['message']['content'].strip()

            self.logger.info(
                "DeepSeek response generated",
                extra={
                    'operation': 'generate_response',
                    'model': self.model,
                    'response_length': len(bot_response),
                    'duration_ms': duration * 1000,
                    'tokens_used': result.get('usage', {}).get('total_tokens', 0)
                }
            )

            return bot_response

        except asyncio.TimeoutError:
            self.logger.error("DeepSeek API timeout")
            raise Exception("DeepSeek API timeout")
        except Exception as e:
            metrics_collector.record_openai_request("error")
            self.logger.error(
                f"DeepSeek API error: {e}",
                extra={'operation': 'generate_response', 'model': self.model}
            )
            raise

    async def close(self):
        """Закрыть HTTP сессию"""
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    def _prepare_messages(self, messages: List[Dict]) -> List[Dict]:
        """Подготовка сообщений для DeepSeek API"""
        prepared_messages = []

        for msg in messages:
            # DeepSeek API использует те же роли что и OpenAI
            role = msg['role']
            content = msg['content']

            # Обрабатываем системные сообщения
            if role == 'system':
                # DeepSeek хорошо работает с системными сообщениями как user
                prepared_messages.append({"role": "user", "content": f"Системная инструкция: {content}"})
            else:
                prepared_messages.append({"role": role, "content": content})

        return prepared_messages