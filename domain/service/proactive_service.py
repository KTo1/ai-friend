from datetime import datetime
from typing import Optional
from domain.entity.user import User


class ProactiveService:
    """Чистая бизнес-логика проактивных сообщений."""

    def __init__(self):
        pass

    async def generate_proactive_message(self, user_id: int, character_id: int) -> str:
        """Генерирует текст проактивного сообщения с контекстом."""

        return "Привет! Давно не общались. Как настроение? Расскажешь, что у тебя нового? 🌟"

