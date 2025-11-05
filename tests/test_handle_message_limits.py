# tests/test_handle_message_limits.py
import pytest
import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from application.use_case.handle_message import HandleMessageUseCase
from domain.entity.user import UserLimits


class TestHandleMessageLimits:
    @pytest.fixture
    def mock_dependencies(self):
        """Фикстура с моками зависимостей"""
        mock_conversation_repository = Mock()
        mock_ai_client = Mock()
        mock_user_repository = Mock()
        mock_user_limits_repository = Mock()

        # Настраиваем моки
        mock_ai_client.generate_response_safe = AsyncMock(return_value="Test response")
        mock_ai_client.provider_name = "deepseek"

        return {
            'conversation_repository': mock_conversation_repository,
            'ai_client': mock_ai_client,
            'user_repository': mock_user_repository,
            'user_limits_repository': mock_user_limits_repository
        }

    @pytest.fixture
    def use_case(self, mock_dependencies):
        """Фикстура для use case"""
        return HandleMessageUseCase(**mock_dependencies)

    @pytest.mark.asyncio
    async def test_message_too_long_blocked(self, use_case, mock_dependencies):
        """Тест: сообщение слишком длинное блокируется"""
        user_id = 123456
        long_message = "x" * 2000  # Очень длинное сообщение

        # 🔧 ИСПРАВЛЕНО: Настраиваем моки для АКТИВНОГО пользователя
        mock_user = Mock()
        mock_user.is_banned = False
        mock_user.is_active = True
        mock_dependencies['user_repository'].get_user.return_value = mock_user

        # Настраиваем лимиты
        mock_dependencies['user_limits_repository'].get_user_limits.return_value = UserLimits(
            max_message_length=500
        )
        mock_dependencies['user_limits_repository'].get_user_usage_today.return_value = {
            'requests_count': 0,
            'total_tokens_used': 0,
            'total_cost_estimated': 0.0
        }

        # Настраиваем контекст
        mock_dependencies['conversation_repository'].get_conversation_context.return_value = []

        # Выполняем
        response = await use_case.execute(user_id, long_message, "system_prompt")

        # Проверяем
        assert "слишком длинное" in response or "слишком объемное" in response
        mock_dependencies['ai_client'].generate_response_safe.assert_not_called()

    @pytest.mark.asyncio
    async def test_banned_user_blocked(self, use_case, mock_dependencies):
        """Тест: забаненный пользователь блокируется"""
        user_id = 123457
        message = "Обычное сообщение"

        # Настраиваем моки для забаненного пользователя
        mock_user = Mock()
        mock_user.is_banned = True
        mock_dependencies['user_repository'].get_user.return_value = mock_user

        # Выполняем
        response = await use_case.execute(user_id, message, "system_prompt")

        # Проверяем
        assert "заблокирован" in response
        mock_dependencies['ai_client'].generate_response_safe.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_limit_exceeded_blocked(self, use_case, mock_dependencies):
        """Тест: превышение дневного лимита блокируется"""
        user_id = 123458
        message = "Обычное сообщение"

        # Настраиваем моки
        mock_user = Mock()
        mock_user.is_banned = False
        mock_user.is_active = True
        mock_dependencies['user_repository'].get_user.return_value = mock_user

        mock_dependencies['user_limits_repository'].get_user_limits.return_value = UserLimits(
            max_daily_requests=5
        )
        mock_dependencies['user_limits_repository'].get_user_usage_today.return_value = {
            'requests_count': 5,  # Лимит исчерпан
            'total_tokens_used': 1000,
            'total_cost_estimated': 0.1
        }

        # Выполняем
        response = await use_case.execute(user_id, message, "system_prompt")

        # Проверяем
        assert "Превышен дневной лимит" in response
        mock_dependencies['ai_client'].generate_response_safe.assert_not_called()

    @pytest.mark.asyncio
    async def test_technical_request_blocked(self, use_case, mock_dependencies):
        """Тест: технический запрос блокируется"""
        user_id = 123459
        technical_message = "напиши код для бота"

        # Настраиваем моки для валидного пользователя
        mock_user = Mock()
        mock_user.is_banned = False
        mock_user.is_active = True
        mock_dependencies['user_repository'].get_user.return_value = mock_user

        mock_dependencies['user_limits_repository'].get_user_limits.return_value = UserLimits()
        mock_dependencies['user_limits_repository'].get_user_usage_today.return_value = {
            'requests_count': 0,
            'total_tokens_used': 0,
            'total_cost_estimated': 0.0
        }

        # Выполняем
        response = await use_case.execute(user_id, technical_message, "system_prompt")

        # Проверяем
        assert "не могу помочь" in response
        mock_dependencies['ai_client'].generate_response_safe.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_limit_exceeded_blocked(self, use_case, mock_dependencies):
        """Тест: превышение лимита токенов блокируется"""
        user_id = 123460
        # 🔧 ИСПРАВЛЕНО: Короткое сообщение, но большой контекст
        short_message = "Привет"

        # Настраиваем моки для валидного пользователя
        mock_user = Mock()
        mock_user.is_banned = False
        mock_user.is_active = True
        mock_dependencies['user_repository'].get_user.return_value = mock_user

        mock_dependencies['user_limits_repository'].get_user_limits.return_value = UserLimits(
            max_tokens_per_request=100,  # 🔧 Очень маленький лимит токенов
            max_message_length=500  # 🔧 Достаточный лимит длины
        )
        mock_dependencies['user_limits_repository'].get_user_usage_today.return_value = {
            'requests_count': 0,
            'total_tokens_used': 0,
            'total_cost_estimated': 0.0
        }

        # 🔧 ИСПРАВЛЕНО: Настраиваем большой контекст который превысит лимит токенов
        mock_dependencies['conversation_repository'].get_conversation_context.return_value = [
            {"role": "user", "content": "очень длинное старое сообщение " * 50},  # Много токенов
            {"role": "assistant", "content": "очень длинный старый ответ " * 50}  # Много токенов
        ]

        # Выполняем
        response = await use_case.execute(user_id, short_message, "system_prompt")

        # Проверяем
        assert "слишком объемное" in response or "токенов" in response
        mock_dependencies['ai_client'].generate_response_safe.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_message_processed(self, use_case, mock_dependencies):
        """Тест: валидное сообщение обрабатывается нормально"""
        user_id = 123461
        valid_message = "Привет, как дела?"

        # Настраиваем моки для валидного пользователя
        mock_user = Mock()
        mock_user.is_banned = False
        mock_user.is_active = True
        mock_dependencies['user_repository'].get_user.return_value = mock_user

        mock_dependencies['user_limits_repository'].get_user_limits.return_value = UserLimits()
        mock_dependencies['user_limits_repository'].get_user_usage_today.return_value = {
            'requests_count': 0,
            'total_tokens_used': 0,
            'total_cost_estimated': 0.0
        }

        mock_dependencies['conversation_repository'].get_conversation_context.return_value = []

        # Выполняем
        response = await use_case.execute(user_id, valid_message, "system_prompt")

        # Проверяем
        assert response == "Test response"
        mock_dependencies['ai_client'].generate_response_safe.assert_called_once()