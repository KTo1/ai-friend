from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional


@dataclass
class RateLimitConfig:
    """Конфигурация лимитов сообщений"""
    messages_per_minute: int = 2
    messages_per_hour: int = 15
    messages_per_day: int = 30

    @classmethod
    def from_env(cls) -> 'RateLimitConfig':
        """Создать конфигурацию из переменных окружения"""
        return cls(
            messages_per_minute=int(cls._get_env("RATE_LIMIT_PER_MINUTE", "2")),
            messages_per_hour=int(cls._get_env("RATE_LIMIT_PER_HOUR", "15")),
            messages_per_day=int(cls._get_env("RATE_LIMIT_PER_DAY", "30"))
        )

    @staticmethod
    def _get_env(key: str, default: str) -> str:
        import os
        return os.getenv(key, default)


@dataclass
class UserRateLimit:
    """Трекер лимитов для пользователя"""
    user_id: int
    message_counts: Dict[str, int]  # period -> count
    last_reset: Dict[str, datetime]  # period -> last reset time
    config: RateLimitConfig

    def __init__(self, user_id: int, config: RateLimitConfig):
        self.user_id = user_id
        self.config = config
        self.message_counts = {
            'minute': 0,
            'hour': 0,
            'day': 0
        }
        now = datetime.utcnow()
        self.last_reset = {
            'minute': now,
            'hour': now,
            'hour_start': now.replace(minute=0, second=0, microsecond=0),  # Начало текущего часа
            'day': now,
            'day_start': now.replace(hour=0, minute=0, second=0, microsecond=0)  # Начало текущего дня
        }

    def can_send_message(self) -> bool:
        """Проверить, может ли пользователь отправить сообщение"""
        self._reset_if_needed()

        return (self.message_counts['minute'] < self.config.messages_per_minute and
                self.message_counts['hour'] < self.config.messages_per_hour and
                self.message_counts['day'] < self.config.messages_per_day)

    def record_message(self):
        """Записать отправку сообщения"""
        self._reset_if_needed()

        for period in ['minute', 'hour', 'day']:
            self.message_counts[period] += 1

    def get_remaining_messages(self) -> Dict[str, int]:
        """Получить оставшееся количество сообщений по периодам"""
        self._reset_if_needed()

        return {
            'minute': max(0, self.config.messages_per_minute - self.message_counts['minute']),
            'hour': max(0, self.config.messages_per_hour - self.message_counts['hour']),
            'day': max(0, self.config.messages_per_day - self.message_counts['day'])
        }

    def get_time_until_reset(self, period: str) -> timedelta:
        """Получить время до сброса лимита"""
        now = datetime.utcnow()

        if period == 'minute':
            # Сброс в начале следующей минуты
            next_reset = (self.last_reset['minute'] + timedelta(minutes=1)).replace(second=0, microsecond=0)
        elif period == 'hour':
            # Сброс в начале следующего часа
            next_reset = self.last_reset['hour_start'] + timedelta(hours=1)
        elif period == 'day':
            # Сброс в начале следующего дня
            next_reset = self.last_reset['day_start'] + timedelta(days=1)
        else:
            return timedelta(0)

        return max(timedelta(0), next_reset - now)

    def _reset_if_needed(self):
        """Сбросить счетчики если период истек"""
        now = datetime.utcnow()

        # Сброс минутного лимита
        if now - self.last_reset['minute'] >= timedelta(minutes=1):
            self.message_counts['minute'] = 0
            self.last_reset['minute'] = now

        # Сброс часового лимита - в начале каждого часа
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        if current_hour_start > self.last_reset['hour_start']:
            self.message_counts['hour'] = 0
            self.last_reset['hour'] = now
            self.last_reset['hour_start'] = current_hour_start

        # Сброс дневного лимита - в начале каждого дня
        current_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if current_day_start > self.last_reset['day_start']:
            self.message_counts['day'] = 0
            self.last_reset['day'] = now
            self.last_reset['day_start'] = current_day_start