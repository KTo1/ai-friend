import json
import re
from typing import List, Optional, Dict, Any, Tuple
from domain.entity.rag_memory import RAGMemory, MemoryType
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.logging import StructuredLogger


class RAGService:
    """Сервис для извлечения и управления памятью пользователя"""

    def __init__(self, ai_client: AIClientInterface):
        self.ai_client = ai_client
        self.logger = StructuredLogger("rag_service")

    async def extract_memories_from_message(self, user_id: int, message: str,
                                            conversation_context: List[Dict] = None) -> List[RAGMemory]:
        """Извлечь важные факты из сообщения пользователя с помощью LLM"""

        # Промпт для извлечения фактов
        system_prompt = """
Ты — аналитик, который выделяет важные персональные факты из сообщений пользователя.

ИЗВЛЕКАЙ ТОЛЬКО:
- Личные предпочтения (люблю/не люблю, нравится/не нравится)
- Важные события (дни рождения, годовщины, достижения)
- Личные характеристики (аллергии, ограничения, привычки)
- Долгосрочные планы и цели
- Значимые отношения (семья, друзья)
- Уникальные навыки и умения

НЕ ИЗВЛЕКАЙ:
- Повседневные действия (сегодня пошел в магазин)
- Временные эмоции (сегодня грустно/весело)
- Общие размышления без конкретики
- Поверхностные комментарии о погоде и т.д.

Формат ответа - JSON:
{
    "memories": [
        {
            "type": "fact|preference|event|personal_detail",
            "content": "Краткая формулировка факта",
            "importance": 0.8,
            "reason": "Почему этот факт важен"
        }
    ]
}

Отвечай ТОЛЬКО JSON, без других текстов.
"""

        user_prompt = f"""
Сообщение пользователя: "{message}"

Контекст разговора (последние сообщения):
{self._format_conversation_context(conversation_context) if conversation_context else "Нет контекста"}

Проанализируй и извлеки важные персональные факты.
"""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = await self.ai_client.generate_response(
                messages,
                max_tokens=1000,
                temperature=0.1  # Низкая температура для консистентности
            )

            # Парсим JSON ответ
            memories_data = self._parse_llm_response(response)

            memories = []
            for mem_data in memories_data.get('memories', []):
                memory = RAGMemory(
                    user_id=user_id,
                    memory_type=MemoryType(mem_data['type']),
                    content=mem_data['content'],
                    source_message=message,
                    importance_score=mem_data['importance'],
                    metadata={'extraction_reason': mem_data['reason']}
                )
                memories.append(memory)

            self.logger.info(
                f"Extracted {len(memories)} memories from user {user_id} message",
                extra={'user_id': user_id, 'message_length': len(message), 'memories_count': len(memories)}
            )

            return memories

        except Exception as e:
            self.logger.error(f"Error extracting memories: {e}")
            return []

    async def generate_embeddings(self, memories: List[RAGMemory]) -> List[RAGMemory]:
        """Генерация эмбеддингов для воспоминаний"""
        try:
            for memory in memories:
                if memory.embedding is None:
                    # Используем DeepSeek для генерации эмбеддингов
                    embedding = await self._get_embedding(memory.content)
                    memory.embedding = embedding

            return memories
        except Exception as e:
            self.logger.error(f"Error generating embeddings: {e}")
            return memories

    async def _get_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг текста через DeepSeek"""
        # Для DeepSeek используем их API для эмбеддингов
        # Временно используем упрощенный подход - позже можно интегрировать с embeddings API
        prompt = f"""
        Преобразуй следующий текст в числовой вектор для семантического поиска.
        Текст: "{text}"

        Верни ТОЛЬКО JSON с массивом из 384 чисел:
        {{"embedding": [число1, число2, ...]}}
        """

        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.ai_client.generate_response(messages, max_tokens=500)

            # Парсим ответ и генерируем псевдо-эмбеддинг
            # В реальной реализации нужно использовать专门的 embeddings API
            return self._generate_simple_embedding(text)

        except Exception as e:
            self.logger.error(f"Error getting embedding: {e}")
            return self._generate_simple_embedding(text)

    def _generate_simple_embedding(self, text: str) -> List[float]:
        """Упрощенная генерация эмбеддинга (заглушка)"""
        # В реальной реализации нужно подключить embeddings API DeepSeek
        import hashlib
        import struct

        # Генерируем детерминированный "эмбеддинг" на основе хеша текста
        hash_obj = hashlib.md5(text.encode())
        hash_bytes = hash_obj.digest()

        # Создаем вектор из 384 элементов (как в популярных моделях)
        embedding = []
        for i in range(384):
            # Используем разные части хеша для заполнения вектора
            byte_idx = i % len(hash_bytes)
            value = (hash_bytes[byte_idx] / 255.0) * 2 - 1  # Нормализуем к [-1, 1]
            embedding.append(round(value, 6))

        return embedding

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Парсинг JSON ответа от LLM"""
        try:
            # Очищаем ответ от возможных markdown блоков
            cleaned_response = re.sub(r'```json\s*|\s*```', '', response).strip()
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response: {response}")
            return {"memories": []}

    def _format_conversation_context(self, context: List[Dict]) -> str:
        """Форматирование контекста разговора для промпта"""
        formatted = []
        for msg in context[-5:]:  # Берем последние 5 сообщений
            role = "Пользователь" if msg['role'] == 'user' else "Айна"
            formatted.append(f"{role}: {msg['content']}")

        return "\n".join(formatted)

    def prepare_memories_for_context(self, memories: List[RAGMemory], max_tokens: int = 500) -> str:
        """Подготовка воспоминаний для включения в контекст диалога"""
        if not memories:
            return ""

        context_parts = ["💫 Я помню о тебе:"]
        token_count = len("💫 Я помню о тебе:")

        for memory in sorted(memories, key=lambda x: x.importance_score, reverse=True):
            memory_text = f"• {memory.content}"
            memory_tokens = len(memory_text)

            if token_count + memory_tokens > max_tokens:
                break

            context_parts.append(memory_text)
            token_count += memory_tokens

        return "\n".join(context_parts)