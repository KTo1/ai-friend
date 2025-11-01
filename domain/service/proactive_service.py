from datetime import datetime, timedelta
from typing import List, Optional
from domain.entity.proactive_message import ProactiveMessage
from domain.entity.profile import UserProfile


class ProactiveService:

    @staticmethod
    def generate_proactive_messages(user_id: int, profile: Optional[UserProfile] = None,
                                    last_activity: Optional[datetime] = None) -> List[ProactiveMessage]:
        """Сгенерировать проактивные сообщения для пользователя"""
        messages = []
        now = datetime.now()

        # Если пользователь новый (нет профиля)
        if not profile or not profile.name:
            messages.append(ProactiveMessage(
                user_id=user_id,
                message_type='welcome_question',
                content="Привет! Я тут подумала... Как тебя лучше называть? И расскажи немного о себе - что тебе интересно? 😊",
                scheduled_time=now + timedelta(minutes=2)  # Через 2 минуты после старта
            ))

        # Если пользователь неактивен какое-то время
        elif last_activity and (now - last_activity) > timedelta(hours=6):
            name = profile.name or "друг"
            messages.append(ProactiveMessage(
                user_id=user_id,
                message_type='check_in',
                content=f"Привет, {name}! Как твои дела? Что интересного произошло с момента нашего последнего разговора? 🌟",
                scheduled_time=now + timedelta(minutes=1)
            ))

        # Регулярные проверки (только если пользователь активен)
        elif last_activity and (now - last_activity) < timedelta(hours=24):
            name = profile.name or "друг"

            # Утреннее сообщение (если утро)
            if 7 <= now.hour <= 10:
                messages.append(ProactiveMessage(
                    user_id=user_id,
                    message_type='morning_check',
                    content=f"Доброе утро, {name}! ☀️ Как ты сегодня проснулся? Какие планы на день?",
                    scheduled_time=now + timedelta(minutes=5)
                ))

            # Вечернее сообщение (если вечер)
            elif 19 <= now.hour <= 23:
                messages.append(ProactiveMessage(
                    user_id=user_id,
                    message_type='evening_check',
                    content=f"Привет, {name}! Как прошел твой день? Хочешь чем-нибудь поделиться? 🌙",
                    scheduled_time=now + timedimedelta(minutes=5)
                ))

            # Вопросы по интересам
            if profile.interests:
                messages.append(ProactiveMessage(
                    user_id=user_id,
                    message_type='interest_followup',
                    content=f"Помню, ты интересовался {profile.interests}. Как продвигается? Есть что-то новое? 🎯",
                    scheduled_time=now + timedelta(hours=2)
                ))

        # Общие вопросы для поддержания разговора
        general_questions = [
            "Как твое настроение сегодня? Хочешь об этом поговорить? 😊",
            "Чем занимаешься в последнее время? Нашел что-то интересное? 🎨",
            "Как ты себя чувствуешь? Все в порядке? 💭",
            "О чем ты думаешь в последнее время? Хочешь поделиться? 🌈"
        ]

        import random
        if random.random() < 0.3:  # 30% шанс добавить общий вопрос
            messages.append(ProactiveMessage(
                user_id=user_id,
                message_type='general_question',
                content=random.choice(general_questions),
                scheduled_time=now + timedelta(hours=1)
            ))

        return messages

    @staticmethod
    def should_send_proactive_message(last_activity: Optional[datetime]) -> bool:
        """Определить, стоит ли отправлять проактивное сообщение"""
        if not last_activity:
            return True

        time_since_last_activity = datetime.now() - last_activity
        return time_since_last_activity > timedelta(minutes=30)