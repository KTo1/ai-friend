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

    @trace_span("usecase.extract_memories", attributes={"component": "application"})
    async def extract_and_save_memories(self, user_id: int, message: str,
                                        conversation_context: List[Dict] = None) -> List[RAGMemory]:
        """Извлечь и сохранить воспоминания из сообщения"""
        try:
            # Извлекаем воспоминания с помощью LLM
            memories = await self.rag_service.extract_memories_from_message(
                user_id, message, conversation_context
            )

            if not memories:
                return []

            # Генерируем эмбеддинги
            memories_with_embeddings = await self.rag_service.generate_embeddings(memories)

            # Сохраняем в базу
            saved_memories = []
            for memory in memories_with_embeddings:
                memory_id = self.rag_repo.save_memory(memory)
                if memory_id:
                    memory.id = memory_id
                    saved_memories.append(memory)

            self.logger.info(
                f"Extracted and saved {len(saved_memories)} memories for user {user_id}",
                extra={'user_id': user_id, 'extracted_count': len(memories), 'saved_count': len(saved_memories)}
            )

            return saved_memories

        except Exception as e:
            self.logger.error(f"Error extracting memories for user {user_id}: {e}")
            return []

    @trace_span("usecase.get_relevant_memories", attributes={"component": "application"})
    async def get_relevant_memories(self, user_id: int, user_message: str,
                                    limit: int = 5) -> List[RAGMemory]:
        """Получить релевантные воспоминания для текущего сообщения"""
        try:
            # Генерируем эмбеддинг для текущего сообщения
            temp_memory = RAGMemory(content=user_message)
            memories_with_embeddings = await self.rag_service.generate_embeddings([temp_memory])

            if not memories_with_embeddings or not memories_with_embeddings[0].embedding:
                # Если не удалось сгенерировать эмбеддинг, возвращаем самые важные воспоминания
                return self.rag_repo.get_user_memories(user_id, limit=limit)

            query_embedding = memories_with_embeddings[0].embedding

            # Ищем похожие воспоминания
            similar_memories = self.rag_repo.search_similar_memories(
                user_id, query_embedding, limit=limit
            )

            # Если не нашли похожих, берем самые важные
            if not similar_memories:
                similar_memories = self.rag_repo.get_user_memories(user_id, limit=limit)

            return similar_memories

        except Exception as e:
            self.logger.error(f"Error getting relevant memories for user {user_id}: {e}")
            return []

    @trace_span("usecase.prepare_rag_context", attributes={"component": "application"})
    async def prepare_rag_context(self, user_id: int, user_message: str,
                                  conversation_context: List[Dict] = None) -> str:
        """Подготовить RAG контекст для диалога"""
        try:
            # Получаем релевантные воспоминания
            relevant_memories = await self.get_relevant_memories(user_id, user_message)

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

    @trace_span("usecase.delete_memory", attributes={"component": "application"})
    def delete_memory(self, memory_id: int) -> bool:
        """Удалить воспоминание"""
        return self.rag_repo.delete_memory(memory_id)

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