from typing import Dict, Optional, Tuple
from datetime import timedelta
from domain.entity.rate_limit import UserRateLimit, RateLimitConfig
from infrastructure.database.repositories.rate_limit_repository import RateLimitRepository
from infrastructure.monitoring.logging import StructuredLogger


class RateLimitService:
    """Сервис для управления лимитами сообщений"""

    def __init__(self, rate_limit_repo: RateLimitRepository):
        self.rate_limit_repo = rate_limit_repo
        self.default_config = RateLimitConfig.from_env()
        self.logger = StructuredLogger("rate_limit_service")

        # Кэш для активных пользователей
        self._rate_limits_cache: Dict[int, UserRateLimit] = {}

    def check_rate_limit(self, user_id: int) -> Tuple[bool, Optional[Dict]]:
        """
        Проверить лимиты для пользователя

        Returns:
            Tuple[bool, Optional[Dict]]: (может отправить, информация о лимитах)
        """
        rate_limit = self._get_or_create_rate_limit(user_id)

        if rate_limit.can_send_message():
            return True, None

        # Пользователь превысил лимит
        remaining = rate_limit.get_remaining_messages()
        limits_info = {
            'remaining': remaining,
            'time_until_reset': {
                'minute': rate_limit.get_time_until_reset('minute'),
                'hour': rate_limit.get_time_until_reset('hour'),
                'day': rate_limit.get_time_until_reset('day')
            },
            'config': {
                'minute': rate_limit.config.messages_per_minute,
                'hour': rate_limit.config.messages_per_hour,
                'day': rate_limit.config.messages_per_day
            }
        }

        self.logger.warning(
            f"Rate limit exceeded for user {user_id}",
            extra={
                'user_id': user_id,
                'remaining': remaining,
                'limits': limits_info['config']
            }
        )

        return False, limits_info

    def record_message(self, user_id: int):
        """Записать отправку сообщения пользователем"""
        rate_limit = self._get_or_create_rate_limit(user_id)
        rate_limit.record_message()
        self._save_rate_limit(rate_limit)

        self.logger.debug(
            f"Message recorded for user {user_id}",
            extra={
                'user_id': user_id,
                'current_counts': rate_limit.message_counts
            }
        )

    def get_user_limits_config(self, user_id: int) -> RateLimitConfig:
        """Получить конфигурацию лимитов пользователя"""
        rate_limit = self._get_or_create_rate_limit(user_id)
        return RateLimitConfig(
            messages_per_minute=rate_limit.config.messages_per_minute,
            messages_per_hour=rate_limit.config.messages_per_hour,
            messages_per_day=rate_limit.config.messages_per_day
        )

    def update_user_limits_config(self, user_id: int, **limits) -> bool:
        """Обновить конфигурацию лимитов пользователя"""
        rate_limit = self._get_or_create_rate_limit(user_id)

        for key, value in limits.items():
            if hasattr(rate_limit.config, key):
                setattr(rate_limit.config, key, value)

        self._save_rate_limit(rate_limit)
        return True

    def get_user_limits_info(self, user_id: int) -> Dict:
        """Получить информацию о лимитах пользователя"""
        rate_limit = self._get_or_create_rate_limit(user_id)

        return {
            'remaining': rate_limit.get_remaining_messages(),
            'current': rate_limit.message_counts,
            'limits': {
                'minute': rate_limit.config.messages_per_minute,
                'hour': rate_limit.config.messages_per_hour,
                'day': rate_limit.config.messages_per_day
            },
            'time_until_reset': {
                'minute': self._format_timedelta(rate_limit.get_time_until_reset('minute')),
                'hour': self._format_timedelta(rate_limit.get_time_until_reset('hour')),
                'day': self._format_timedelta(rate_limit.get_time_until_reset('day'))
            }
        }

    def reset_user_limits(self, user_id: int):
        """Сбросить лимиты пользователя"""
        if user_id in self._rate_limits_cache:
            del self._rate_limits_cache[user_id]

        self.rate_limit_repo.delete_rate_limit(user_id)
        self.logger.info(f"Rate limits reset for user {user_id}")

    def _get_or_create_rate_limit(self, user_id: int) -> UserRateLimit:
        """Получить или создать трекер лимитов для пользователя"""
        if user_id in self._rate_limits_cache:
            return self._rate_limits_cache[user_id]

        # Пытаемся загрузить из базы
        rate_limit = self.rate_limit_repo.get_rate_limit(user_id, self.default_config)

        if not rate_limit:
            # Создаем новый
            rate_limit = UserRateLimit(user_id, self.default_config)
            self._save_rate_limit(rate_limit)

        self._rate_limits_cache[user_id] = rate_limit
        return rate_limit

    def _save_rate_limit(self, rate_limit: UserRateLimit):
        """Сохранить лимиты пользователя"""
        try:
            self.rate_limit_repo.save_rate_limit(rate_limit)
        except Exception as e:
            self.logger.error(f"Error saving rate limit for user {rate_limit.user_id}: {e}")

    def _format_timedelta(self, td: timedelta) -> str:
        """Форматировать timedelta в читаемую строку"""
        if td.days > 0:
            return f"{td.days}д {td.seconds // 3600}ч"
        elif td.seconds >= 3600:
            hours = td.seconds // 3600
            minutes = (td.seconds % 3600) // 60
            return f"{hours}ч {minutes}м"
        elif td.seconds >= 60:
            minutes = td.seconds // 60
            seconds = td.seconds % 60
            return f"{minutes}м {seconds}с"
        else:
            return f"{td.seconds}с"