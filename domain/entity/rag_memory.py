from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class MemoryType(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    PERSONAL_DETAIL = "personal_detail"
    PERSONAL_CHARACTERISTIC = "personal_characteristic"
    INTEREST = "interest"
    MOOD = "mood"
    AGE = "age"
    HABIT = "habit"
    GOAL = "goal"


@dataclass
class RAGMemory:
    """Сущность для хранения важных фактов о пользователе"""
    id: Optional[int] = None
    user_id: int = None
    memory_type: MemoryType = MemoryType.FACT
    content: str = None
    source_message: str = None
    importance_score: float = 0.5  # 0-1, где 1 - максимальная важность
    embedding: Optional[List[float]] = None
    created_at: datetime = None
    updated_at: datetime = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'memory_type': self.memory_type.value,
            'content': self.content,
            'source_message': self.source_message,
            'importance_score': self.importance_score,
            'embedding': self.embedding,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RAGMemory':
        return cls(
            id=data.get('id'),
            user_id=data['user_id'],
            memory_type=MemoryType(data['memory_type']),
            content=data['content'],
            source_message=data['source_message'],
            importance_score=data['importance_score'],
            embedding=data.get('embedding'),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            metadata=data.get('metadata', {})
        )