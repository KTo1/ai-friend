from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum


class ProactiveTrigger(Enum):
    MORNING_GREETING = "morning_greeting"
    EVENING_CHECK = "evening_check"
    INACTIVITY_REMINDER = "inactivity_reminder"
    FOLLOW_UP = "follow_up"
    WEEKLY_CHECKIN = "weekly_checkin"


@dataclass
class UserActivity:
    user_id: int
    last_message_time: datetime
    last_proactive_time: Optional[datetime] = None
    message_count: int = 0
    timezone_offset: int = 0  # Смещение часового пояса в часах

    def get_local_time(self) -> datetime:
        """Получить локальное время пользователя"""
        return datetime.utcnow() + timedelta(hours=self.timezone_offset)

    def should_send_proactive(self, trigger: ProactiveTrigger) -> bool:
        """Определить, нужно ли отправлять проактивное сообщение"""
        now = self.get_local_time()

        if trigger == ProactiveTrigger.MORNING_GREETING:
            # Утро: 7-10 утра по местному времени
            return (7 <= now.hour <= 10 and
                    (self.last_proactive_time is None or
                     self.last_proactive_time.date() < now.date()))

        elif trigger == ProactiveTrigger.EVENING_CHECK:
            # Вечер: 19-23 вечера по местному времени
            return (19 <= now.hour <= 23 and
                    (self.last_proactive_time is None or
                     self.last_proactive_time.date() < now.date()))

        elif trigger == ProactiveTrigger.INACTIVITY_REMINDER:
            # Напоминание после 24 часов неактивности
            time_since_last = now - self.last_message_time
            return (time_since_last > timedelta(hours=24) and
                    (self.last_proactive_time is None or
                     now - self.last_proactive_time > timedelta(hours=12)))

        elif trigger == ProactiveTrigger.FOLLOW_UP:
            # Follow-up через 2 часа после активного разговора
            time_since_last = now - self.last_message_time
            return (time_since_last > timedelta(hours=2) and
                    self.message_count > 3 and
                    (self.last_proactive_time is None or
                     now - self.last_proactive_time > timedelta(hours=6)))

        return False