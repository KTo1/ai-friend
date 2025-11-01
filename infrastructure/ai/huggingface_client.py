import os
import re
from openai import AsyncOpenAI  # ← ВАЖНО: AsyncOpenAI вместо OpenAI
from typing import List, Dict
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.ai.base_ai_client import BaseAIClient


class HuggingFaceClient(BaseAIClient, AIClientInterface):
    def __init__(self):
        self.api_key = os.getenv("HF_API_KEY")
        self.model = os.getenv("HF_MODEL", "microsoft/DialoGPT-medium")
        self.logger = StructuredLogger("huggingface_client")

        # Асинхронный OpenAI клиент - КОРРЕКТНО!
        self.client = AsyncOpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=self.api_key or "hf_placeholder"
        )

    @trace_span("huggingface.generate_response", attributes={"component": "ai"})
    async def generate_response(self, messages: List[Dict], max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Сгенерировать ответ через Hugging Face Router API (асинхронно)"""

        try:
            import time
            start_time = time.time()

            # АСИНХРОННЫЙ вызов - КОРРЕКТНО!
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )

            duration = time.time() - start_time
            metrics_collector.record_processing_time("huggingface_api_call", duration)
            metrics_collector.record_openai_request("success")

            raw_response = completion.choices[0].message.content.strip()
            cleaned_response = self._clean_response(raw_response)

            self.logger.info(
                "Hugging Face response generated",
                extra={
                    'operation': 'generate_response',
                    'model': self.model,
                    'response_length': len(cleaned_response),
                    'duration_ms': duration * 1000
                }
            )

            return cleaned_response

        except Exception as e:
            metrics_collector.record_openai_request("error")
            self.logger.error(
                f"Hugging Face API error: {e}",
                extra={'operation': 'generate_response', 'model': self.model}
            )
            raise

    async def close(self):
        """Закрыть клиент"""
        await self.client.close()

    def _clean_response(self, response: str) -> str:
        """Очистить ответ от тегов reasoning"""
        # Удаляем блоки <think>...</think>
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        response = re.sub(r'<reasoning>.*?</reasoning>', '', response, flags=re.DOTALL)
        response = re.sub(r'<reason>.*?</reason>', '', response, flags=re.DOTALL)
        response = re.sub(r'<thought>.*?</thought>', '', response, flags=re.DOTALL)

        # Удаляем строки с reasoning
        lines = response.split('\n')
        cleaned_lines = []
        skip_next = False

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if (line.lower().startswith('reasoning:') or
                    line.lower().startswith('thinking:') or
                    line.lower().startswith('thoughts:') or
                    line.lower().startswith('analysis:')):
                skip_next = True
                continue

            if skip_next:
                if line and not line[0].isalnum():
                    continue
                skip_next = False

            cleaned_lines.append(line)

        cleaned_response = '\n'.join(cleaned_lines)

        if not cleaned_response.strip():
            return "Извини, я не совсем поняла твой вопрос. Можешь переформулировать? 😊"

        return cleaned_response.strip()