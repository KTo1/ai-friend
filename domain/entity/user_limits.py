from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RateLimitConfig:
    """Конфигурация рейт-лимитов"""
    messages_per_minute: int = 10
    messages_per_hour: int = 100
    messages_per_day: int = 500


@dataclass
class MessageLimitConfig:
    """Конфигурация лимитов сообщений"""
    max_message_length: int = 2000
    max_context_messages: int = 10
    max_context_length: int = 4000


@dataclass
class UserLimits:
    """Все лимиты пользователя в одном месте"""
    user_id: int
    rate_limits: RateLimitConfig
    message_limits: MessageLimitConfig

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь для отображения"""
        return {
            'user_id': self.user_id,
            'rate_limits': {
                'messages_per_minute': self.rate_limits.messages_per_minute,
                'messages_per_hour': self.rate_limits.messages_per_hour,
                'messages_per_day': self.rate_limits.messages_per_day
            },
            'message_limits': {
                'max_message_length': self.message_limits.max_message_length,
                'max_context_messages': self.message_limits.max_context_messages,
                'max_context_length': self.message_limits.max_context_length
            }
        }

    @classmethod
    def create_default(cls, user_id: int) -> 'UserLimits':
        """Создать лимиты по умолчанию"""
        return cls(
            user_id=user_id,
            rate_limits=RateLimitConfig(),
            message_limits=MessageLimitConfig()
        )