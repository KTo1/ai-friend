# 📄 application/use_case/manage_tariff.py
from typing import List, Tuple, Optional, Dict, Any
from domain.entity.tariff_plan import TariffPlan, UserTariff
from domain.service.tariff_service import TariffService
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageTariffUseCase:
    """Use case для управления тарифными планами"""

    def __init__(self, tariff_service: TariffService):
        self.tariff_service = tariff_service
        self.logger = StructuredLogger("manage_tariff_uc")

    @trace_span("usecase.get_all_tariffs", attributes={"component": "application"})
    def get_all_tariffs(self) -> str:
        """Получить список всех тарифных планов"""
        tariffs = self.tariff_service.get_all_tariffs()

        if not tariffs:
            return "📋 Список тарифных планов пуст"

        message = ""

        for i, tariff in enumerate(tariffs, 1):
            message = message + self.tariff_service.get_tariff_info(tariff.id) + "\n\n"

        return message

    @trace_span("usecase.assign_tariff", attributes={"component": "application"})
    def assign_tariff_to_user(self, user_id: int, tariff_plan_id: int,
                              duration_days: int = None) -> Tuple[bool, str]:
        """Назначить тарифный план пользователю"""
        return self.tariff_service.assign_tariff_to_user(user_id, tariff_plan_id, duration_days)

    @trace_span("usecase.get_user_tariff", attributes={"component": "application"})
    def get_user_tariff_info(self, user_id: int) -> str:
        """Получить информацию о тарифе пользователя"""
        user_tariff = self.tariff_service.get_user_tariff(user_id)

        if not user_tariff:
            return f"ℹ️ У пользователя {user_id} не назначен тарифный план"

        message = f"📊 **Тариф пользователя {user_id}:**\n\n"
        message += f"• Тариф: **{user_tariff.tariff_plan.name}**\n"
        message += f"• Активирован: {user_tariff.activated_at.strftime('%d.%m.%Y %H:%M')}\n"

        if user_tariff.expires_at:
            days_remaining = user_tariff.days_remaining()
            message += f"• Истекает: {user_tariff.expires_at.strftime('%d.%m.%Y')}\n"
            message += f"• Осталось дней: {days_remaining}\n"
            if user_tariff.is_expired():
                message += "• ⚠️ **ТАРИФ ИСТЕК**\n"
        else:
            message += "• Срок действия: бессрочно\n"

        message += f"• Статус: {'Активен' if user_tariff.is_active else 'Неактивен'}\n\n"

        # ИНФОРМАЦИЯ О ЛИМИТАХ ТАРИФА
        tariff = user_tariff.tariff_plan
        message += "🕒 **Рейт-лимиты:**\n"
        message += f"• В минуту: {tariff.rate_limits.messages_per_minute} сообщений\n"
        message += f"• В час: {tariff.rate_limits.messages_per_hour} сообщений\n"
        message += f"• В день: {tariff.rate_limits.messages_per_day} сообщений\n\n"

        message += "📏 **Лимиты сообщений:**\n"
        message += f"• Длина сообщения: {tariff.message_limits.max_message_length} символов\n"
        message += f"• История сообщений: {tariff.message_limits.max_context_messages}\n"
        message += f"• Длина контекста: {tariff.message_limits.max_context_length} символов\n"

        return message

    @trace_span("usecase.apply_tariff_limits", attributes={"component": "application"})
    def apply_tariff_limits_to_user(self, user_id: int, user_limits_uc: Any) -> Tuple[bool, str]:
        """
        Применить лимиты тарифа к пользователю
        user_limits_uc - это ManageUserLimitsUseCase (обновленный)
        """
        return self.tariff_service.apply_tariff_limits_to_user(user_id, user_limits_uc)

    @trace_span("usecase.remove_user_tariff", attributes={"component": "application"})
    def remove_user_tariff(self, user_id: int) -> Tuple[bool, str]:
        """Удалить тариф пользователя"""
        return self.tariff_service.remove_user_tariff(user_id)

    @trace_span("usecase.create_tariff", attributes={"component": "application"})
    def create_tariff_plan(self, **tariff_data) -> Tuple[bool, str]:
        """Создать новый тарифный план"""
        return self.tariff_service.create_tariff_plan(**tariff_data)