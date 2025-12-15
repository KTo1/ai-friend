from typing import List, Optional, Dict, Any
from domain.entity.rag_memory import RAGMemory
from domain.service.rag_service import RAGService
from infrastructure.database.repositories.rag_repository import RAGRepository
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageRAGUseCase:
    """Use case для управления RAG памятью"""

    def __init__(self, rag_repository: RAGRepository, rag_service: RAGService):
        self.rag_repo = rag_repository
        self.rag_service = rag_service
        self.logger = StructuredLogger("manage_rag_uc")
        self.bot_keywords = [
            'айна', 'бот', 'ты ', 'тебе', 'твой', 'твоя', 'твоё', 'у тебя',
            'тебя', 'с тобой', 'тобой', 'о тебе', 'ваш', 'ваша', 'ваше'
        ]

    @trace_span("usecase.extract_memories", attributes={"component": "application"})
    async def extract_and_save_memories(self, user_id: int, character_id: int, message: str) -> List[RAGMemory]:
        """Извлечь и сохранить воспоминания ТОЛЬКО из текущего сообщения"""
        try:
            # Извлекаем воспоминания только из текущего сообщения
            memories = await self.rag_service.extract_memories_from_message(user_id, message)

            if not memories:
                return []

            # Фильтруем воспоминания, связанные с ботом
            filtered_memories = self._filter_bot_memories(memories)

            if not filtered_memories:
                return []

            # Проверяем на дубликаты перед сохранением
            unique_memories = await self._filter_duplicate_memories(user_id, character_id, filtered_memories)

            if not unique_memories:
                return []

            # Генерируем эмбеддинги
            memories_with_embeddings = await self.rag_service.generate_embeddings(unique_memories)

            # Сохраняем в базу
            saved_memories = []
            for memory in memories_with_embeddings:
                memory_id = self.rag_repo.save_memory(memory, character_id)
                if memory_id:
                    memory.id = memory_id
                    saved_memories.append(memory)

            self.logger.info(
                f"RAG: Saved {len(saved_memories)} new memories from current message",
                extra={
                    'user_id': user_id,
                    'character_id': character_id,
                    'original_count': len(memories),
                    'unique_count': len(saved_memories)
                }
            )

            return saved_memories

        except Exception as e:
            self.logger.error(f"Error extracting memories for user {user_id}: {e}")
            return []

    async def _filter_duplicate_memories(self, user_id: int,  character_id: int, new_memories: List[RAGMemory]) -> List[RAGMemory]:
        """Фильтрация дубликатов на основе семантической схожести"""
        if not new_memories:
            return []

        # Получаем существующие воспоминания пользователя
        existing_memories = self.rag_repo.get_user_memories(user_id, character_id, limit=50)

        if not existing_memories:
            return new_memories

        unique_memories = []

        for new_memory in new_memories:
            is_duplicate = False

            # Проверяем семантическую схожесть с существующими воспоминаниями
            for existing_memory in existing_memories:
                if existing_memory.embedding and new_memory.embedding:
                    similarity = self._cosine_similarity(existing_memory.embedding, new_memory.embedding)
                    if similarity > 0.85:  # Порог схожести
                        self.logger.debug(f"Filtered duplicate memory: {new_memory.content[:50]}...")
                        is_duplicate = True
                        break

            if not is_duplicate:
                unique_memories.append(new_memory)

        return unique_memories

    def _filter_bot_memories(self, memories: List[RAGMemory]) -> List[RAGMemory]:
        """Отфильтровать воспоминания, связанные с ботом"""
        filtered_memories = []

        for memory in memories:
            content_lower = memory.content.lower()

            # Проверяем, не содержит ли воспоминание ссылки на бота
            is_bot_related = any(keyword in content_lower for keyword in self.bot_keywords)

            if not is_bot_related:
                filtered_memories.append(memory)

        return filtered_memories

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Вычисление косинусной схожести между векторами"""
        if len(vec1) != len(vec2) or not vec1 or not vec2:
            return 0.0

        try:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return round(similarity, 6)
        except Exception as e:
            self.logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0

    @trace_span("usecase.get_relevant_memories", attributes={"component": "application"})
    async def get_relevant_memories(self, user_id: int, character_id: int, user_message: str,
                                    limit: int = 5) -> List[RAGMemory]:
        """Получить релевантные воспоминания для текущего сообщения"""
        try:
            # Генерируем эмбеддинг для текущего сообщения
            temp_memory = RAGMemory(content=user_message)
            memories_with_embeddings = await self.rag_service.generate_embeddings([temp_memory])

            if not memories_with_embeddings or not memories_with_embeddings[0].embedding:
                # Если не удалось сгенерировать эмбеддинг, возвращаем самые важные воспоминания
                return self.rag_repo.get_user_memories(user_id, character_id, limit=limit)

            query_embedding = memories_with_embeddings[0].embedding

            # Ищем похожие воспоминания
            similar_memories = self.rag_repo.search_similar_memories(
                user_id, character_id, query_embedding, limit=limit, similarity_threshold=0.3
            )

            # Если не нашли похожих, берем самые важные
            if not similar_memories:
                similar_memories = self.rag_repo.get_user_memories(user_id, character_id, limit=limit)

            return similar_memories

        except Exception as e:
            self.logger.error(f"Error getting relevant memories for user {user_id}: {e}")
            return []

    @trace_span("usecase.prepare_rag_context", attributes={"component": "application"})
    async def prepare_rag_context(self, user_id: int, character_id: int, user_message: str,
                                  conversation_context: List[Dict] = None) -> str:
        """Подготовить RAG контекст для диалога"""
        try:
            # Получаем релевантные воспоминания
            relevant_memories = await self.get_relevant_memories(user_id, character_id, user_message)

            # Подготавливаем текст для контекста
            rag_context = self.rag_service.prepare_memories_for_context(relevant_memories)

            return rag_context

        except Exception as e:
            self.logger.error(f"Error preparing RAG context for user {user_id}: {e}")
            return ""

    @trace_span("usecase.get_user_memories", attributes={"component": "application"})
    def get_user_memories(self, user_id: int, limit: int = 20) -> List[RAGMemory]:
        """Получить все воспоминания пользователя"""
        return self.rag_repo.get_user_memories(user_id, limit=limit)

    @trace_span("usecase.clear_user_memories", attributes={"component": "application"})
    def clear_user_memories(self, user_id: int) -> bool:
        """Очистить все воспоминания пользователя"""
        return self.rag_repo.delete_user_memories(user_id)

    @trace_span("usecase.get_memory_stats", attributes={"component": "application"})
    def get_memory_stats(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику по памяти пользователя"""
        memories = self.get_user_memories(user_id, limit=1000)  # Большой лимит для статистики

        if not memories:
            return {"total_memories": 0, "by_type": {}}

        by_type = {}
        for memory in memories:
            mem_type = memory.memory_type.value
            if mem_type not in by_type:
                by_type[mem_type] = 0
            by_type[mem_type] += 1

        return {
            "total_memories": len(memories),
            "by_type": by_type,
            "avg_importance": sum(m.importance_score for m in memories) / len(memories)
        }