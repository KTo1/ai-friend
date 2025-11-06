from typing import Tuple, Optional, Dict
from domain.service.rate_limit_service import RateLimitService
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class CheckRateLimitUseCase:
    """Use case для проверки лимитов сообщений"""

    def __init__(self, rate_limit_service: RateLimitService):
        self.rate_limit_service = rate_limit_service
        self.logger = StructuredLogger("check_rate_limit_uc")

    @trace_span("usecase.check_rate_limit", attributes={"component": "application"})
    def execute(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Проверить может ли пользователь отправить сообщение

        Returns:
            Tuple[bool, Optional[str]]: (может отправить, сообщение об ошибке)
        """
        can_send, limits_info = self.rate_limit_service.check_rate_limit(user_id)

        if can_send:
            return True, None

        # Формируем сообщение об ошибке
        error_message = self._format_rate_limit_message(limits_info)
        return False, error_message

    def get_limits_info(self, user_id: int) -> Dict:
        """Получить информацию о лимитах пользователя"""
        return self.rate_limit_service.get_user_limits_info(user_id)

    def record_message_usage(self, user_id: int):
        """Записать использование сообщения"""
        self.rate_limit_service.record_message(user_id)

    def _format_rate_limit_message(self, limits_info: Dict) -> str:
        """Форматировать сообщение о превышении лимита"""
        remaining = limits_info['remaining']
        time_until_reset = limits_info['time_until_reset']
        config = limits_info['config']

        message = "⏰ Превышен лимит сообщений!\n\n"

        if remaining['minute'] <= 0:
            message += f"• Минутный лимит: {config['minute']} сообщений\n"
            message += f"⏳ Жди: {time_until_reset['minute']}\n\n"
        elif remaining['hour'] <= 0:
            message += f"• Часовой лимит: {config['hour']} сообщений\n"
            message += f"⏳ Жди: {time_until_reset['hour']}\n\n"
        elif remaining['day'] <= 0:
            message += f"• Дневной лимит: {config['day']} сообщений\n"
            message += f"⏳ Жди: {time_until_reset['day']}\n\n"

        message += f"Осталось сообщений:\n"
        message += f"• В минуту: {remaining['minute']}/{config['minute']}\n"
        message += f"• В час: {remaining['hour']}/{config['hour']}\n"
        message += f"• В день: {remaining['day']}/{config['day']}\n\n"
        message += "Лимиты сбрасываются автоматически 🕒"

        return message