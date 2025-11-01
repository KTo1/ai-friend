from dataclasses import dataclass
from datetime import datetime
from typing import List
from domain.value_objects.message import Message


@dataclass
class Conversation:
    user_id: int
    messages: List[Message]
    max_context_length: int = 15

    def add_message(self, role: str, content: str):
        message = Message(role=role, content=content, timestamp=datetime.now())
        self.messages.append(message)

        if len(self.messages) > self.max_context_length:
            self.messages = self.messages[-self.max_context_length:]

    def get_context(self, limit: int = 10) -> List[Message]:
        return list(reversed(self.messages[-limit:]))