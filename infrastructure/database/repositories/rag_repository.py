import json
import psycopg2
from typing import List, Optional
from datetime import datetime
from domain.entity.rag_memory import RAGMemory, MemoryType
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger

class RAGRepository:

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger('rag_repository')

    def save_memory(self, memory: RAGMemory) -> int:
        try:
            # Конвертируем embedding в строку для PostgreSQL vector типа
            embedding_str = None
            if memory.embedding:
                embedding_str = '[' + ','.join(map(str, memory.embedding)) + ']'

            query = '''
                    INSERT INTO user_rag_memories
                    (user_id, memory_type, content, source_message, importance_score,
                     embedding, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id \
                    '''
            params = (
                memory.user_id,
                memory.memory_type.value,
                memory.content,
                memory.source_message,
                memory.importance_score,
                embedding_str,  # Используем строку для vector типа
                memory.created_at,
                memory.updated_at
            )

            result = self.db.fetch_one(query, params)
            return result['id'] if result and 'id' in result else 0

        except Exception as e:
            self.logger.error(f'Error saving memory: {e}')
            return 0

    def get_user_memories(self, user_id: int, limit: int=50, min_importance: float=0.7) -> List[RAGMemory]:
        try:
            results = self.db.fetch_all("""
                SELECT id, user_id, memory_type, content, source_message, 
                       importance_score, embedding, created_at, updated_at
                FROM user_rag_memories 
                WHERE user_id = %s AND importance_score >= %s
                ORDER BY importance_score DESC, updated_at DESC
                LIMIT %s
            """, (user_id, min_importance, limit))
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
                    updated_at=result['updated_at']
                )
                memories.append(memory)
            return memories
        except Exception as e:
            self.logger.error(f'Error getting user memories: {e}')
            return []

    def search_similar_memories(self, user_id: int, query_embedding: List[float],
                                limit: int = 5, similarity_threshold: float = 0.6) -> List[RAGMemory]:
        try:
            # Конвертируем embedding в строку для PostgreSQL
            embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

            # ВАЖНО: pgvector оператор <=> возвращает косинусное расстояние (1 - cosine similarity)
            # Поэтому: similarity = 1 - distance = cosine similarity
            results = self.db.fetch_all('''
                                        SELECT id,
                                               user_id,
                                               memory_type,
                                               content,
                                               source_message,
                                               importance_score,
                                               embedding,
                                               created_at,
                                               updated_at,
                                               1 - (embedding <=> %s::vector) as similarity
                                        FROM user_rag_memories
                                        WHERE user_id = %s
                                          AND embedding IS NOT NULL
                                        ORDER BY similarity DESC -- ⚠️ ИЗМЕНЕНО: сортируем по similarity, а не distance
                                            LIMIT %s
                                        ''', (embedding_str, user_id, limit))

            self.logger.debug(f'Found {len(results)} memories before filtering')

            # Фильтруем по порогу схожести
            filtered_results = []
            for result in results:
                similarity = result.get('similarity', 0.0)
                self.logger.debug(
                    f'Memory ID {result["id"]}: "{result["content"][:30]}..." - similarity: {similarity:.4f}')

                if similarity >= similarity_threshold:
                    # Удаляем поле similarity из результата
                    result_copy = dict(result)
                    if 'similarity' in result_copy:
                        del result_copy['similarity']
                    filtered_results.append(result_copy)

            self.logger.info(f'Found {len(filtered_results)} memories with similarity >= {similarity_threshold}')

            # Конвертируем результаты в RAGMemory объекты
            memories = []
            for result in filtered_results:
                # Парсим вектор из PostgreSQL
                embedding = None
                if result['embedding']:
                    if isinstance(result['embedding'], list):
                        embedding = result['embedding']
                    else:
                        # Парсим строку вектора
                        embedding = self._parse_pgvector(result['embedding'])

                memory = RAGMemory(
                    id=result['id'],
                    user_id=result['user_id'],
                    memory_type=MemoryType(result['memory_type']),
                    content=result['content'],
                    source_message=result['source_message'],
                    importance_score=result['importance_score'],
                    embedding=embedding,
                    created_at=result['created_at'],
                    updated_at=result['updated_at']
                )
                memories.append(memory)

            return memories

        except Exception as e:
            self.logger.error(f'Error searching similar memories: {e}', exc_info=True)
            return []

    def delete_user_memories(self, user_id: int) -> bool:
        try:
            self.db.execute_query("DELETE FROM user_rag_memories WHERE user_id = %s", (user_id,))
            return True
        except Exception as e:
            self.logger.error(f'Error deleting user memories: {e}')
            return False

    def _parse_pgvector(self, vector_data):
        """Парсит вектор из PostgreSQL в список чисел"""
        if vector_data is None:
            return None

        # Если уже список (может вернуться из драйвера как список)
        if isinstance(vector_data, list):
            return vector_data

        # Если это строка в формате вектора PostgreSQL
        if isinstance(vector_data, str):
            try:
                # Удаляем квадратные скобки и пробелы
                cleaned = vector_data.strip('[]')
                if not cleaned:
                    return []

                # Разделяем по запятым и конвертируем в float
                return [float(x.strip()) for x in cleaned.split(',')]
            except Exception as e:
                self.logger.error(f'Error parsing pgvector string: {e}, data: {vector_data[:100]}...')

        # Если это другой формат (например, memoryview или bytes)
        try:
            # Попробуем конвертировать в строку и распарсить
            str_repr = str(vector_data)
            if str_repr.startswith('[') and str_repr.endswith(']'):
                return self._parse_pgvector(str_repr)
        except Exception as e:
            self.logger.error(f'Error converting vector to string: {e}')

        return None