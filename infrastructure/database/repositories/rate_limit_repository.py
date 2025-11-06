import json
from typing import Dict, Optional
from datetime import datetime
from domain.entity.rate_limit import UserRateLimit, RateLimitConfig
from infrastructure.database.database import Database


class RateLimitRepository:
    """Репозиторий для хранения лимитов пользователей"""

    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы лимитов"""
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS user_rate_limits (
                user_id INTEGER PRIMARY KEY,
                message_counts TEXT NOT NULL,
                last_reset TEXT NOT NULL,
                config TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def save_rate_limit(self, rate_limit: UserRateLimit):
        """Сохранить лимиты пользователя"""
        data = {
            'message_counts': rate_limit.message_counts,
            'last_reset': {
                'minute': rate_limit.last_reset['minute'].isoformat(),
                'hour': rate_limit.last_reset['hour'].isoformat(),
                'day': rate_limit.last_reset['day'].isoformat()
            },
            'config': {
                'messages_per_minute': rate_limit.config.messages_per_minute,
                'messages_per_hour': rate_limit.config.messages_per_hour,
                'messages_per_day': rate_limit.config.messages_per_day
            }
        }

        self.db.execute_query('''
            INSERT OR REPLACE INTO user_rate_limits 
            (user_id, message_counts, last_reset, config, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            rate_limit.user_id,
            json.dumps(data['message_counts']),
            json.dumps(data['last_reset']),
            json.dumps(data['config']),
            datetime.utcnow()
        ))

    def get_rate_limit(self, user_id: int, default_config: RateLimitConfig) -> Optional[UserRateLimit]:
        """Получить лимиты пользователя"""
        result = self.db.fetch_one(
            'SELECT message_counts, last_reset, config FROM user_rate_limits WHERE user_id = ?',
            (user_id,)
        )

        if result:
            try:
                message_counts = json.loads(result[0])
                last_reset_data = json.loads(result[1])
                config_data = json.loads(result[2])

                # Создаем конфиг из сохраненных данных или используем дефолтный
                config = RateLimitConfig(
                    messages_per_minute=config_data.get('messages_per_minute', default_config.messages_per_minute),
                    messages_per_hour=config_data.get('messages_per_hour', default_config.messages_per_hour),
                    messages_per_day=config_data.get('messages_per_day', default_config.messages_per_day)
                )

                rate_limit = UserRateLimit(user_id, config)
                rate_limit.message_counts = message_counts

                # Восстанавливаем даты
                for period in ['minute', 'hour', 'day']:
                    if period in last_reset_data:
                        rate_limit.last_reset[period] = datetime.fromisoformat(last_reset_data[period])

                return rate_limit

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error loading rate limit for user {user_id}: {e}")

        return None

    def delete_rate_limit(self, user_id: int):
        """Удалить лимиты пользователя"""
        self.db.execute_query(
            'DELETE FROM user_rate_limits WHERE user_id = ?',
            (user_id,)
        )