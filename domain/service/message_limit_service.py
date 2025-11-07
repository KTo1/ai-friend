from typing import Tuple, Optional, Dict
from domain.entity.message_limit import UserMessageLimit, MessageLimitConfig
from infrastructure.database.repositories.message_limit_repository import MessageLimitRepository
from infrastructure.monitoring.logging import StructuredLogger


class MessageLimitService:
    """Сервис для управления лимитами сообщений пользователей"""

    def __init__(self, message_limit_repo: MessageLimitRepository):
        self.message_limit_repo = message_limit_repo
        self.default_config = MessageLimitConfig.from_env()
        self.logger = StructuredLogger("message_limit_service")

        # Кэш для активных пользователей
        self._message_limits_cache: Dict[int, UserMessageLimit] = {}

    def validate_message(self, user_id: int, message: str) -> Tuple[bool, str]:
        """
        Валидация сообщения пользователя с учетом его лимитов

        Returns:
            Tuple[bool, str]: (валидно, сообщение об ошибке)
        """
        user_limit = self._get_or_create_user_limit(user_id)

        # Проверка максимальной длины
        if len(message) > user_limit.config.max_message_length:
            # Обновляем статистику (сообщение отклонено)
            user_limit.update_stats(len(message), was_rejected=True)
            self._save_user_limit(user_limit)

            error_msg = (
                f"🚫 Ваше сообщение слишком длинное ({len(message)} символов).\n"
                f"Максимально допустимая длина: {user_limit.config.max_message_length} символов.\n\n"
                f"Пожалуйста, разделите ваше сообщение на несколько частей или сократите его."
            )

            self.logger.info(
                f"Message rejected - too long from user {user_id}",
                extra={
                    'user_id': user_id,
                    'message_length': len(message),
                    'limit': user_limit.config.max_message_length
                }
            )

            return False, error_msg

        # Сообщение валидно - обновляем статистику
        user_limit.update_stats(len(message), was_rejected=False)
        self._save_user_limit(user_limit)

        # Логируем длинные сообщения (но в пределах лимита)
        if len(message) > 1000:
            self.logger.info(
                f"Long message from user {user_id}",
                extra={
                    'user_id': user_id,
                    'message_length': len(message),
                    'limit': user_limit.config.max_message_length
                }
            )

        return True, ""

    def get_user_limits_config(self, user_id: int) -> MessageLimitConfig:
        """Получить конфигурацию лимитов пользователя"""
        message_limit = self._get_or_create_user_limit(user_id)
        return MessageLimitConfig(
            max_message_length=message_limit.config.max_message_length,
            max_context_messages=message_limit.config.max_context_messages,
            max_context_length=message_limit.config.max_context_length
        )

    def update_user_limits_config(self, user_id: int, **limits) -> bool:
        """Обновить конфигурацию лимитов пользователя"""
        message_limit = self._get_or_create_user_limit(user_id)

        for key, value in limits.items():
            if hasattr(message_limit.config, key):
                setattr(message_limit.config, key, value)

        self._save_user_limit(message_limit)
        return True

    def get_user_limits(self, user_id: int) -> UserMessageLimit:
        """Получить лимиты пользователя"""
        return self._get_or_create_user_limit(user_id)

    def update_user_limits(self, user_id: int, **limits) -> bool:
        """Обновить лимиты пользователя"""
        user_limit = self._get_or_create_user_limit(user_id)

        # Обновляем конфигурацию
        for key, value in limits.items():
            if hasattr(user_limit.config, key):
                setattr(user_limit.config, key, value)

        self._save_user_limit(user_limit)

        self.logger.info(
            f"Updated message limits for user {user_id}",
            extra={'user_id': user_id, 'new_limits': limits}
        )

        return True

    def reset_user_limits(self, user_id: int):
        """Сбросить лимиты пользователя к значениям по умолчанию"""
        if user_id in self._message_limits_cache:
            del self._message_limits_cache[user_id]

        self.message_limit_repo.delete_user_limit(user_id)
        self.logger.info(f"Message limits reset for user {user_id}")

    def get_user_stats(self, user_id: int) -> Dict:
        """Получить статистику пользователя"""
        user_limit = self._get_or_create_user_limit(user_id)
        return user_limit.get_stats()

    def _get_or_create_user_limit(self, user_id: int) -> UserMessageLimit:
        """Получить или создать лимиты пользователя"""
        if user_id in self._message_limits_cache:
            return self._message_limits_cache[user_id]

        # Пытаемся загрузить из базы
        user_limit = self.message_limit_repo.get_user_limit(user_id, self.default_config)

        if not user_limit:
            # Создаем новый с дефолтными настройками
            user_limit = UserMessageLimit(user_id=user_id, config=self.default_config)
            self._save_user_limit(user_limit)

        self._message_limits_cache[user_id] = user_limit
        return user_limit

    def _save_user_limit(self, user_limit: UserMessageLimit):
        """Сохранить лимиты пользователя"""
        try:
            self.message_limit_repo.save_user_limit(user_limit)
        except Exception as e:
            self.logger.error(f"Error saving message limit for user {user_limit.user_id}: {e}")