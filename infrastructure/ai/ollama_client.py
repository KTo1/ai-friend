import os
import aiohttp
import asyncio
from typing import List, Dict
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.ai.base_ai_client import BaseAIClient


class OllamaClient(BaseAIClient, AIClientInterface):
    def __init__(self):
        super().__init__("ollama")
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "llama2:7b")
        self.logger = StructuredLogger("ollama_client")
        self._session = None
        self._session_lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        """Получить или создать aiohttp сессию (потокобезопасно)"""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                timeout = aiohttp.ClientTimeout(total=120)
                self._session = aiohttp.ClientSession(timeout=timeout)
            return self._session

    @trace_span("ollama.generate_response", attributes={"component": "ai"})
    async def generate_response(self, messages: List[Dict], max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Сгенерировать ответ с помощью Ollama (асинхронно)"""

        session = await self.get_session()
        prompt = self._format_messages(messages)

        try:
            import time
            start_time = time.time()

            async with session.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "num_predict": max_tokens,
                            "temperature": temperature
                        }
                    }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                result = await response.json()

            duration = time.time() - start_time
            metrics_collector.record_processing_time("ollama_api_call", duration)
            metrics_collector.record_openai_request("success")

            self.logger.info(
                "Ollama response generated",
                extra={
                    'operation': 'generate_response',
                    'model': self.model,
                    'response_length': len(result.get('response', '')),
                    'duration_ms': duration * 1000
                }
            )

            return result['response'].strip()

        except Exception as e:
            metrics_collector.record_openai_request("error")
            self.logger.error(
                f"Ollama API error: {e}",
                extra={'operation': 'generate_response', 'model': self.model}
            )
            raise

    async def close(self):
        """Закрыть HTTP сессию"""
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    def _format_messages(self, messages: List[Dict]) -> str:
        """Форматирование сообщений для Ollama"""
        formatted = []
        for msg in messages:
            if msg['role'] == 'system':
                formatted.append(f"Инструкция: {msg['content']}")
            elif msg['role'] == 'user':
                formatted.append(f"Пользователь: {msg['content']}")
            elif msg['role'] == 'assistant':
                formatted.append(f"Ассистент: {msg['content']}")

        # Добавляем промпт для ответа
        return "\n\n".join(formatted) + "\n\nАссистент:"