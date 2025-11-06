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

    def promote_to_admin(self):
        """Назначить пользователя администратором"""
        self.is_admin = True

    def demote_from_admin(self):
        """Убрать права администратора"""
        self.is_admin = False