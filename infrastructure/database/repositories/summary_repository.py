import json
from typing import List, Optional
from datetime import datetime
from domain.entity.conversation_summary import ConversationSummary
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger

class SummaryRepository:

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger('summary_repository')
        self._init_table()

    def _init_table(self):
        try:
            self.db.execute_query('''
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    character_id INTEGER NOT NULL,
                    level INTEGER NOT NULL DEFAULT 1,
                    content TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    CONSTRAINT fk_character FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE,
                    UNIQUE(user_id, character_id, level)  -- Храним только одну суммаризацию каждого уровня
                )
            ''')

            self.logger.info('Conversation summaries table initialized')

        except Exception as e:
            self.logger.error(f'Error initializing summary table: {e}')

    def save_summary(self, summary: ConversationSummary) -> bool:
        """Сохраняет или обновляет суммаризацию"""

        try:
            # Используем UPSERT (UPDATE or INSERT) через ON CONFLICT
            query = '''
                INSERT INTO conversation_summaries 
                (user_id, character_id, level, content, message_count, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, character_id, level) 
                DO UPDATE SET 
                    content = EXCLUDED.content,
                    message_count = EXCLUDED.message_count,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
            '''

            result = self.db.fetch_one(query, (
                summary.user_id,
                summary.character_id,
                summary.level,
                summary.content,
                summary.message_count,
                datetime.utcnow()
            ))

            if result and result['id']:
                summary.id = result['id']
                return True
            return False

        except Exception as e:
            self.logger.error(f'Error saving summary: {e}')
            return False

    def get_summary(self, user_id: int, character_id: int,
                   level: int = 1) -> Optional[ConversationSummary]:
        """Получает суммаризацию указанного уровня"""

        try:
            result = self.db.fetch_one('''
                SELECT id, user_id, character_id, level, content,
                       message_count, created_at, updated_at, deleted_at
                FROM conversation_summaries
                WHERE user_id = %s AND character_id = %s AND level = %s
            ''', (user_id, character_id, level))

            if result:
                return ConversationSummary(
                    id=result['id'],
                    user_id=result['user_id'],
                    character_id=result['character_id'],
                    level=result['level'],
                    content=result['content'],
                    message_count=result['message_count'],
                    created_at=result['created_at'],
                    updated_at=result['updated_at'],
                    deleted_at=result['deleted_at']
                )
            return None

        except Exception as e:
            self.logger.error(f'Error getting summary: {e}')
            return None

    def get_all_summaries(self, user_id: int, character_id: int) -> List[ConversationSummary]:
        """Получает все суммаризации пользователя для персонажа"""

        try:
            results = self.db.fetch_all('''
                SELECT id, user_id, character_id, level, content,
                       message_count, created_at, updated_at, deleted_at
                FROM conversation_summaries
                WHERE user_id = %s AND character_id = %s
                ORDER BY level DESC, updated_at DESC
            ''', (user_id, character_id))

            summaries = []
            for result in results:
                summaries.append(ConversationSummary(
                    id=result['id'],
                    user_id=result['user_id'],
                    character_id=result['character_id'],
                    level=result['level'],
                    content=result['content'],
                    message_count=result['message_count'],
                    created_at=result['created_at'],
                    updated_at=result['updated_at'],
                    deleted_at=result['deleted_at']
                ))
            return summaries

        except Exception as e:
            self.logger.error(f'Error getting summaries: {e}')
            return []

    def delete_summaries(self, user_id: int, character_id: int) -> bool:
        """Удаляет все суммаризации пользователя для персонажа"""

        try:
            self.db.execute_query(
                'UPDATE conversation_summaries SET deleted_at = %s WHERE user_id = %s AND character_id = %s',
                (datetime.utcnow(), user_id, character_id)
            )
            return True
        except Exception as e:
            self.logger.error(f'Error deleting user summaries: {e}')
            return False
