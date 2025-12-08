import asyncio
import random
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
    """
    Улучшенный менеджер проактивных сообщений.
    """

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

        # Защита от дублирования: теперь хранит список времен отправок (per-day) и последние тексты
        self.sent_today: Dict[int, List[datetime]] = {}
        self.last_sent_texts: Dict[int, List[str]] = {}

        # Максимум последних текстов для хранения
        self._LAST_TEXTS_KEEP = 5

    async def start_monitoring(self):
        """Запустить мониторинг активности пользователей (асинхронно)"""
        self.logger.info(f"Starting proactive messages monitoring ({self.check_interval}s checks)")

        while True:
            try:
                await self._check_proactive_messages()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"❌ Error in proactive monitoring: {e}")
                await asyncio.sleep(60)  # Подождать минуту при ошибке

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

        self.logger.debug(f"Updated activity for user {user_id}: {activity.message_count} messages")

    async def _check_proactive_messages(self):
        """Проверить и отправить проактивные сообщения"""
        current_time = datetime.utcnow()
        proactive_sent_count = 0

        # Очищаем кэш отправленных за вчерашний день
        self._cleanup_sent_cache(current_time)

        self.logger.debug(f"Checking proactive messages for {len(self.user_activities)} users")

        # Создаем список задач для параллельной обработки
        tasks = []
        for user_id, activity in list(self.user_activities.items()):
            # Пропускаем если уже отправили максимальное количество сегодня
            if self._has_reached_daily_limit(user_id, current_time):
                self.logger.debug(f"User {user_id}: reached daily limit")
                continue

            # Проверяем минимальное количество сообщений для активации
            if activity.message_count < config.proactive.min_messages_for_activation:
                self.logger.debug(f"User {user_id}: not enough messages ({activity.message_count})")
                continue

            # Проверяем триггеры
            trigger = self._get_trigger_for_user(activity, current_time)
            if trigger:
                # Создаем задачу для отправки сообщения
                task = self._create_proactive_task(user_id, activity, trigger, current_time)
                tasks.append(task)

        # Ограничиваем количество одновременных задач
        max_concurrent_tasks = 5  # Можно вынести в конфиг
        if tasks:
            # Разбиваем задачи на группы для параллельной обработки
            for i in range(0, len(tasks), max_concurrent_tasks):
                batch = tasks[i:i + max_concurrent_tasks]
                results = await asyncio.gather(*batch, return_exceptions=True)

                # Обрабатываем результаты
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.error(f"Error in proactive task: {result}")
                    elif result:
                        proactive_sent_count += 1

        if proactive_sent_count > 0:
            self.logger.info(f"Sent {proactive_sent_count} proactive messages")
        else:
            self.logger.debug("No proactive messages to send at this time")

    def _get_trigger_for_user(self, activity: UserActivity, current_time: datetime) -> Optional[ProactiveTrigger]:
        """Получить триггер для пользователя"""
        triggers_to_check = [
            ProactiveTrigger.MORNING_GREETING,
            ProactiveTrigger.EVENING_CHECK,
            ProactiveTrigger.INACTIVITY_REMINDER,
            ProactiveTrigger.FOLLOW_UP
        ]

        for trigger in triggers_to_check:
            if activity.should_send_proactive(trigger):
                return trigger
        return None

    async def _create_proactive_task(self, user_id: int, activity: UserActivity,
                                     trigger: ProactiveTrigger, current_time: datetime) -> bool:
        """Создать задачу для отправки проактивного сообщения"""
        try:
            # Добавляем небольшой jitter
            jitter_seconds = random.uniform(0, min(300, self.check_interval))  # до 5 минут
            await asyncio.sleep(jitter_seconds)

            # Отправляем сообщение
            success = await self._send_proactive_message_with_dedup(user_id, activity, trigger)

            if success:
                # Добавляем время отправки в список sent_today
                self.sent_today.setdefault(user_id, []).append(datetime.utcnow())
                self.logger.info(f"Sent {trigger.value} to user {user_id}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error in proactive task for user {user_id}: {e}")
            return False

    async def _send_proactive_message_with_dedup(self, user_id: int, activity: UserActivity,
                                                 trigger: ProactiveTrigger) -> bool:
        """
        Сначала генерируем сообщение, проверяем на дубликат по последним текстам
        и по кэшу генератора, затем отправляем.
        """
        try:
            message_limits = self.message_limit_service.get_user_limits(user_id)

            # Получаем профиль и контекст
            profile = self.profile_repo.get_profile(user_id)
            conversation_context = self.conversation_repo.get_conversation_context(
                user_id, message_limits.config.max_context_messages
            )

            # Генерируем сообщение (без таймаутов в этом методе)
            message = await self.generator.generate_proactive_message(
                user_id, profile, activity, trigger, conversation_context
            )

            if not message:
                self.logger.debug(f"No message generated for user {user_id}, trigger {trigger}")
                return False

            # Дедупликация по тексту: проверяем последние отправленные тексты
            last_texts = self.last_sent_texts.get(user_id, [])
            if message in last_texts:
                self.logger.info(f"Skipping send to {user_id}: identical to recently sent text")
                return False

            # Дополнительно: если в памяти генератора есть last_generated и совпадает с new message — пропускаем
            last_generated = self.generator.get_last_for_user(user_id)
            if last_generated and last_generated == message:
                # если последнее сгенерированное == новое, значит модель повторяется — пропускаем
                self.logger.info(f"Skipping send to {user_id}: generator repeated last message")
                return False

            # Отправляем через безопасный метод
            if message and hasattr(self.bot, '_safe_send_message'):
                success = await self.bot._safe_send_message(
                    chat_id=user_id,
                    text=message
                )

                if success:
                    # Обновляем время и кэш текстов
                    activity.last_proactive_time = datetime.utcnow()
                    self.proactive_repo.save_activity(activity)

                    # Обновляем last_sent_texts (крутящийся буфер)
                    lst = self.last_sent_texts.setdefault(user_id, [])
                    lst.append(message)
                    if len(lst) > self._LAST_TEXTS_KEEP:
                        lst.pop(0)

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
        sent_times = self.sent_today.get(user_id, [])
        # Считаем только отправки за текущую дату
        sent_count_today = sum(1 for t in sent_times if t.date() == current_time.date())
        return sent_count_today >= config.proactive.max_messages_per_day

    def _cleanup_sent_cache(self, current_time: datetime):
        """Очистить кэш отправленных сообщений от вчерашних записей"""
        removed = 0
        for user_id, times in list(self.sent_today.items()):
            new_times = [t for t in times if t.date() == current_time.date()]
            if new_times:
                self.sent_today[user_id] = new_times
            else:
                del self.sent_today[user_id]
                removed += 1

        if removed:
            self.logger.info(f"🧹 Cleaned {removed} old entries from sent cache")