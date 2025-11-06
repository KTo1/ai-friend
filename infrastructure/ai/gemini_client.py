import os
import asyncio
import google.generativeai as genai
from typing import List, Dict
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.ai.base_ai_client import BaseAIClient


class GeminiClient(BaseAIClient, AIClientInterface):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        # Конфигурируем Gemini с таймаутами
        genai.configure(
            api_key=api_key,
            # transport='rest',  # Можно попробовать другой транспорт
        )

        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.logger = StructuredLogger("gemini_client")

        # Получаем список доступных моделей
        available_models = self._get_available_models()
        self.logger.info(f"Available Gemini models: {list(available_models.keys())}")

        try:
            self.model = genai.GenerativeModel(self.model_name)
            self.logger.info(f"Gemini model initialized: {self.model_name}")
        except Exception as e:
            self.logger.error(f"Failed to initialize model: {e}")
            raise

    def _get_available_models(self) -> Dict:
        """Получить список доступных моделей"""
        try:
            models = {}
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    models[m.name] = m
            return models
        except Exception as e:
            self.logger.error(f"Error listing models: {e}")
            return {}

    @trace_span("gemini.generate_response", attributes={"component": "ai"})
    async def generate_response(self, messages: List[Dict], max_tokens: int = 500, temperature: float = 0.7) -> str:
        """Сгенерировать ответ с помощью Google Gemini"""

        max_retries = 3
        retry_delay = 1  # секунды

        for attempt in range(max_retries):
            try:
                self.logger.info(f"🔄 Attempt {attempt + 1}/{max_retries} for Gemini API")

                # Конвертируем сообщения в формат Gemini
                prompt = self._convert_to_gemini_format(messages)

                import time
                start_time = time.time()

                # Асинхронный вызов с таймаутом
                response = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.model.generate_content(
                            prompt,
                            generation_config=genai.types.GenerationConfig(
                                max_output_tokens=max_tokens or 500,
                                temperature=temperature or 0.7,
                                top_p=0.8,
                                top_k=40
                            )
                        )
                    ),
                    timeout=30.0  # 30 секунд таймаут
                )

                duration = time.time() - start_time

                # Проверяем ответ
                if not response:
                    raise ValueError("No response from Gemini")

                if not hasattr(response, 'text') or not response.text:
                    raise ValueError("Empty text in Gemini response")

                bot_response = response.text.strip()

                metrics_collector.record_processing_time("gemini_api_call", duration)
                metrics_collector.record_openai_request("success")

                self.logger.info(
                    "Gemini response generated",
                    extra={
                        'operation': 'generate_response',
                        'model': self.model_name,
                        'response_length': len(bot_response),
                        'duration_ms': duration * 1000,
                        'attempt': attempt + 1
                    }
                )

                return bot_response

            except asyncio.TimeoutError:
                self.logger.warning(f"⏰ Gemini API timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Увеличиваем задержку
                    continue
                else:
                    raise Exception("Gemini API timeout after all retries")

            except Exception as e:
                self.logger.warning(f"⚠️ Gemini API error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    metrics_collector.record_openai_request("error")
                    self.logger.error(
                        f"Gemini API failed after {max_retries} attempts: {e}",
                        extra={'operation': 'generate_response', 'model': self.model_name}
                    )
                    raise

    def _convert_to_gemini_format(self, messages: List[Dict]) -> str:
        """Конвертировать сообщения в формат Gemini"""
        conversation_text = ""

        for msg in messages:
            if msg['role'] == 'system':
                conversation_text += f"Контекст: {msg['content']}\n\n"
            elif msg['role'] == 'user':
                conversation_text += f"Пользователь: {msg['content']}\n\n"
            elif msg['role'] == 'assistant':
                conversation_text += f"Ассистент: {msg['content']}\n\n"

        conversation_text += "Ассистент:"
        return conversation_text.strip()

    async def close(self):
        pass

