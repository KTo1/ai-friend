from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional


@dataclass
class ProactiveMessage:
    user_id: int
    message_type: str  # 'greeting', 'check_in', 'follow_up', 'interest_question'
    content: str
    scheduled_time: datetime
    is_sent: bool = False
    sent_time: Optional[datetime] = None

    def should_send(self) -> bool:
        """Проверить, нужно ли отправлять сообщение"""
        return (not self.is_sent and
                datetime.now() >= self.scheduled_time)

    def mark_sent(self):
        """Пометить как отправленное"""
        self.is_sent = True
        self.sent_time = datetime.now()