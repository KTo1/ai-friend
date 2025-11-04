import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from domain.entity.proactive_message import UserActivity, ProactiveTrigger
from domain.entity.profile import UserProfile
from domain.service.proactive_generator import ProactiveMessageGenerator
from infrastructure.database.repositories.proactive_repository import ProactiveRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.monitoring.logging import StructuredLogger


class ProactiveMessageManager:
    def __init__(self,
                 proactive_repo: ProactiveRepository,
                 profile_repo: ProfileRepository,
                 conversation_repo: ConversationRepository,
                 ai_client,
                 telegram_bot_instance,
                 check_interval: int = 300):  # Проверка каждые 5 минут

        self.proactive_repo = proactive_repo
        self.profile_repo = profile_repo
        self.conversation_repo = conversation_repo
        self.generator = ProactiveMessageGenerator(ai_client)
        self.bot = telegram_bot_instance
        self.logger = StructuredLogger("proactive_manager")
        self.check_interval = check_interval

        # Хранилище активности пользователей
        self.user_activities: Dict[int, UserActivity] = {}

    async def start_monitoring(self):
        """Запустить мониторинг активности пользователей"""
        self.logger.info("Starting proactive messages monitoring (5min checks)")

        while True:
            try:
                await self._check_proactive_messages()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"❌ Error in proactive monitoring: {e}")
                await asyncio.sleep(60)

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

        self.logger.info(f"Updated activity for user {user_id}: {activity.message_count} messages")

    async def _check_proactive_messages(self):
        """Проверить и отправить проактивные сообщения"""
        current_time = datetime.utcnow()
        proactive_sent = False

        self.logger.info(f"Checking proactive messages for {len(self.user_activities)} users")

        for user_id, activity in list(self.user_activities.items()):
            try:
                # Логируем статистику для отладки
                time_since_last = current_time - activity.last_message_time
                last_proactive = activity.last_proactive_time or "Never"

                self.logger.info(
                    f"👤 User {user_id}: "
                    f"messages={activity.message_count}, "
                    f"last_activity={time_since_last.total_seconds() / 3600:.1f}h ago, "
                    f"last_proactive={last_proactive}"
                )

                # Проверяем триггеры в порядке приоритета
                triggers_to_check = [
                    ProactiveTrigger.MORNING_GREETING,
                    ProactiveTrigger.EVENING_CHECK,
                    ProactiveTrigger.INACTIVITY_REMINDER,
                    ProactiveTrigger.FOLLOW_UP
                ]

                for trigger in triggers_to_check:
                    if activity.should_send_proactive(trigger):
                        await self._send_proactive_message(user_id, activity, trigger)
                        proactive_sent = True
                        self.logger.info(f"✅ Sent {trigger.value} to user {user_id}")
                        break  # Отправляем только одно сообщение за проверку

            except Exception as e:
                self.logger.error(f"❌ Error checking proactive for user {user_id}: {e}")

        if not proactive_sent:
            self.logger.info("No proactive messages to send at this time")

    async def _send_proactive_message(self, user_id: int, activity: UserActivity, trigger: ProactiveTrigger):
        """Отправить проактивное сообщение в Telegram"""
        try:
            # Получаем профиль и контекст
            profile = self.profile_repo.get_profile(user_id)
            conversation_context = self.conversation_repo.get_conversation_context(user_id, limit=10)

            # Генерируем сообщение
            message = await self.generator.generate_proactive_message(
                user_id, profile, activity, trigger, conversation_context
            )

            if message and self.bot and self.bot.application:
                # ОТПРАВЛЯЕМ В TELEGRAM!
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message
                )

                # Обновляем время последнего проактивного сообщения
                activity.last_proactive_time = datetime.utcnow()

                # Сохраняем в базу
                self.proactive_repo.save_activity(activity)

                self.logger.info(f"📨 Telegram proactive message sent to {user_id}")
            else:
                self.logger.error("❌ Cannot send message: bot or application not available")

        except Exception as e:
            self.logger.error(f"❌ Error sending proactive message to user {user_id}: {e}")