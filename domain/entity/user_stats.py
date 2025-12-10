from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class UserStats:
    """Статистика использования пользователя"""
    user_id: int
    total_messages_processed: int = 0
    total_characters_processed: int = 0
    total_messages_rejected: int = 0  # Отклонено из-за длины
    total_rate_limit_hits: int = 0  # Попаданий в rate limit
    average_message_length: float = 0.0
    last_message_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
        if self.last_message_at is None:
            self.last_message_at = datetime.utcnow()

    def record_message(self, message_length: int, was_rejected: bool = False, was_rate_limited: bool = False):
        """Записать обработку сообщения"""
        if not was_rejected:
            self.total_messages_processed += 1
            self.total_characters_processed += message_length
            self.average_message_length = self.total_characters_processed / self.total_messages_processed
        else:
            self.total_messages_rejected += 1

        if was_rate_limited:
            self.total_rate_limit_hits += 1

        self.last_message_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь"""
        return {
            'user_id': self.user_id,
            'total_messages_processed': self.total_messages_processed,
            'total_characters_processed': self.total_characters_processed,
            'total_messages_rejected': self.total_messages_rejected,
            'total_rate_limit_hits': self.total_rate_limit_hits,
            'average_message_length': round(self.average_message_length, 2),
            'last_message_at': self.last_message_at.isoformat() if self.last_message_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }