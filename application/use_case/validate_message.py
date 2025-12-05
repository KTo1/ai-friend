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
