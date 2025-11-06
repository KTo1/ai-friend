# domain/entity/user.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class UserLimits:
    """Лимиты пользователя"""
    max_daily_requests: int = 50
    max_message_length: int = 500
    max_context_messages: int = 5
    max_tokens_per_request: int = 1200
    custom_limits_enabled: bool = False

    # 🔧 НОВЫЕ RATE LIMITS
    messages_per_minute: int = 10    # Максимум 10 сообщений в минуту
    messages_per_hour: int = 100     # Максимум 100 сообщений в час

    # 🔧 СЧЕТЧИКИ RATE LIMITS (технические поля)
    minute_window_start: datetime = None
    minute_count: int = 0
    hour_window_start: datetime = None
    hour_count: int = 0
    updated_at: datetime = None

    def __post_init__(self):
        """Инициализация временных меток если они None"""
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.minute_window_start is None:
            self.minute_window_start = datetime.now()
        if self.hour_window_start is None:
            self.hour_window_start = datetime.now()

@dataclass
class User:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    created_at: datetime = None
    is_active: bool = True
    is_banned: bool = False
    limits: UserLimits = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.limits is None:
            self.limits = UserLimits()

    def can_make_request(self, current_usage: int) -> bool:
        """Может ли пользователь сделать запрос"""
        if self.is_banned or not self.is_active:
            return False
        return current_usage < self.limits.max_daily_requests

    def get_remaining_requests(self, current_usage: int) -> int:
        """Оставшееся количество запросов"""
        return max(0, self.limits.max_daily_requests - current_usage)