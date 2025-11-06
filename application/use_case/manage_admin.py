from typing import List, Dict, Tuple
from domain.entity.user import User
from domain.service.admin_service import AdminService
from infrastructure.monitoring.tracing import trace_span
from infrastructure.monitoring.logging import StructuredLogger


class ManageAdminUseCase:
    """Use case для управления администраторами"""

    def __init__(self, admin_service: AdminService):
        self.admin_service = admin_service
        self.logger = StructuredLogger("manage_admin_uc")

    @trace_span("usecase.check_admin", attributes={"component": "application"})
    def is_user_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        return self.admin_service.is_admin(user_id)

    @trace_span("usecase.promote_user", attributes={"component": "application"})
    def promote_user(self, target_user_id: int, admin_user_id: int) -> Tuple[bool, str]:
        """
        Назначить пользователя администратором

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        success = self.admin_service.promote_user(target_user_id, admin_user_id)

        if success:
            return True, f"✅ Пользователь {target_user_id} назначен администратором"
        else:
            return False, f"❌ Не удалось назначить пользователя {target_user_id} администратором"

    @trace_span("usecase.demote_user", attributes={"component": "application"})
    def demote_user(self, target_user_id: int, admin_user_id: int) -> Tuple[bool, str]:
        """
        Убрать права администратора

        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        success = self.admin_service.demote_user(target_user_id, admin_user_id)

        if success:
            return True, f"✅ Пользователь {target_user_id} лишен прав администратора"
        else:
            return False, f"❌ Не удалось лишить пользователя {target_user_id} прав администратора"

    @trace_span("usecase.get_admin_list", attributes={"component": "application"})
    def get_admin_list(self) -> str:
        """Получить список администраторов"""
        admins = self.admin_service.get_admin_users()

        if not admins:
            return "📋 Список администраторов пуст"

        message = "👑 **Список администраторов:**\n\n"
        for i, admin in enumerate(admins, 1):
            username = f"@{admin.username}" if admin.username else "без username"
            message += f"{i}. {admin.first_name or 'Без имени'} {username} (ID: {admin.user_id})\n"

            # Безопасное форматирование дат
            created_str = self._format_datetime(admin.created_at)
            last_seen_str = self._format_datetime(admin.last_seen)

            message += f"   📅 Зарегистрирован: {created_str}\n"
            message += f"   👀 Последний раз: {last_seen_str}\n\n"

        return message

    @trace_span("usecase.get_user_stats", attributes={"component": "application"})
    def get_user_stats(self) -> str:
        """Получить статистику пользователей"""
        stats = self.admin_service.get_user_stats()

        message = "📊 **Статистика пользователей:**\n\n"
        message += f"• Всего пользователей: {stats['total_users']}\n"
        message += f"• Администраторов: {stats['admin_users']}\n"
        message += f"• Обычных пользователей: {stats['regular_users']}\n"
        message += f"• Активных пользователей: {stats['active_users']}\n"
        message += f"• Неактивных пользователей: {stats['inactive_users']}\n"

        return message

    @trace_span("usecase.get_user_info", attributes={"component": "application"})
    def get_user_info(self, user_id: int) -> str:
        """Получить информацию о пользователе"""
        try:
            user = self.admin_service.user_repo.get_user(user_id)

            if not user:
                return f"❌ Пользователь с ID {user_id} не найден"

            role = "👑 Администратор" if user.is_admin else "👤 Обычный пользователь"
            username = f"@{user.username}" if user.username else "не установлен"

            # Безопасная проверка активности
            is_active = self.admin_service._is_user_active(user)
            status = "🟢 Активен" if is_active else "🔴 Неактивен"

            # Безопасное форматирование дат
            created_str = self._format_datetime(user.created_at)
            last_seen_str = self._format_datetime(user.last_seen)

            message = f"👤 **Информация о пользователе:**\n\n"
            message += f"• ID: {user.user_id}\n"
            message += f"• Имя: {user.first_name or 'не указано'}\n"
            message += f"• Фамилия: {user.last_name or 'не указана'}\n"
            message += f"• Username: {username}\n"
            message += f"• Роль: {role}\n"
            message += f"• Статус: {status}\n"
            message += f"• Зарегистрирован: {created_str}\n"
            message += f"• Последняя активность: {last_seen_str}\n"

            return message

        except Exception as e:
            self.logger.error(f"Error getting user info for {user_id}: {e}")
            return f"❌ Ошибка при получении информации о пользователе {user_id}"

    def _format_datetime(self, dt_value) -> str:
        """Безопасное форматирование datetime"""
        try:
            if not dt_value:
                return "неизвестно"

            # Если это строка, попробуем преобразовать в datetime
            if isinstance(dt_value, str):
                dt_value = self.admin_service._parse_datetime(dt_value)

            if isinstance(dt_value, (int, float)):
                # Если это timestamp
                from datetime import datetime
                dt_value = datetime.fromtimestamp(dt_value)

            if hasattr(dt_value, 'strftime'):
                return dt_value.strftime('%d.%m.%Y %H:%M')
            else:
                return str(dt_value)

        except Exception as e:
            self.logger.debug(f"Error formatting datetime {dt_value}: {e}")
            return "неизвестно"