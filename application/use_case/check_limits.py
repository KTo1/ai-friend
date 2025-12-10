from typing import Tuple, Optional, Dict
from domain.entity.tariff_plan import TariffPlan
from domain.service.limit_service import LimitService
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class CheckLimitsUseCase:
    """Use case для проверки всех лимитов"""

    def __init__(self, limit_service: LimitService):
        self.limit_service = limit_service
        self.logger = StructuredLogger("check_limits_uc")

    @trace_span("usecase.check_limits", attributes={"component": "application"})
    def check_message_length(self, user_id: int, message: str, tariff: TariffPlan) -> Tuple[bool, Optional[str]]:
        """Проверить длину сообщения"""
        return self.limit_service.check_message_length(user_id, message, tariff)

    @trace_span("usecase.check_rate_limit", attributes={"component": "application"})
    def check_rate_limit(self, user_id: int, tariff: TariffPlan) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """Проверить rate limit"""
        return self.limit_service.check_rate_limit(user_id, tariff)

    @trace_span("usecase.record_message_usage", attributes={"component": "application"})
    def record_message_usage(self, user_id: int, message_length: int, tariff: TariffPlan):
        """Записать использование сообщения"""
        self.limit_service.record_message_usage(user_id, message_length, tariff)

    @trace_span("usecase.get_limits_info", attributes={"component": "application"})
    def get_limits_info(self, user_id: int, tariff: TariffPlan) -> Dict:
        """Получить информацию о лимитах пользователя"""
        return self.limit_service.get_user_limits_info(user_id, tariff)