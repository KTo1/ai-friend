from typing import Tuple, Dict
from domain.service.message_limit_service import MessageLimitService
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ValidateMessageUseCase:
    """Use case для валидации сообщений с учетом лимитов пользователя"""

    def __init__(self, message_limit_service: MessageLimitService):
        self.message_limit_service = message_limit_service
        self.logger = StructuredLogger("validate_message_uc")

    @trace_span("usecase.validate_message", attributes={"component": "application"})
    def execute(self, user_id: int, message: str) -> Tuple[bool, str]:
        """
        Валидация сообщения пользователя

        Returns:
            Tuple[bool, str]: (валидно, сообщение об ошибке)
        """
        return self.message_limit_service.validate_message(user_id, message)

    @trace_span("usecase.get_message_stats", attributes={"component": "application"})
    def get_user_stats(self, user_id: int) -> Dict:
        """Получить статистику сообщений пользователя"""
        return self.message_limit_service.get_user_stats(user_id)

    @trace_span("usecase.update_message_limits", attributes={"component": "application"})
    def update_user_limits(self, user_id: int, **limits) -> Tuple[bool, str]:
        """
        Обновить лимиты сообщений пользователя

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        try:
            success = self.message_limit_service.update_user_limits(user_id, **limits)
            if success:
                return True, f"✅ Лимиты сообщений для пользователя {user_id} обновлены"
            else:
                return False, f"❌ Не удалось обновить лимиты для пользователя {user_id}"
        except Exception as e:
            self.logger.error(f"Error updating message limits for user {user_id}: {e}")
            return False, f"❌ Ошибка при обновлении лимитов: {str(e)}"

    @trace_span("usecase.reset_message_limits", attributes={"component": "application"})
    def reset_user_limits(self, user_id: int) -> Tuple[bool, str]:
        """
        Сбросить лимиты сообщений пользователя

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        try:
            self.message_limit_service.reset_user_limits(user_id)
            return True, f"✅ Лимиты сообщений для пользователя {user_id} сброшены к значениям по умолчанию"
        except Exception as e:
            self.logger.error(f"Error resetting message limits for user {user_id}: {e}")
            return False, f"❌ Ошибка при сбросе лимитов: {str(e)}"