import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from domain.entity.proactive_message import UserActivity, ProactiveTrigger
from domain.entity.profile import UserProfile
from domain.service.message_limit_service import MessageLimitService
from domain.service.proactive_generator import ProactiveMessageGenerator
from infrastructure.database.repositories.proactive_repository import ProactiveRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.monitoring.logging import StructuredLogger
from config.settings import config


class ProactiveMessageManager:
    def __init__(self,
                 proactive_repo: ProactiveRepository,
                 profile_repo: ProfileRepository,
                 conversation_repo: ConversationRepository,
                 message_limit_service: MessageLimitService,
                 ai_client,
                 telegram_bot_instance,
                 check_interval: int = None):  # Можно передать кастомный интервал

        self.proactive_repo = proactive_repo
        self.profile_repo = profile_repo
        self.conversation_repo = conversation_repo
        self.generator = ProactiveMessageGenerator(ai_client)
        self.bot = telegram_bot_instance
        self.logger = StructuredLogger("proactive_manager")
        self.message_limit_service = message_limit_service

        # Используем интервал из конфига или переданный параметр
        self.check_interval = check_interval or config.proactive.check_interval

        # Хранилище активности пользователей
        self.user_activities: Dict[int, UserActivity] = {}

        # Защита от дублирования
        self.sent_today: Dict[int, datetime] = {}

    async def start_monitoring(self):
        """Запустить мониторинг активности пользователей"""
        self.logger.info(f"Starting proactive messages monitoring ({self.check_interval}s checks)")

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
            # Загружаем из базы, если есть
            stored_activity = self.proactive_repo.get_activity(user_id)
            if stored_activity:
                self.user_activities[user_id] = stored_activity
            else:
                self.user_activities[user_id] = UserActivity(
                    user_id=user_id,
                    last_message_time=now,
                    message_count=0
                )

        activity = self.user_activities[user_id]
        activity.last_message_time = now

        if message:
            activity.message_count += 1

        # Сохраняем в базу
        self.proactive_repo.save_activity(activity)

        self.logger.info(f"Updated activity for user {user_id}: {activity.message_count} messages")

    async def _check_proactive_messages(self):
        """Проверить и отправить проактивные сообщения"""
        current_time = datetime.utcnow()
        proactive_sent_count = 0

        # Очищаем кэш отправленных за вчерашний день
        self._cleanup_sent_cache(current_time)

        self.logger.info(f"Checking proactive messages for {len(self.user_activities)} users")

        for user_id, activity in list(self.user_activities.items()):
            try:
                # Пропускаем если уже отправили максимальное количество сегодня
                if self._has_reached_daily_limit(user_id, current_time):
                    continue

                # Проверяем минимальное количество сообщений для активации
                if activity.message_count < config.proactive.min_messages_for_activation:
                    self.logger.info(f"👤 User {user_id}: not enough messages ({activity.message_count})")
                    continue

                # Логируем статистику
                time_since_last = current_time - activity.last_message_time
                last_proactive = activity.last_proactive_time or "Never"

                self.logger.info(
                    f"👤 User {user_id}: "
                    f"messages={activity.message_count}, "
                    f"last_activity={time_since_last.total_seconds() / 3600:.1f}h ago, "
                    f"last_proactive={last_proactive}"
                )

                # Проверяем триггеры
                triggers_to_check = [
                    ProactiveTrigger.MORNING_GREETING,
                    ProactiveTrigger.EVENING_CHECK,
                    ProactiveTrigger.INACTIVITY_REMINDER,
                    ProactiveTrigger.FOLLOW_UP
                ]

                for trigger in triggers_to_check:
                    if activity.should_send_proactive(trigger):
                        success = await self._send_proactive_message(user_id, activity, trigger)
                        if success:
                            proactive_sent_count += 1
                            self.sent_today[user_id] = current_time
                            self.logger.info(f"Sent {trigger.value} to user {user_id}")
                        break

            except Exception as e:
                self.logger.error(f"Error checking proactive for user {user_id}: {e}")

        if proactive_sent_count > 0:
            self.logger.info(f"Sent {proactive_sent_count} proactive messages")
        else:
            self.logger.info("No proactive messages to send at this time")

    async def _send_proactive_message(self, user_id: int, activity: UserActivity, trigger: ProactiveTrigger) -> bool:
        """Отправить проактивное сообщение в Telegram"""
        try:
            message_limits = self.message_limit_service.get_user_limits(user_id)

            # Получаем профиль и контекст
            profile = self.profile_repo.get_profile(user_id)
            conversation_context = self.conversation_repo.get_conversation_context(user_id,
                                                                                   message_limits.config.max_context_messages)

            # Генерируем сообщение
            message = await self.generator.generate_proactive_message(
                user_id, profile, activity, trigger, conversation_context
            )

            if message and hasattr(self.bot, '_safe_send_message'):
                # Используем безопасный метод отправки через TelegramMessageSender
                success = await self.bot._safe_send_message(
                    chat_id=user_id,
                    text=message
                )

                if success:
                    # Обновляем время последнего проактивного сообщения
                    activity.last_proactive_time = datetime.utcnow()

                    # Сохраняем в базу
                    self.proactive_repo.save_activity(activity)

                    self.logger.info(f"📨 Telegram proactive message sent to {user_id}")
                    return True
                else:
                    self.logger.error(f"Failed to send proactive message to {user_id}")
                    return False
            else:
                self.logger.error("❌ Cannot send message: bot or safe_send_message method not available")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error sending proactive message to user {user_id}: {e}")
            return False

    def _has_reached_daily_limit(self, user_id: int, current_time: datetime) -> bool:
        """Проверить, достигнут ли дневной лимит сообщений для пользователя"""
        if user_id not in self.sent_today:
            return False

        sent_count_today = 0
        for uid, sent_time in self.sent_today.items():
            if uid == user_id and sent_time.date() == current_time.date():
                sent_count_today += 1

        return sent_count_today >= config.proactive.max_messages_per_day

    def _cleanup_sent_cache(self, current_time: datetime):
        """Очистить кэш отправленных сообщений от вчерашних записей"""
        users_to_remove = []
        for user_id, sent_time in self.sent_today.items():
            if sent_time.date() < current_time.date():
                users_to_remove.append(user_id)

        for user_id in users_to_remove:
            del self.sent_today[user_id]

        if users_to_remove:
            self.logger.info(f"🧹 Cleaned {len(users_to_remove)} old entries from sent cache")