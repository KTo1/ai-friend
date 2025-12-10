from typing import Dict
from datetime import datetime, timedelta
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger


class RateLimitTrackingRepository:
    """Репозиторий для трекинга rate limit (временные счетчики)"""

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger("rate_limit_tracking_repository")
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы трекинга"""
        try:
            self.db.execute_query('''
                CREATE TABLE IF NOT EXISTS user_rate_limit_tracking (
                    user_id BIGINT PRIMARY KEY,
                    minute_counter INTEGER DEFAULT 0,
                    hour_counter INTEGER DEFAULT 0,
                    day_counter INTEGER DEFAULT 0,
                    last_minute_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_hour_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_day_reset TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            self.db.execute_query('''
                CREATE INDEX IF NOT EXISTS idx_rate_tracking_user_id 
                ON user_rate_limit_tracking(user_id)
            ''')

            self.logger.info("Rate limit tracking table initialized")
        except Exception as e:
            self.logger.error(f"Error initializing rate limit tracking table: {e}")

    def get_counters(self, user_id: int) -> Dict[str, any]:
        """Получить текущие счетчики пользователя"""
        result = self.db.fetch_one(
            '''SELECT minute_counter, hour_counter, day_counter,
                      last_minute_reset, last_hour_reset, last_day_reset
               FROM user_rate_limit_tracking WHERE user_id = %s''',
            (user_id,)
        )

        if result:
            return {
                'minute_counter': result['minute_counter'] or 0,
                'hour_counter': result['hour_counter'] or 0,
                'day_counter': result['day_counter'] or 0,
                'last_minute_reset': self._parse_datetime(result['last_minute_reset']),
                'last_hour_reset': self._parse_datetime(result['last_hour_reset']),
                'last_day_reset': self._parse_datetime(result['last_day_reset'])
            }

        # Если запись не существует, создаем дефолтные значения
        now = datetime.utcnow()
        return {
            'minute_counter': 0,
            'hour_counter': 0,
            'day_counter': 0,
            'last_minute_reset': now,
            'last_hour_reset': now,
            'last_day_reset': now
        }

    def increment_counters(self, user_id: int):
        """Увеличить счетчики пользователя"""
        try:
            # Сначала проверяем и сбрасываем счетчики если нужно
            counters = self.get_counters(user_id)
            now = datetime.utcnow()

            # Проверяем нужно ли сбросить счетчики
            minute_reset = now - counters['last_minute_reset'] >= timedelta(minutes=1)
            hour_reset = now - counters['last_hour_reset'] >= timedelta(hours=1)
            day_reset = now - counters['last_day_reset'] >= timedelta(days=1)

            # Обновляем счетчики
            self.db.execute_query('''
                INSERT INTO user_rate_limit_tracking 
                (user_id, minute_counter, hour_counter, day_counter,
                 last_minute_reset, last_hour_reset, last_day_reset, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    minute_counter = CASE 
                        WHEN EXCLUDED.last_minute_reset > user_rate_limit_tracking.last_minute_reset + INTERVAL '1 minute'
                        THEN 1
                        ELSE user_rate_limit_tracking.minute_counter + 1
                    END,
                    hour_counter = CASE 
                        WHEN EXCLUDED.last_hour_reset > user_rate_limit_tracking.last_hour_reset + INTERVAL '1 hour'
                        THEN 1
                        ELSE user_rate_limit_tracking.hour_counter + 1
                    END,
                    day_counter = CASE 
                        WHEN EXCLUDED.last_day_reset > user_rate_limit_tracking.last_day_reset + INTERVAL '1 day'
                        THEN 1
                        ELSE user_rate_limit_tracking.day_counter + 1
                    END,
                    last_minute_reset = CASE 
                        WHEN EXCLUDED.last_minute_reset > user_rate_limit_tracking.last_minute_reset + INTERVAL '1 minute'
                        THEN EXCLUDED.last_minute_reset
                        ELSE user_rate_limit_tracking.last_minute_reset
                    END,
                    last_hour_reset = CASE 
                        WHEN EXCLUDED.last_hour_reset > user_rate_limit_tracking.last_hour_reset + INTERVAL '1 hour'
                        THEN EXCLUDED.last_hour_reset
                        ELSE user_rate_limit_tracking.last_hour_reset
                    END,
                    last_day_reset = CASE 
                        WHEN EXCLUDED.last_day_reset > user_rate_limit_tracking.last_day_reset + INTERVAL '1 day'
                        THEN EXCLUDED.last_day_reset
                        ELSE user_rate_limit_tracking.last_day_reset
                    END,
                    updated_at = EXCLUDED.updated_at
            ''', (
                user_id,
                1,  # minute_counter
                1,  # hour_counter
                1,  # day_counter
                now, now, now, now  # все reset времена и updated_at
            ))

        except Exception as e:
            self.logger.error(f"Error incrementing counters for user {user_id}: {e}")

    def reset_counters_if_needed(self, user_id: int):
        """Сбросить счетчики если период истек"""
        try:
            counters = self.get_counters(user_id)
            now = datetime.utcnow()

            # Проверяем каждый период
            minute_needs_reset = now - counters['last_minute_reset'] >= timedelta(minutes=1)
            hour_needs_reset = now - counters['last_hour_reset'] >= timedelta(hours=1)
            day_needs_reset = now - counters['last_day_reset'] >= timedelta(days=1)

            if minute_needs_reset or hour_needs_reset or day_needs_reset:
                self.db.execute_query('''
                    UPDATE user_rate_limit_tracking SET
                        minute_counter = CASE WHEN %s THEN 0 ELSE minute_counter END,
                        hour_counter = CASE WHEN %s THEN 0 ELSE hour_counter END,
                        day_counter = CASE WHEN %s THEN 0 ELSE day_counter END,
                        last_minute_reset = CASE WHEN %s THEN %s ELSE last_minute_reset END,
                        last_hour_reset = CASE WHEN %s THEN %s ELSE last_hour_reset END,
                        last_day_reset = CASE WHEN %s THEN %s ELSE last_day_reset END,
                        updated_at = %s
                    WHERE user_id = %s
                ''', (
                    minute_needs_reset, hour_needs_reset, day_needs_reset,
                    minute_needs_reset, now, hour_needs_reset, now, day_needs_reset, now,
                    now, user_id
                ))

        except Exception as e:
            self.logger.error(f"Error resetting counters for user {user_id}: {e}")

    def _parse_datetime(self, dt_value) -> datetime:
        """Парсинг datetime"""
        if dt_value is None:
            return datetime.utcnow()

        if isinstance(dt_value, datetime):
            return dt_value

        if isinstance(dt_value, str):
            try:
                return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
            except Exception:
                return datetime.utcnow()

        return datetime.utcnow()