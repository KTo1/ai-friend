import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from domain.entity.proactive_message import UserActivity, ProactiveTrigger
from domain.entity.profile import UserProfile
from domain.service.proactive_generator import ProactiveMessageGenerator
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.monitoring.logging import StructuredLogger


class ProactiveMessageManager:
    def __init__(self,
                 profile_repo: ProfileRepository,
                 conversation_repo: ConversationRepository,
                 ai_client,
                 check_interval: int = 300):  # Проверка каждые 5 минут

        self.profile_repo = profile_repo
        self.conversation_repo = conversation_repo
        self.generator = ProactiveMessageGenerator(ai_client)
        self.logger = StructuredLogger("proactive_manager")
        self.check_interval = check_interval

        # Хранилище активности пользователей
        self.user_activities: Dict[int, UserActivity] = {}

    async def start_monitoring(self):
        """Запустить мониторинг активности пользователей"""
        self.logger.info("Starting proactive messages monitoring")

        while True:
            try:
                await self._check_proactive_messages()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Error in proactive monitoring: {e}")
                await asyncio.sleep(60)  # Подождать минуту при ошибке

    def update_user_activity(self, user_id: int, message: str = None):
        """Обновить активность пользователя"""
        now = datetime.utcnow()

        if user_id not in self.user_activities:
            self.user_activities[user_id] = UserActivity(
                user_id=user_id,
                last_message_time=now,
                message_count=0
            )

        activity = self.user_activities[user_id]
        activity.last_message_time = now

        if message:
            activity.message_count += 1

    async def _check_proactive_messages(self):
        """Проверить и отправить проактивные сообщения"""
        current_time = datetime.utcnow()

        for user_id, activity in list(self.user_activities.items()):
            try:
                # Проверяем разные триггеры
                triggers_to_check = [
                    ProactiveTrigger.MORNING_GREETING,
                    ProactiveTrigger.EVENING_CHECK,
                    ProactiveTrigger.INACTIVITY_REMINDER,
                    ProactiveTrigger.FOLLOW_UP
                ]

                for trigger in triggers_to_check:
                    if activity.should_send_proactive(trigger):
                        await self._send_proactive_message(user_id, activity, trigger)
                        break  # Отправляем только одно сообщение за проверку

            except Exception as e:
                self.logger.error(f"Error checking proactive for user {user_id}: {e}")

    async def _send_proactive_message(self, user_id: int, activity: UserActivity, trigger: ProactiveTrigger):
        """Отправить проактивное сообщение"""
        try:
            # Получаем профиль и контекст
            profile = self.profile_repo.get_profile(user_id)
            conversation_context = self.conversation_repo.get_conversation_context(user_id, limit=10)

            # Генерируем сообщение через LLM
            message = await self.generator.generate_proactive_message(
                user_id, profile, activity, trigger, conversation_context
            )

            if message:
                # Здесь будет логика отправки через Telegram
                # Пока просто логируем
                self.logger.info(
                    f"📨 Proactive message ready for user {user_id}",
                    extra={
                        'user_id': user_id,
                        'trigger': trigger.value,
                        'message': message[:100] + '...' if len(message) > 100 else message
                    }
                )

                # Обновляем время последнего проактивного сообщения
                activity.last_proactive_time = datetime.utcnow()

        except Exception as e:
            self.logger.error(f"Error sending proactive message to user {user_id}: {e}")