import os
import asyncio
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.ai.openai_client import OpenAIClient
from infrastructure.ai.ollama_client import OllamaClient
from infrastructure.ai.gemini_client import GeminiClient
from infrastructure.ai.huggingface_client import HuggingFaceClient
from infrastructure.ai.deepseek_client import DeepSeekClient
from infrastructure.monitoring.logging import StructuredLogger


class AIFactory:
    @staticmethod
    def create_client() -> AIClientInterface:
        """Создать AI клиент на основе конфигурации"""
        logger = StructuredLogger("ai_factory")

        provider = os.getenv("AI_PROVIDER", "ollama").lower()

        logger.info(f"Creating AI client for provider: {provider}")

        if provider == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
            return OpenAIClient()

        elif provider == "ollama":
            return OllamaClient()

        elif provider == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                raise ValueError("GEMINI_API_KEY is required for Gemini provider")
            return GeminiClient()

        elif provider == "huggingface":
            return HuggingFaceClient()

        elif provider == "deepseek":
            if not os.getenv("DEEPSEEK_API_KEY"):
                raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek provider")
            return DeepSeekClient()

        else:
            logger.warning(f"Unknown AI provider: {provider}. Using Ollama as default.")
            return OllamaClient()

    @staticmethod
    async def create_client_async() -> AIClientInterface:
        """Создать AI клиент асинхронно (для использования в async контексте)"""
        # Для большинства клиентов синхронное создание достаточно
        return AIFactory.create_client()