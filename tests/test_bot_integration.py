# tests/test_bot_integration.py
import pytest
import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from presentation.telegram.bot import FriendBot


class TestBotIntegration:
    @pytest.fixture
    def bot(self):
        """Фикстура для бота с полным контролем над инициализацией"""
        with patch('presentation.telegram.bot.setup_logging'), \
                patch('presentation.telegram.bot.Database') as mock_db_class, \
                patch('presentation.telegram.bot.AIFactory.create_client') as mock_ai_factory, \
                patch('presentation.telegram.bot.metrics_collector'), \
                patch('presentation.telegram.bot.trace_manager'), \
                patch('presentation.telegram.bot.HealthChecker') as mock_health_class:
            # Создаем мок инстансы БАЗОВЫХ компонентов
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            mock_ai_client = AsyncMock()
            mock_ai_client.generate_response_safe = AsyncMock(return_value="Тестовый ответ")
            mock_ai_client.provider_name = "deepseek"
            mock_ai_factory.return_value = mock_ai_client

            mock_health = Mock()
            mock_health.perform_health_check = Mock(return_value=Mock(
                status="healthy",
                details={"database": {"status": "healthy"}, "ai_provider": {"status": "healthy"}}
            ))
            mock_health_class.return_value = mock_health

            # Теперь создаем бота, но ПЕРЕОПРЕДЕЛЯЕМ его атрибуты после инициализации
            bot = FriendBot()

            # 🔧 ПЕРЕОПРЕДЕЛЯЕМ все компоненты бота на наши моки
            bot.database = mock_db
            bot.ai_client = mock_ai_client
            bot.health_checker = mock_health

            # Создаем моки для репозиториев
            bot.user_repo = Mock()
            bot.profile_repo = Mock()
            bot.conversation_repo = Mock()
            bot.user_limits_repo = Mock()

            # Создаем моки для use cases
            bot.start_conversation_uc = Mock()
            bot.start_conversation_uc.execute = Mock(return_value="Добро пожаловать!")

            bot.manage_profile_uc = Mock()
            bot.manage_profile_uc.get_profile = Mock(return_value="Ваш профиль")
            bot.manage_profile_uc.extract_and_update_profile = Mock(return_value=("Test", 25, "чтение", "хорошее"))
            bot.manage_profile_uc.get_memory = Mock(return_value="Я помню о тебе...")

            bot.handle_message_uc = AsyncMock()
            bot.handle_message_uc.execute = AsyncMock(return_value="Это тестовый ответ")

            bot.admin_uc = Mock()

            # 🔧 ИСПРАВЛЕНО: Полные данные для admin_stats
            bot.admin_uc.get_user_stats = Mock(return_value={
                'user_info': {
                    'user_id': 123456,
                    'username': 'test_user',
                    'is_banned': False,
                    'is_active': True,
                    'created_at': '2024-01-01 10:00:00'  # ✅ ДОБАВЛЕНО
                },
                'limits': {
                    'max_daily_requests': 50,
                    'max_message_length': 1000,
                    'max_context_messages': 10,
                    'max_tokens_per_request': 5000
                },
                'usage_today': {
                    'requests_count': 10,
                    'total_tokens_used': 5000,
                    'total_cost_estimated': 0.5
                },
                'remaining_requests': 40
            })
            bot.admin_uc.ban_user = Mock(return_value=True)
            bot.admin_uc.unban_user = Mock(return_value=True)
            bot.admin_uc.set_user_limits = Mock(return_value=True)

            # 🔧 КРИТИЧЕСКИ ВАЖНО: Создаем мок для proactive_manager
            bot.proactive_manager = Mock()
            bot.proactive_manager.update_user_activity = Mock()

            bot.middleware = Mock()
            bot.middleware.create_user_from_telegram = Mock(return_value=Mock(
                user_id=123456,
                username="test_user",
                first_name="Test",
                last_name="User"
            ))

            # Мокаем асинхронные компоненты чтобы избежать запуска потоков
            bot._start_proactive_monitoring = Mock()
            bot._start_proactive_scheduler = Mock()
            bot._check_proactive_messages = Mock()

            yield bot

    @pytest.mark.asyncio
    async def test_bot_handles_valid_message(self, bot):
        """Тест: бот обрабатывает валидное сообщение"""
        # Создаем мок update
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.effective_user.username = "test_user"
        mock_update.effective_user.first_name = "Test"
        mock_update.effective_user.last_name = "User"
        mock_update.message = Mock()
        mock_update.message.text = "Привет, как дела?"
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Настраиваем моки для успешной обработки
        mock_user = Mock()
        mock_user.is_banned = False
        mock_user.is_active = True
        bot.user_repo.get_user.return_value = mock_user

        mock_profile = Mock()
        bot.profile_repo.get_profile.return_value = mock_profile

        # Выполняем обработку сообщения
        await bot.handle_message(mock_update, mock_context)

        # Проверяем что use case был вызван
        bot.handle_message_uc.execute.assert_called_once()

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("Это тестовый ответ")

        # Проверяем что активность пользователя была обновлена
        bot.proactive_manager.update_user_activity.assert_called_once_with(123456, "Привет, как дела?")

    @pytest.mark.asyncio
    async def test_admin_stats_command(self, bot):
        """Тест: команда /stats работает корректно"""
        # Настраиваем моки для админа
        bot.user_limits_repo.is_admin.return_value = True

        # Создаем мок update для команды /stats
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 111111  # Админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = ["123456"]  # user_id для статистики

        # Выполняем команду
        await bot.admin_stats(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once()

        # Проверяем что метод статистики был вызван
        bot.admin_uc.get_user_stats.assert_called_once_with(111111, 123456)

        # Проверяем что в ответе есть ожидаемые данные
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Статистика пользователя 123456" in call_args
        assert "test_user" in call_args
        assert "50" in call_args  # max_daily_requests

    @pytest.mark.asyncio
    async def test_admin_ban_command(self, bot):
        """Тест: команда /ban работает"""
        # Настраиваем моки для админа
        bot.user_limits_repo.is_admin.return_value = True

        # Создаем мок update для команды /ban
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 111111  # Админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = ["123456", "спам"]  # user_id и причина

        # Выполняем команду
        await bot.admin_ban(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("✅ Пользователь 123456 забанен.\nПричина: спам")

        # Проверяем что метод бана был вызван
        bot.admin_uc.ban_user.assert_called_once_with(111111, 123456, "спам")

    @pytest.mark.asyncio
    async def test_admin_unban_command(self, bot):
        """Тест: команда /unban работает"""
        # Настраиваем моки для админа
        bot.user_limits_repo.is_admin.return_value = True

        # Создаем мок update для команды /unban
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 111111  # Админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = ["123456"]  # user_id

        # Выполняем команду
        await bot.admin_unban(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("✅ Пользователь 123456 разбанен.")

        # Проверяем что метод разбана был вызван
        bot.admin_uc.unban_user.assert_called_once_with(111111, 123456)

    @pytest.mark.asyncio
    async def test_admin_set_limits_command(self, bot):
        """Тест: команда /limits работает"""
        # Настраиваем моки для админа
        bot.user_limits_repo.is_admin.return_value = True

        # Создаем мок update для команды /limits
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 111111  # Админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = ["123456", "100", "2000", "10", "5000"]  # user_id и лимиты

        # Выполняем команду
        await bot.admin_set_limits(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("✅ Лимиты для 123456 установлены.")

        # Проверяем что метод установки лимитов был вызван
        bot.admin_uc.set_user_limits.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_admin_cannot_use_admin_commands(self, bot):
        """Тест: не-админ не может использовать админ команды"""
        # Настраиваем моки для не-админа
        bot.user_limits_repo.is_admin.return_value = False

        # Создаем мок update для команды /stats
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 999999  # Не админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = ["123456"]

        # Выполняем команду
        await bot.admin_stats(mock_update, mock_context)

        # Проверяем что доступ запрещен
        mock_update.message.reply_text.assert_called_once_with("❌ Недостаточно прав.")

    @pytest.mark.asyncio
    async def test_start_command(self, bot):
        """Тест: команда /start работает"""
        # Создаем мок update для команды /start
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.effective_user.username = "test_user"
        mock_update.effective_user.first_name = "Test"
        mock_update.effective_user.last_name = "User"
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Выполняем команду
        await bot.start(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("Добро пожаловать!")

        # Проверяем что use case был вызван
        bot.start_conversation_uc.execute.assert_called_once_with(123456, "test_user", "Test", "User")

    @pytest.mark.asyncio
    async def test_profile_command(self, bot):
        """Тест: команда /profile работает"""
        # Создаем мок update для команды /profile
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Выполняем команду
        await bot.profile(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("Ваш профиль")

        # Проверяем что use case был вызван
        bot.manage_profile_uc.get_profile.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_memory_command(self, bot):
        """Тест: команда /memory работает"""
        # Создаем мок update для команды /memory
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Выполняем команду
        await bot.memory(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("Я помню о тебе...")

        # Проверяем что use case был вызван
        bot.manage_profile_uc.get_memory.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_reset_command(self, bot):
        """Тест: команда /reset работает"""
        # Создаем мок update для команды /reset
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Выполняем команду
        await bot.reset(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once_with("🧹 Давай начнем наш разговор заново! Как твои дела?")

        # Проверяем что конверсация была очищена
        bot.conversation_repo.clear_conversation.assert_called_once_with(123456)

    @pytest.mark.asyncio
    async def test_health_command(self, bot):
        """Тест: команда /health работает"""
        # Создаем мок update для команды /health
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Выполняем команду
        await bot.health(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once()

        # Проверяем что health check был выполнен
        bot.health_checker.perform_health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_help_command(self, bot):
        """Тест: команда /help работает"""
        # Создаем мок update для команды /help
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Выполняем команду
        await bot.help_command(mock_update, mock_context)

        # Проверяем что ответ был отправлен
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0][0]

        # 🔧 ИСПРАВЛЕНО: Проверяем актуальный текст помощи
        assert "💫 Я здесь чтобы быть твоим другом!" in call_args
        assert "/start" in call_args
        assert "/profile" in call_args
        assert "/memory" in call_args
        assert "/reset" in call_args
        assert "ИИ-помощник" in call_args

    @pytest.mark.asyncio
    async def test_banned_user_cannot_send_messages(self, bot):
        """Тест: забаненный пользователь не может отправлять сообщения"""
        # Создаем мок update
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 123456
        mock_update.effective_user.username = "banned_user"
        mock_update.effective_user.first_name = "Banned"
        mock_update.effective_user.last_name = "User"
        mock_update.message = Mock()
        mock_update.message.text = "Привет"
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()

        # Настраиваем моки для забаненного пользователя
        mock_user = Mock()
        mock_user.is_banned = True
        mock_user.is_active = True
        bot.user_repo.get_user.return_value = mock_user

        # 🔧 ИСПРАВЛЕНО: Настраиваем handle_message_uc чтобы он возвращал сообщение о бане
        bot.handle_message_uc.execute = AsyncMock(return_value="🔒 Ваш аккаунт заблокирован.")

        # Выполняем обработку сообщения
        await bot.handle_message(mock_update, mock_context)

        # 🔧 ИСПРАВЛЕНО: Проверяем что use case БЫЛ вызван (проверка бана происходит внутри него)
        bot.handle_message_uc.execute.assert_called_once()

        # Проверяем что отправлен ответ о бане
        mock_update.message.reply_text.assert_called_once_with("🔒 Ваш аккаунт заблокирован.")

    @pytest.mark.asyncio
    async def test_admin_stats_without_args_shows_usage(self, bot):
        """Тест: команда /stats без аргументов показывает usage"""
        # Настраиваем моки для админа
        bot.user_limits_repo.is_admin.return_value = True

        # Создаем мок update для команды /stats без аргументов
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 111111  # Админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = []  # Нет аргументов

        # Выполняем команду
        await bot.admin_stats(mock_update, mock_context)

        # Проверяем что показано сообщение об использовании
        mock_update.message.reply_text.assert_called_once_with("Использование: /stats <user_id>")

    @pytest.mark.asyncio
    async def test_admin_ban_without_args_shows_usage(self, bot):
        """Тест: команда /ban без аргументов показывает usage"""
        # Настраиваем моки для админа
        bot.user_limits_repo.is_admin.return_value = True

        # Создаем мок update для команды /ban без аргументов
        mock_update = Mock()
        mock_update.effective_user = Mock()
        mock_update.effective_user.id = 111111  # Админ
        mock_update.message = Mock()
        mock_update.message.reply_text = AsyncMock()

        mock_context = Mock()
        mock_context.args = []  # Нет аргументов

        # Выполняем команду
        await bot.admin_ban(mock_update, mock_context)

        # Проверяем что показано сообщение об использовании
        mock_update.message.reply_text.assert_called_once_with("Использование: /ban <user_id> [причина]")