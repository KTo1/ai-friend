# AI package
from .deepseek_client import DeepSeekClient  # ← ДОБАВЬТЕ
from .ollama_client import OllamaClient
# from .openai_client import OpenAIClient
# from .gemini_client import GeminiClient
from .huggingface_client import HuggingFaceClient

__all__ = [
    # 'OpenAIClient',
    'OllamaClient',
    # 'GeminiClient',
    'HuggingFaceClient',
    'DeepSeekClient'  # ← ДОБАВЬТЕ
]