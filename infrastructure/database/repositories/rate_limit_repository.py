import json
from typing import Optional
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
        # Таблица уже создана в PostgreSQL инициализации
        pass

    def save_rate_limit(self, rate_limit: UserRateLimit):
        """Сохранить лимиты пользователя"""
        data = {
            'message_counts': rate_limit.message_counts,
            'last_reset': {
                'minute': rate_limit.last_reset['minute'].isoformat(),
                'hour': rate_limit.last_reset['hour'].isoformat(),
                'hour_start': rate_limit.last_reset['hour_start'].isoformat(),
                'day': rate_limit.last_reset['day'].isoformat(),
                'day_start': rate_limit.last_reset['day_start'].isoformat()
            },
            'config': {
                'messages_per_minute': rate_limit.config.messages_per_minute,
                'messages_per_hour': rate_limit.config.messages_per_hour,
                'messages_per_day': rate_limit.config.messages_per_day
            }
        }

        self.db.execute_query('''
            INSERT INTO user_rate_limits 
            (user_id, message_counts, last_reset, config, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                message_counts = EXCLUDED.message_counts,
                last_reset = EXCLUDED.last_reset,
                config = EXCLUDED.config,
                updated_at = EXCLUDED.updated_at
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
            'SELECT message_counts, last_reset, config FROM user_rate_limits WHERE user_id = %s',
            (user_id,)
        )

        if result:
            try:
                # В PostgreSQL с JSONB поля уже являются словарями Python
                message_counts = result["message_counts"]
                last_reset_data = result["last_reset"]
                config_data = result["config"]

                # Если данные пришли как строки (старая версия), парсим JSON
                if isinstance(message_counts, str):
                    message_counts = json.loads(message_counts)
                if isinstance(last_reset_data, str):
                    last_reset_data = json.loads(last_reset_data)
                if isinstance(config_data, str):
                    config_data = json.loads(config_data)

                # Создаем конфиг из сохраненных данных или используем дефолтный
                config = RateLimitConfig(
                    messages_per_minute=config_data.get('messages_per_minute', default_config.messages_per_minute),
                    messages_per_hour=config_data.get('messages_per_hour', default_config.messages_per_hour),
                    messages_per_day=config_data.get('messages_per_day', default_config.messages_per_day)
                )

                rate_limit = UserRateLimit(user_id, config)
                rate_limit.message_counts = message_counts

                # Восстанавливаем даты с безопасным парсингом
                for key in ['minute', 'hour', 'hour_start', 'day', 'day_start']:
                    if key in last_reset_data:
                        rate_limit.last_reset[key] = self._parse_datetime(last_reset_data[key])

                return rate_limit

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error loading rate limit for user {user_id}: {e}")

        return None

    def delete_rate_limit(self, user_id: int):
        """Удалить лимиты пользователя"""
        self.db.execute_query(
            'DELETE FROM user_rate_limits WHERE user_id = %s',
            (user_id,)
        )

    def _parse_datetime(self, dt_value) -> datetime:
        """Парсинг datetime из различных форматов"""
        if dt_value is None:
            return datetime.utcnow()

        if isinstance(dt_value, datetime):
            return dt_value

        if isinstance(dt_value, str):
            try:
                # PostgreSQL возвращает datetime в формате ISO
                return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
            except Exception:
                return datetime.utcnow()

        return datetime.utcnow()