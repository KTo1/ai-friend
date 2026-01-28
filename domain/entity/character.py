from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class Character:
    id: int
    name: str
    description: str
    system_prompt: str
    avatar: bytes  # Изображение в формате bytes
    avatar_mime_type: str = "image/jpeg"
    avatar_file_id: Optional[str] = None
    is_active: bool = True
    display_order: int = 0
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

    def update_avatar_file_id(self, avatar_file_id: str):
        self.avatar_file_id = avatar_file_id
        self.updated_at = datetime.utcnow()