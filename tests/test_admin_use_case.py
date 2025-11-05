# tests/test_admin_use_case.py
import pytest
import os
import sys
from unittest.mock import Mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from application.use_case.admin_use_case import AdminUseCase
from domain.entity.user import UserLimits


class TestAdminUseCase:
    @pytest.fixture
    def mock_dependencies(self):
        """Фикстура с моками зависимостей"""
        mock_user_repository = Mock()
        mock_user_limits_repository = Mock()

        return {
            'user_repository': mock_user_repository,
            'user_limits_repository': mock_user_limits_repository
        }

    @pytest.fixture
    def admin_uc(self, mock_dependencies):
        """Фикстура для admin use case"""
        return AdminUseCase(**mock_dependencies)

    def test_set_user_limits_success(self, admin_uc, mock_dependencies):
        """Тест: успешная установка лимитов администратором"""
        admin_user_id = 111111
        target_user_id = 123456
        limits = UserLimits(
            max_daily_requests=100,
            max_message_length=2000,
            max_tokens_per_request=5000
        )

        # Настраиваем моки
        mock_dependencies['user_limits_repository'].is_admin.return_value = True

        # Выполняем
        result = admin_uc.set_user_limits(admin_user_id, target_user_id, limits)

        # Проверяем
        assert result is True
        mock_dependencies['user_limits_repository'].set_user_limits.assert_called_once_with(target_user_id, limits)

    def test_set_user_limits_non_admin_fails(self, admin_uc, mock_dependencies):
        """Тест: не-админ не может устанавливать лимиты"""
        admin_user_id = 111111
        target_user_id = 123456
        limits = UserLimits()

        # Настраиваем моки
        mock_dependencies['user_limits_repository'].is_admin.return_value = False

        # Выполняем
        result = admin_uc.set_user_limits(admin_user_id, target_user_id, limits)

        # Проверяем
        assert result is False
        mock_dependencies['user_limits_repository'].set_user_limits.assert_not_called()

    def test_ban_user_success(self, admin_uc, mock_dependencies):
        """Тест: успешный бан пользователя"""
        admin_user_id = 111112
        target_user_id = 123457

        # Настраиваем моки
        mock_dependencies['user_limits_repository'].is_admin.return_value = True

        # Выполняем
        result = admin_uc.ban_user(admin_user_id, target_user_id, "спам")

        # Проверяем
        assert result is True
        mock_dependencies['user_limits_repository'].ban_user.assert_called_once_with(target_user_id)

    def test_unban_user_success(self, admin_uc, mock_dependencies):
        """Тест: успешный разбан пользователя"""
        admin_user_id = 111113
        target_user_id = 123458

        # Настраиваем моки
        mock_dependencies['user_limits_repository'].is_admin.return_value = True

        # Выполняем
        result = admin_uc.unban_user(admin_user_id, target_user_id)

        # Проверяем
        assert result is True
        mock_dependencies['user_limits_repository'].unban_user.assert_called_once_with(target_user_id)

    def test_get_user_stats_success(self, admin_uc, mock_dependencies):
        """Тест: успешное получение статистики пользователя"""
        admin_user_id = 111114
        target_user_id = 123459

        # Настраиваем моки
        mock_dependencies['user_limits_repository'].is_admin.return_value = True

        mock_user = Mock()
        mock_user.user_id = target_user_id
        mock_user.username = "test_user"
        mock_user.is_banned = False
        mock_user.is_active = True
        mock_user.created_at = "2024-01-01 10:00:00"

        mock_limits = UserLimits(max_daily_requests=50)
        mock_usage = {
            'requests_count': 10,
            'total_tokens_used': 5000,
            'total_cost_estimated': 0.5
        }

        mock_dependencies['user_repository'].get_user.return_value = mock_user
        mock_dependencies['user_limits_repository'].get_user_limits.return_value = mock_limits
        mock_dependencies['user_limits_repository'].get_user_usage_today.return_value = mock_usage

        # Выполняем
        stats = admin_uc.get_user_stats(admin_user_id, target_user_id)

        # Проверяем
        assert stats is not None
        assert stats['user_info']['user_id'] == target_user_id
        assert stats['user_info']['username'] == "test_user"
        assert stats['limits']['max_daily_requests'] == 50
        assert stats['usage_today']['requests_count'] == 10
        assert stats['remaining_requests'] == 40  # 50 - 10

    def test_get_user_stats_non_admin_returns_empty(self, admin_uc, mock_dependencies):
        """Тест: не-админ получает пустую статистику"""
        admin_user_id = 111115
        target_user_id = 123460

        # Настраиваем моки
        mock_dependencies['user_limits_repository'].is_admin.return_value = False

        # Выполняем
        stats = admin_uc.get_user_stats(admin_user_id, target_user_id)

        # Проверяем
        assert stats == {}