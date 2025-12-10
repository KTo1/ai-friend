from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class RateLimitConfig:
    """Конфигурация рейт-лимитов для тарифа"""
    messages_per_minute: int = 2
    messages_per_hour: int = 15
    messages_per_day: int = 30


@dataclass
class MessageLimitConfig:
    """Конфигурация лимитов сообщений для тарифа"""
    max_message_length: int = 2000
    max_context_messages: int = 10
    max_context_length: int = 4000


@dataclass
class TariffPlan:
    """Тарифный план со всеми лимитами"""
    # Обязательные аргументы
    id: int
    name: str
    description: str
    price: float  # Цена в рублях/месяц
    rate_limits: RateLimitConfig
    message_limits: MessageLimitConfig

    # Аргументы со значениями по умолчанию
    is_active: bool = True
    is_default: bool = False
    features: Dict[str, Any] = None
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.features is None:
            self.features = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def is_rag_enabled(self) -> bool:
        """Проверить, доступен ли RAG для этого тарифа"""
        # RAG доступен для всех тарифов кроме бесплатного
        return self.name != 'Бесплатный' and self.is_active

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь для отображения"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'is_active': self.is_active,
            'is_default': self.is_default,
            'rate_limits': {
                'messages_per_minute': self.rate_limits.messages_per_minute,
                'messages_per_hour': self.rate_limits.messages_per_hour,
                'messages_per_day': self.rate_limits.messages_per_day
            },
            'message_limits': {
                'max_message_length': self.message_limits.max_message_length,
                'max_context_messages': self.message_limits.max_context_messages,
                'max_context_length': self.message_limits.max_context_length
            },
            'features': self.features,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'rag_enabled': self.is_rag_enabled(),
        }


@dataclass
class UserTariff:
    """Тарифный план пользователя"""
    # Обязательные аргументы
    user_id: int
    tariff_plan_id: int

    # Аргументы со значениями по умолчанию
    tariff_plan: Optional[TariffPlan] = None
    activated_at: datetime = None
    expires_at: Optional[datetime] = None
    is_active: bool = True

    def __post_init__(self):
        if self.activated_at is None:
            self.activated_at = datetime.utcnow()

    def is_expired(self) -> bool:
        """Проверить истек ли тариф"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def days_remaining(self) -> Optional[int]:
        """Осталось дней до истечения тарифа"""
        if self.expires_at is None:
            return None
        remaining = self.expires_at - datetime.utcnow()
        return max(0, remaining.days)