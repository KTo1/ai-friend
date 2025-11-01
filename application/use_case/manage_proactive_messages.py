from datetime import datetime
from typing import List, Optional
from domain.entity.proactive_message import ProactiveMessage
from domain.entity.profile import UserProfile
from domain.service.proactive_service import ProactiveService
from infrastructure.database.repositories.proactive_repository import ProactiveRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.monitoring.logging import StructuredLogger


class ManageProactiveMessagesUseCase:
    def __init__(self, proactive_repository: ProactiveRepository, profile_repository: ProfileRepository):
        self.proactive_repo = proactive_repository
        self.profile_repo = profile_repository
        self.proactive_service = ProactiveService()
        self.logger = StructuredLogger("proactive_messages_uc")

    def schedule_proactive_messages(self, user_id: int):
        """Запланировать проактивные сообщения для пользователя"""
        try:
            # Получаем профиль пользователя
            profile = self.profile_repo.get_profile(user_id)

            # Проверяем, нет ли уже активных сообщений
            if self.proactive_repo.user_has_active_messages(user_id):
                self.logger.debug(f"User {user_id} already has proactive messages")
                return

            # Генерируем новые сообщения
            messages = self.proactive_service.generate_proactive_messages(
                user_id=user_id,
                profile=profile,
                last_activity=datetime.now()  # В реальности нужно брать из истории
            )

            # Сохраняем сообщения
            for message in messages:
                self.proactive_repo.save_message(message)

            self.logger.info(
                f"Scheduled {len(messages)} proactive messages for user {user_id}",
                extra={'user_id': user_id, 'message_count': len(messages)}
            )

        except Exception as e:
            self.logger.error(f"Error scheduling proactive messages: {e}")

    def get_pending_messages(self, user_id: int) -> List[ProactiveMessage]:
        """Получить ожидающие проактивные сообщения"""
        return self.proactive_repo.get_pending_messages(user_id)

    def mark_message_sent(self, user_id: int, message_type: str):
        """Пометить сообщение как отправленное"""
        self.proactive_repo.mark_message_sent(user_id, message_type)