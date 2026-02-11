from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class ConversationSummary:
    id: Optional[int] = None
    user_id: int = None
    character_id: int = None
    level: int = 1  # 1=краткая суммаризация (диалог), 2=детальная суммаризация (сессия/отношения)
    content: str = None
    created_at: datetime = None
    updated_at: datetime = None
    deleted_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    @property
    def is_recent(self) -> bool:
        """Проверяет, актуальна ли суммаризация (младше 2 дней)"""
        return (datetime.utcnow() - self.updated_at).days < 2