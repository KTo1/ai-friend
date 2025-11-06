import json
from typing import Optional
from domain.entity.message_limit import UserMessageLimit, MessageLimitConfig
from infrastructure.database.database import Database


class MessageLimitRepository:
    """Репозиторий для хранения лимитов сообщений пользователей"""

    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы лимитов сообщений"""
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS user_message_limits (
                user_id INTEGER PRIMARY KEY,
                config TEXT NOT NULL,
                total_messages_processed INTEGER DEFAULT 0,
                total_characters_processed INTEGER DEFAULT 0,
                average_message_length REAL DEFAULT 0.0,
                rejected_messages_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def save_user_limit(self, user_limit: UserMessageLimit):
        """Сохранить лимиты пользователя"""
        config_data = {
            'max_message_length': user_limit.config.max_message_length,
            'max_context_messages': user_limit.config.max_context_messages,
            'max_context_length': user_limit.config.max_context_length
        }

        self.db.execute_query('''
            INSERT OR REPLACE INTO user_message_limits 
            (user_id, config, total_messages_processed, total_characters_processed, 
             average_message_length, rejected_messages_count, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            user_limit.user_id,
            json.dumps(config_data),
            user_limit.total_messages_processed,
            user_limit.total_characters_processed,
            user_limit.average_message_length,
            user_limit.rejected_messages_count
        ))

    def get_user_limit(self, user_id: int, default_config: MessageLimitConfig) -> Optional[UserMessageLimit]:
        """Получить лимиты пользователя"""
        result = self.db.fetch_one(
            '''SELECT config, total_messages_processed, total_characters_processed, 
                      average_message_length, rejected_messages_count 
               FROM user_message_limits WHERE user_id = ?''',
            (user_id,)
        )

        if result:
            try:
                config_data = json.loads(result[0])

                # Создаем конфиг из сохраненных данных
                config = MessageLimitConfig(
                    max_message_length=config_data.get('max_message_length', default_config.max_message_length),
                    max_context_messages=config_data.get('max_context_messages', default_config.max_context_messages),
                    max_context_length=config_data.get('max_context_length', default_config.max_context_length)
                )

                user_limit = UserMessageLimit(
                    user_id=user_id,
                    config=config,
                    total_messages_processed=result[1] or 0,
                    total_characters_processed=result[2] or 0,
                    average_message_length=result[3] or 0.0,
                    rejected_messages_count=result[4] or 0
                )

                return user_limit

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error loading message limit for user {user_id}: {e}")

        return None

    def delete_user_limit(self, user_id: int):
        """Удалить лимиты пользователя"""
        self.db.execute_query(
            'DELETE FROM user_message_limits WHERE user_id = ?',
            (user_id,)
        )