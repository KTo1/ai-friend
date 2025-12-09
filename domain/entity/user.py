from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    is_admin: bool = False
    is_blocked: bool = False
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    blocked_by: Optional[int] = None
    created_at: datetime = None
    last_seen: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_seen is None:
            self.last_seen = datetime.now()

    def update_last_seen(self):
        """Обновить время последней активности"""
        self.last_seen = datetime.now()

    def block_user(self, blocked_by: int, reason: Optional[str] = None):
        """Заблокировать пользователя"""
        self.is_blocked = True
        self.blocked_reason = reason
        self.blocked_at = datetime.now()
        self.blocked_by = blocked_by

    def unblock_user(self):
        """Разблокировать пользователя"""
        self.is_blocked = False
        self.blocked_reason = None
        self.blocked_at = None
        self.blocked_by = None