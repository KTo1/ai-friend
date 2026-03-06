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

    @trace_span("usecase.get_users_list", attributes={"component": "application"})
    def get_users_list(self, page: int = 1, page_size: int = 20) -> str:
        """Получить список пользователей с пагинацией"""
        try:
            all_users = self.admin_service.get_all_users()

            if not all_users:
                return "📋 Список пользователей пуст"

            # Применяем пагинацию
            total_users = len(all_users)
            total_pages = (total_users + page_size - 1) // page_size
            page = max(1, min(page, total_pages))

            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            users_page = all_users[start_idx:end_idx]

            message = f"👥 **Список пользователей** (страница {page}/{total_pages}):\n\n"

            for i, user in enumerate(users_page, start_idx + 1):
                # Основная информация
                username = f"@{user.username}" if user.username else "без username"
                name = user.first_name or "Без имени"
                role = "👑" if user.is_admin else "👤"
                status = "🚫" if user.is_blocked else "🟢"
                utm = f"{user.utm_label}"

                message += f"{i}. {role} {status} {name} {username}\n"
                message += f"   🆔 ID: {user.user_id}\n"

                # Статус блокировки
                if user.is_blocked:
                    message += f"   ⚠️ Заблокирован\n"

                # Активность
                if user.last_seen:
                    from datetime import datetime, timedelta
                    days_ago = (datetime.now() - user.last_seen).days
                    if days_ago == 0:
                        message += f"   🕒 Был сегодня\n"
                    elif days_ago == 1:
                        message += f"   🕒 Был вчера\n"
                    elif days_ago < 7:
                        message += f"   🕒 Был {days_ago} дней назад\n"
                    else:
                        message += f"   🕒 Неактивен {days_ago} дней\n"

                if utm:
                    message += f"   ⚠️ {utm}\n"

                message += "\n"

            # Статистика в конце
            admin_count = len([u for u in all_users if u.is_admin])
            blocked_count = len([u for u in all_users if u.is_blocked])

            message += f"📊 **Статистика:** Всего: {total_users} | Админы: {admin_count} | Заблокированы: {blocked_count}\n"
            message += f"💡 Используйте `/admin_users <страница>` для навигации"

            return message

        except Exception as e:
            self.logger.error(f"Error getting users list: {e}")
            return "❌ Ошибка при получении списка пользователей"

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