import json
import psycopg2
from typing import List, Optional
from datetime import datetime
from domain.entity.rag_memory import RAGMemory, MemoryType
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger


class RAGRepository:
    """Репозиторий для работы с RAG памятью"""

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger("rag_repository")
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы для RAG памяти"""
        try:
            # Создаем таблицу для хранения воспоминаний
            self.db.execute_query('''
                CREATE TABLE IF NOT EXISTS user_rag_memories (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    memory_type VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    source_message TEXT,
                    importance_score FLOAT DEFAULT 0.5,
                    embedding JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}',

                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            # Создаем индексы для эффективного поиска
            self.db.execute_query('''
                CREATE INDEX IF NOT EXISTS idx_rag_memories_user_id 
                ON user_rag_memories(user_id)
            ''')

            self.db.execute_query('''
                CREATE INDEX IF NOT EXISTS idx_rag_memories_importance 
                ON user_rag_memories(importance_score DESC)
            ''')

            self.db.execute_query('''
                CREATE INDEX IF NOT EXISTS idx_rag_memories_type 
                ON user_rag_memories(memory_type)
            ''')

            self.logger.info("RAG memories table initialized")

        except Exception as e:
            self.logger.error(f"Error initializing RAG table: {e}")

    def save_memory(self, memory: RAGMemory) -> int:
        """Сохранить воспоминание"""
        try:
            result = self.db.execute_query('''
                INSERT INTO user_rag_memories 
                (user_id, memory_type, content, source_message, importance_score, 
                 embedding, created_at, updated_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                memory.user_id,
                memory.memory_type.value,
                memory.content,
                memory.source_message,
                memory.importance_score,
                json.dumps(memory.embedding) if memory.embedding else None,
                memory.created_at,
                memory.updated_at,
                json.dumps(memory.metadata)
            ))

            if result and hasattr(result, '__getitem__') and 'id' in result:
                return result['id']
            else:
                last_id = self.db.fetch_one("SELECT LASTVAL() as id")
                return last_id['id'] if last_id else 0

        except Exception as e:
            self.logger.error(f"Error saving memory: {e}")
            return 0

    def get_user_memories(self, user_id: int, limit: int = 50,
                          min_importance: float = 0.3) -> List[RAGMemory]:
        """Получить воспоминания пользователя"""
        try:
            results = self.db.fetch_all('''
                SELECT id, user_id, memory_type, content, source_message, 
                       importance_score, embedding, created_at, updated_at, metadata
                FROM user_rag_memories 
                WHERE user_id = %s AND importance_score >= %s
                ORDER BY importance_score DESC, updated_at DESC
                LIMIT %s
            ''', (user_id, min_importance, limit))

            memories = []
            for result in results:
                memory = RAGMemory(
                    id=result['id'],
                    user_id=result['user_id'],
                    memory_type=MemoryType(result['memory_type']),
                    content=result['content'],
                    source_message=result['source_message'],
                    importance_score=result['importance_score'],
                    embedding=json.loads(result['embedding']) if result['embedding'] else None,
                    created_at=result['created_at'],
                    updated_at=result['updated_at'],
                    metadata=json.loads(result['metadata']) if result['metadata'] else {}
                )
                memories.append(memory)

            return memories

        except Exception as e:
            self.logger.error(f"Error getting user memories: {e}")
            return []

    def search_similar_memories(self, user_id: int, query_embedding: List[float],
                                limit: int = 5, similarity_threshold: float = 0.7) -> List[RAGMemory]:
        """Поиск похожих воспоминаний по эмбеддингу"""
        try:
            # Для векторного поиска в PostgreSQL можно использовать расширение vector
            # Здесь упрощенная реализация через косинусное расстояние
            results = self.db.fetch_all('''
                SELECT id, user_id, memory_type, content, source_message, 
                       importance_score, embedding, created_at, updated_at, metadata
                FROM user_rag_memories 
                WHERE user_id = %s AND embedding IS NOT NULL
                ORDER BY importance_score DESC
                LIMIT %s
            ''', (user_id, limit * 3))  # Берем больше, потом фильтруем

            # Вычисляем косинусную схожесть
            memories_with_similarity = []
            for result in results:
                if result['embedding']:
                    memory_embedding = json.loads(result['embedding'])
                    similarity = self._cosine_similarity(query_embedding, memory_embedding)

                    if similarity >= similarity_threshold:
                        memory = RAGMemory(
                            id=result['id'],
                            user_id=result['user_id'],
                            memory_type=MemoryType(result['memory_type']),
                            content=result['content'],
                            source_message=result['source_message'],
                            importance_score=result['importance_score'],
                            embedding=memory_embedding,
                            created_at=result['created_at'],
                            updated_at=result['updated_at'],
                            metadata=json.loads(result['metadata']) if result['metadata'] else {}
                        )
                        memories_with_similarity.append((memory, similarity))

            # Сортируем по схожести и берем топ
            memories_with_similarity.sort(key=lambda x: x[1], reverse=True)
            return [mem for mem, _ in memories_with_similarity[:limit]]

        except Exception as e:
            self.logger.error(f"Error searching similar memories: {e}")
            return []

    def delete_memory(self, memory_id: int) -> bool:
        """Удалить воспоминание"""
        try:
            self.db.execute_query(
                'DELETE FROM user_rag_memories WHERE id = %s',
                (memory_id,)
            )
            return True
        except Exception as e:
            self.logger.error(f"Error deleting memory: {e}")
            return False

    def delete_user_memories(self, user_id: int) -> bool:
        """Удалить все воспоминания пользователя"""
        try:
            self.db.execute_query(
                'DELETE FROM user_rag_memories WHERE user_id = %s',
                (user_id,)
            )
            return True
        except Exception as e:
            self.logger.error(f"Error deleting user memories: {e}")
            return False

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Вычисление косинусной схожести между векторами"""
        if len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)