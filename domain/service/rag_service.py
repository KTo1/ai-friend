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

    async def extract_memories_from_message(self, user_id: int, message: str) -> List[RAGMemory]:
        """Извлечь важные факты ИСКЛЮЧИТЕЛЬНО из текущего сообщения пользователя"""

        # УПРОЩЕННЫЙ И БОЛЕЕ ЭФФЕКТИВНЫЙ ПРОМПТ
        system_prompt = """
        Ты — инструмент для извлечения персональных фактов о пользователе. 
        Анализируй сообщение и классифицируй информацию по типам:

        ТИПЫ ФАКТОВ И ПРИМЕРЫ:
        1. personal_detail - Личные данные (имя, город, работа)
           Пример: "Меня зовут Анна" → тип: personal_detail

        2. age - Возраст в годах
           Пример: "Мне 25 лет" → тип: age

        3. interest - Интересы и хобби
           Пример: "Люблю читать книги" → тип: interest

        4. mood - Текущее настроение
           Пример: "Сегодня я счастлив" → тип: mood

        5. personal_characteristic - Черты характера
           Пример: "Я терпеливый человек" → тип: personal_characteristic

        6. habit - Привычки и рутины  
           Пример: "Каждое утро бегаю" → тип: habit

        7. goal - Цели и мечты
           Пример: "Хочу выучить английский" → тип: goal

        8. event - Важные события
           Пример: "Вчера защитил диплом" → тип: event

        9. preference - Предпочтения и вкусы
           Пример: "Предпочитаю чай кофе" → тип: preference

        Формат ответа - JSON:
        {
            "memories": [
                {
                    "type": "ТИП_ИЗ_СПИСКА_ВЫШЕ",
                    "content": "Краткая формулировка",
                    "importance": 0.7,
                    "metadata": {
                        "возраст": 25,
                        "настроение": "радостное",
                        "интересы": ["чтение", "спорт"]
                    }
                }
            ]
        }

        Извлекай ТОЛЬКО если информация явно указана в сообщении.
        """

        user_prompt = f"""
    Сообщение пользователя: "{message}"

    Извлеки ТОЛЬКО новые персональные факты о пользователе из этого сообщения.
    """

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = await self.ai_client.generate_response(
                messages,
                max_tokens=500,  # Уменьшаем, т.к. анализируем только одно сообщение
                temperature=0.1
            )

            memories_data = self._parse_llm_response(response)

            memories = []
            for mem_data in memories_data.get('memories', []):
                content = mem_data['content'].lower()

                # Фильтруем факты, связанные с ботом
                bot_keywords = ['айна', 'бот', 'ты ', 'тебе', 'твой', 'твоя', 'твоё', 'у тебя', 'тебя']
                if any(keyword in content for keyword in bot_keywords):
                    self.logger.debug(f"Filtered bot-related memory: {mem_data['content']}")
                    continue

                memory = RAGMemory(
                    user_id=user_id,
                    memory_type=MemoryType(mem_data['type']),
                    content=mem_data['content'],
                    source_message=message,
                    importance_score=mem_data['importance']
                )
                memories.append(memory)

            self.logger.info(
                f"Extracted {len(memories)} memories from current message",
                extra={'user_id': user_id, 'message_length': len(message), 'memories_count': len(memories)}
            )

            return memories

        except Exception as e:
            self.logger.error(f"Error extracting memories: {e}")
            return []

    async def generate_embeddings(self, memories: List[RAGMemory]) -> List[RAGMemory]:
        try:
            for memory in memories:
                if memory.embedding is None:
                    # Используем метод get_embedding из ai_client
                    embedding = await self.ai_client.get_embedding(memory.content)
                    memory.embedding = embedding
            return memories
        except Exception as e:
            self.logger.error(f'Error generating embeddings: {e}')
            return memories

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Парсинг JSON ответа от LLM"""
        try:
            # Очищаем ответ от возможных markdown блоков
            cleaned_response = re.sub(r'```json\s*|\s*```', '', response).strip()
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse LLM response: {response}")
            return {"memories": []}

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