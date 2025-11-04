from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
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
        last_proactive = self.last_proactive_time or datetime.fromtimestamp(0)

        print(f"🔍 Checking {trigger.value}: last_proactive={last_proactive}, now={now}")

        if trigger == ProactiveTrigger.MORNING_GREETING:
            # Утро: 7-10 утра по местному времени, не отправляли сегодня
            is_morning = 7 <= now.hour <= 10
            not_sent_today = last_proactive.date() < now.date()
            has_conversation = self.message_count >= 3  # Было активное общение
            return is_morning and not_sent_today and has_conversation

        elif trigger == ProactiveTrigger.EVENING_CHECK:
            # Вечер: 19-23 вечера по местному времени, не отправляли сегодня
            is_evening = 19 <= now.hour <= 23
            not_sent_today = last_proactive.date() < now.date()
            has_conversation = self.message_count >= 3  # Было активное общение
            return is_evening and not_sent_today and has_conversation

        elif trigger == ProactiveTrigger.INACTIVITY_REMINDER:
            # Напоминание после 6 часов неактивности
            time_since_last = now - self.last_message_time
            time_since_last_proactive = now - last_proactive
            has_conversation = self.message_count >= 4  # Активный разговор
            return (time_since_last > timedelta(hours=6) and
                    time_since_last_proactive > timedelta(hours=12) and
                    has_conversation)

        elif trigger == ProactiveTrigger.FOLLOW_UP:
            # Follow-up через 2 часа после активного разговора
            time_since_last = now - self.last_message_time
            time_since_last_proactive = now - last_proactive
            has_conversation = self.message_count >= 4  # Активный разговор
            return (time_since_last > timedelta(hours=2) and
                    time_since_last_proactive > timedelta(hours=6) and
                    has_conversation)

        return False