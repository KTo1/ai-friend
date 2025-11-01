import os
from openai import AsyncOpenAI  # ← AsyncOpenAI вместо OpenAI
from typing import List, Dict
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.ai.base_ai_client import BaseAIClient


class OpenAIClient(BaseAIClient, AIClientInterface):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # ← AsyncOpenAI
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.logger = StructuredLogger("openai_client")

    @trace_span("openai.generate_response", attributes={"component": "ai"})
    async def generate_response(self, messages: List[Dict], max_tokens: int = None, temperature: float = None) -> str:
        """Сгенерировать ответ с помощью OpenAI (асинхронно)"""
        max_tokens = max_tokens or int(os.getenv("OPENAI_MAX_TOKENS", "500"))
        temperature = temperature or float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

        try:
            import time
            start_time = time.time()

            # АСИНХРОННЫЙ вызов
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            duration = time.time() - start_time
            metrics_collector.record_processing_time("openai_api_call", duration)
            metrics_collector.record_openai_request("success")

            self.logger.info(
                "OpenAI response generated",
                extra={
                    'operation': 'generate_response',
                    'model': self.model,
                    'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                    'completion_tokens': response.usage.completion_tokens if response.usage else 0,
                    'duration_ms': duration * 1000
                }
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            metrics_collector.record_openai_request("error")
            self.logger.error(
                f"OpenAI API error: {e}",
                extra={'operation': 'generate_response', 'model': self.model}
            )
            raise

    async def close(self):
        """Закрыть клиент"""
        await self.client.close()