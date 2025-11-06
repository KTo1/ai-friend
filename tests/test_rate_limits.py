import pytest
import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.database.repositories.user_limits_repository import UserLimitsRepository
from domain.entity.user import UserLimits


class TestRateLimits:
    @pytest.fixture
    def mock_db(self):
        mock_db = Mock()
        mock_db.execute_query = Mock()
        mock_db.fetch_one = Mock()
        return mock_db

    @pytest.fixture
    def repo(self, mock_db):
        return UserLimitsRepository(mock_db)

    def test_rate_limits_reset_after_minute(self, repo, mock_db):
        """Тест: счетчики сбрасываются после минуты"""
        user_id = 123456

        # Настраиваем мок для существующих лимитов
        old_time = datetime.now() - timedelta(seconds=61)  # Прошло больше минуты
        mock_db.fetch_one.return_value = (
            100, 1000, 10, 2000, False,  # базовые лимиты
            3, 60,  # rate limits
            old_time.isoformat(), 2,  # minute: 2 сообщения из 3
            old_time.isoformat(), 10,  # hour: 10 сообщений из 60
            old_time.isoformat()  # updated_at
        )

        # Проверяем лимиты
        result = repo.check_rate_limits(user_id)

        # Должен быть сброс и разрешение
        assert result["allowed"] is True
        assert result["minute_count"] == 1  # Сброшено до 0 и увеличено до 1
        assert result["minute_remaining"] == 2

    def test_rate_limits_block_when_exceeded(self, repo, mock_db):
        """Тест: блокировка при превышении лимита"""
        user_id = 123457

        # Настраиваем мок для лимитов с превышением
        current_time = datetime.now()
        mock_db.fetch_one.return_value = (
            100, 1000, 10, 2000, False,
            3, 60,
            current_time.isoformat(), 3,  # уже 3 сообщения (лимит)
            current_time.isoformat(), 10,
            current_time.isoformat()
        )

        # Проверяем лимиты
        result = repo.check_rate_limits(user_id)

        # Должен быть запрет
        assert result["allowed"] is False
        assert result["minute_remaining"] == 0

    def test_rate_limits_allow_within_limits(self, repo, mock_db):
        """Тест: разрешение в пределах лимитов"""
        user_id = 123458

        # Настраиваем мок для лимитов в пределах
        current_time = datetime.now()
        mock_db.fetch_one.return_value = (
            100, 1000, 10, 2000, False,
            3, 60,
            current_time.isoformat(), 1,  # 1 сообщение из 3
            current_time.isoformat(), 5,
            current_time.isoformat()
        )

        # Проверяем лимиты
        result = repo.check_rate_limits(user_id)

        # Должен быть разрешен
        assert result["allowed"] is True
        assert result["minute_count"] == 2  # Увеличено на 1
        assert result["minute_remaining"] == 1