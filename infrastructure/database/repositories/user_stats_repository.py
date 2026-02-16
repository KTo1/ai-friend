from typing import Optional
from datetime import datetime
from domain.entity.user_stats import UserStats
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.monitoring.metrics import metrics_collector


class UserStatsRepository:
    """Репозиторий для хранения статистики пользователей"""

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger("user_stats_repository")
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы статистики"""
        try:
            self.db.execute_query('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id BIGINT PRIMARY KEY,
                    total_messages_processed INTEGER DEFAULT 0,
                    total_characters_processed INTEGER DEFAULT 0,
                    total_messages_rejected INTEGER DEFAULT 0,
                    total_rate_limit_hits INTEGER DEFAULT 0,
                    average_message_length FLOAT DEFAULT 0.0,
                    paywall_reached BOOLEAN DEFAULT FALSE,
                    paywall_reached_at TIMESTAMP,                    
                    last_message_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            self.logger.info("User stats table initialized")
        except Exception as e:
            self.logger.error(f"Error initializing user stats table: {e}")

    def get_user_stats(self, user_id: int) -> Optional[UserStats]:
        """Получить статистику пользователя"""
        result = self.db.fetch_one(
            '''SELECT user_id, total_messages_processed, total_characters_processed,
                      total_messages_rejected, total_rate_limit_hits, average_message_length,
                      paywall_reached, paywall_reached_at, last_message_at, created_at, updated_at
               FROM user_stats WHERE user_id = %s''',
            (user_id,)
        )

        if result:
            return UserStats(
                user_id=result['user_id'],
                total_messages_processed=result['total_messages_processed'] or 0,
                total_characters_processed=result['total_characters_processed'] or 0,
                total_messages_rejected=result['total_messages_rejected'] or 0,
                total_rate_limit_hits=result['total_rate_limit_hits'] or 0,
                average_message_length=result['average_message_length'] or 0.0,
                paywall_reached=bool(result['paywall_reached']),
                paywall_reached_at=self._parse_datetime(result['paywall_reached_at']),
                last_message_at=self._parse_datetime(result['last_message_at']),
                created_at=self._parse_datetime(result['created_at']),
                updated_at=self._parse_datetime(result['updated_at'])
            )
        return None

    def save_user_stats(self, stats: UserStats):
        """Сохранить статистику пользователя"""
        try:
            self.db.execute_query('''
                INSERT INTO user_stats 
                (user_id, total_messages_processed, total_characters_processed,
                 total_messages_rejected, total_rate_limit_hits, average_message_length,
                 paywall_reached, paywall_reached_at,
                 last_message_at, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    total_messages_processed = EXCLUDED.total_messages_processed,
                    total_characters_processed = EXCLUDED.total_characters_processed,
                    total_messages_rejected = EXCLUDED.total_messages_rejected,
                    total_rate_limit_hits = EXCLUDED.total_rate_limit_hits,
                    average_message_length = EXCLUDED.average_message_length,
                    paywall_reached = EXCLUDED.paywall_reached,
                    paywall_reached_at = EXCLUDED.paywall_reached_at,
                    last_message_at = EXCLUDED.last_message_at,
                    updated_at = EXCLUDED.updated_at
            ''', (
                stats.user_id,
                stats.total_messages_processed,
                stats.total_characters_processed,
                stats.total_messages_rejected,
                stats.total_rate_limit_hits,
                stats.average_message_length,
                stats.paywall_reached,
                stats.paywall_reached_at,
                stats.last_message_at,
                stats.created_at,
                stats.updated_at
            ))
        except Exception as e:
            self.logger.error(f"Error saving user stats for {stats.user_id}: {e}")

    def check_and_mark_paywall(self, user_id: int, character_id: int ) -> bool:
        """Если пользователь достиг paywall и ещё не отмечен, отмечает и возвращает True."""
        stats = self.get_user_stats(user_id)
        if stats is None:
            stats = UserStats(user_id=user_id)
        if not stats.paywall_reached:
            stats.record_paywall_reached()
            self.save_user_stats(stats)
            self.logger.info(f'Marked paywall reached for user {user_id}')

            # Записываем детальную метрику для аналитики
            metrics_collector.record_user_reached_paywall(
                user_id=user_id,
                character_id=character_id
            )

            return True

        return False

    def mark_paywall_reached(self, stats: UserStats) -> bool:
        try:
            stats.record_paywall_reached()
            self.save_user_stats(stats)
            self.logger.info(f'Marked paywall reached for user {stats.user_id}')
            return True
        except Exception as e:
            self.logger.error(f'Error marking paywall reached for user {stats.user_id}: {e}')
            return False

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