from abc import ABC, abstractmethod
from typing import List, Dict


class AIClientInterface(ABC):
    """Абстрактный интерфейс для AI клиентов"""

    @abstractmethod
    async def generate_response(self, messages: List[Dict], max_tokens: int = None, temperature: float = None) -> str:
        """Сгенерировать ответ (асинхронно)"""
        pass

    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        pass

    async def close(self):
        """Закрыть ресурсы (асинхронно)"""
        pass