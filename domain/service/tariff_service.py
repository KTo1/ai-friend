# 📄 domain/service/tariff_service.py
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from domain.entity.tariff_plan import TariffPlan, UserTariff
from infrastructure.database.repositories.tariff_repository import TariffRepository
from infrastructure.monitoring.logging import StructuredLogger


class TariffService:
    """Сервис для управления тарифными планами"""

    def __init__(self, tariff_repository: TariffRepository):
        self.tariff_repo = tariff_repository
        self.logger = StructuredLogger("tariff_service")

    def get_all_tariffs(self, active_only: bool = True) -> List[TariffPlan]:
        """Получить все тарифные планы"""
        return self.tariff_repo.get_all_tariff_plans(active_only)

    def get_tariff_by_id(self, tariff_id: int) -> Optional[TariffPlan]:
        """Получить тариф по ID"""
        return self.tariff_repo.get_tariff_plan(tariff_id)

    def get_default_tariff(self) -> Optional[TariffPlan]:
        """Получить тариф по умолчанию"""
        return self.tariff_repo.get_default_tariff_plan()

    def assign_tariff_to_user(self, user_id: int, tariff_plan_id: int,
                              duration_days: int = None) -> Tuple[bool, str]:
        """Назначить тариф пользователю"""
        try:
            # Получаем тариф
            tariff = self.tariff_repo.get_tariff_plan(tariff_plan_id)
            if not tariff:
                return False, f"❌ Тарифный план с ID {tariff_plan_id} не найден"

            # Рассчитываем дату истечения
            expires_at = None
            if duration_days:
                expires_at = datetime.utcnow() + timedelta(days=duration_days)

            # Назначаем тариф
            success = self.tariff_repo.assign_tariff_to_user(user_id, tariff_plan_id, expires_at)
            if success:
                self.logger.info(f"Assigned tariff {tariff.name} to user {user_id}")
                message = f"✅ Пользователю {user_id} назначен тариф '{tariff.name}'"
                if expires_at:
                    message += f" на {duration_days} дней (до {expires_at.strftime('%d.%m.%Y')})"
                return True, message
            else:
                return False, f"❌ Ошибка при назначении тарифа пользователю {user_id}"

        except Exception as e:
            self.logger.error(f"Error assigning tariff to user {user_id}: {e}")
            return False, f"❌ Ошибка при назначении тарифа: {str(e)}"

    def get_user_tariff(self, user_id: int) -> Optional[UserTariff]:
        """Получить тариф пользователя"""
        return self.tariff_repo.get_user_tariff(user_id)

    def remove_user_tariff(self, user_id: int) -> Tuple[bool, str]:
        """Удалить тариф пользователя"""
        try:
            success = self.tariff_repo.remove_user_tariff(user_id)
            if success:
                self.logger.info(f"Removed tariff from user {user_id}")
                return True, f"✅ Тариф пользователя {user_id} удален"
            else:
                return False, f"❌ Ошибка при удалении тарифа пользователя {user_id}"
        except Exception as e:
            self.logger.error(f"Error removing tariff from user {user_id}: {e}")
            return False, f"❌ Ошибка при удалении тарифа: {str(e)}"

    def get_tariff_info(self, tariff_plan_id: int) -> str:
        """Получить информацию о тарифном плане"""
        tariff = self.get_tariff_by_id(tariff_plan_id)
        if not tariff:
            return f"❌ Тарифный план с ID {tariff_plan_id} не найден"

        message = f"📋 **Тарифный план: {tariff.name}**\n\n"
        message += f"📝 Описание: {tariff.description}\n"
        message += f"💰 Цена: {tariff.price} руб./месяц\n"
        message += f"🔄 Статус: {'Активен' if tariff.is_active else 'Неактивен'}\n"
        message += f"⚙️ По умолчанию: {'Да' if tariff.is_default else 'Нет'}\n\n"

        message += "🕒 **Рейт-лимиты:**\n"
        message += f"• В минуту: {tariff.rate_limits.messages_per_minute} сообщений\n"
        message += f"• В час: {tariff.rate_limits.messages_per_hour} сообщений\n"
        message += f"• В день: {tariff.rate_limits.messages_per_day} сообщений\n\n"

        message += "📏 **Лимиты сообщений:**\n"
        message += f"• Макс. длина сообщения: {tariff.message_limits.max_message_length} символов\n"
        message += f"• Макс. сообщений в истории: {tariff.message_limits.max_context_messages}\n"

        if tariff.features:
            message += "🌟 **Особенности:**\n"
            for feature, value in tariff.features.items():
                message += f"• {feature}: {value}\n"

        return message