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

    def get_tariff_by_name(self, name: str) -> Optional[TariffPlan]:
        """Получить тариф по имени"""
        return self.tariff_repo.get_tariff_plan_by_name(name)

    def get_default_tariff(self) -> Optional[TariffPlan]:
        """Получить тариф по умолчанию"""
        return self.tariff_repo.get_default_tariff_plan()

    def create_tariff_plan(self, **tariff_data) -> Tuple[bool, str]:
        """Создать новый тарифный план"""
        try:
            from domain.entity.tariff_plan import RateLimitConfig, MessageLimitConfig

            # Извлекаем лимиты из данных
            rate_limits = RateLimitConfig(
                messages_per_minute=tariff_data.get('messages_per_minute', 2),
                messages_per_hour=tariff_data.get('messages_per_hour', 15),
                messages_per_day=tariff_data.get('messages_per_day', 30)
            )

            message_limits = MessageLimitConfig(
                max_message_length=tariff_data.get('max_message_length', 2000),
                max_context_messages=tariff_data.get('max_context_messages', 10),
                max_context_length=tariff_data.get('max_context_length', 4000)
            )

            tariff = TariffPlan(
                id=0,
                name=tariff_data['name'],
                description=tariff_data.get('description', ''),
                price=tariff_data.get('price', 0),
                rate_limits=rate_limits,
                message_limits=message_limits,
                is_active=tariff_data.get('is_active', True),
                is_default=tariff_data.get('is_default', False),
                features=tariff_data.get('features', {})
            )

            tariff_id = self.tariff_repo.save_tariff_plan(tariff)
            self.logger.info(f"Created tariff plan: {tariff.name} (ID: {tariff_id})")
            return True, f"✅ Тарифный план '{tariff.name}' создан (ID: {tariff_id})"

        except Exception as e:
            self.logger.error(f"Error creating tariff plan: {e}")
            return False, f"❌ Ошибка при создании тарифного плана: {str(e)}"

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

    def apply_tariff_limits_to_user(self, user_id: int, user_limits_uc: Any) -> Tuple[bool, str]:
        """
        Применить лимиты тарифа к пользователю.
        В новой архитектуре этот метод только логирует применение,
        так как лимиты теперь хранятся в тарифе и проверяются через LimitService.
        """
        try:
            user_tariff = self.get_user_tariff(user_id)
            if not user_tariff or not user_tariff.tariff_plan:
                return False, f"❌ У пользователя {user_id} не назначен тариф"

            # Используем новый use case для применения лимитов
            return user_limits_uc.apply_tariff_limits(user_id, user_tariff.tariff_plan)

        except Exception as e:
            self.logger.error(f"Error applying tariff limits to user {user_id}: {e}")
            return False, f"❌ Ошибка при применении лимитов тарифа: {str(e)}"

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
        message += f"• Макс. длина контекста: {tariff.message_limits.max_context_length} символов\n\n"

        if tariff.features:
            message += "🌟 **Особенности:**\n"
            for feature, value in tariff.features.items():
                message += f"• {feature}: {value}\n"

        return message