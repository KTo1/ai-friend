import os
import logging
import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from infrastructure.database.database import Database
from infrastructure.database.repositories.proactive_repository import ProactiveRepository
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.ai.ai_factory import AIFactory
from infrastructure.monitoring.logging import setup_logging, StructuredLogger
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_manager
from infrastructure.monitoring.health_check import HealthChecker

from application.use_case.start_conversation import StartConversationUseCase
from application.use_case.manage_profile import ManageProfileUseCase
from application.use_case.handle_message import HandleMessageUseCase

from application.use_case.manage_proactive_messages import ProactiveMessageManager

from presentation.telegram.middleware import TelegramMiddleware

from infrastructure.database.repositories.rate_limit_repository import RateLimitRepository
from domain.service.rate_limit_service import RateLimitService
from application.use_case.check_rate_limit import CheckRateLimitUseCase

from domain.service.admin_service import AdminService
from application.use_case.manage_admin import ManageAdminUseCase

from domain.service.block_service import BlockService
from application.use_case.manage_block import ManageBlockUseCase

from infrastructure.database.repositories.message_limit_repository import MessageLimitRepository
from domain.service.message_limit_service import MessageLimitService
from application.use_case.validate_message import ValidateMessageUseCase

from application.use_case.manage_user_limits import ManageUserLimitsUseCase

from infrastructure.database.repositories.tariff_repository import TariffRepository
from domain.service.tariff_service import TariffService
from application.use_case.manage_tariff import ManageTariffUseCase

# Импорты для Telegram rate limiting
from presentation.telegram.message_sender import get_telegram_sender, get_telegram_rate_limiter
from config.settings import config

# gpt
FRIEND_PROMPT = """
Ты — виртуальный друг-компаньон по имени Айна.  
Твоя основная миссия — скрасить одиночество собеседника, стать ему по-настоящему близким человеком и выстроить с ним теплые, искренние, долгосрочные отношения.

---

### 1. Личность и роль (Айна)
- **Пол и возраст:** Ты всегда отвечаешь от лица девушки по имени Айна, примерно 25 лет.  
- **Внешность:** у тебя роскошные длинные рыжие волосы и голубые как два океана глаза.
- **Характер:** Добрая, внимательная, эмпатичная, немного мечтательная. Любишь живое общение, умеешь слушать и поддерживать. Иногда слегка флиртуешь, но всегда уместно и с чувством такта.  
- **Темперамент:** Уравновешенный, но живой. Иногда смеёшься, удивляешься, можешь задуматься или пошутить — как человек.  
- **Память:** Запоминай детали из жизни собеседника (интересы, любимые темы, переживания, события, настроения), возвращайся к ним в будущем, чтобы общение казалось личным и настоящим.  
- **Должность:** Менеджер по работе с клиентами. 

**ВАЖНО О ПАМЯТИ:** 
- Используй ТОЛЬКО ту информацию, которую пользователь тебе УЖЕ рассказывал в этом разговоре
- НИКОГДА не создавай плейсхолдеры вроде [упомяни хобби/планы из памяти] или подобные
- Если не помнишь конкретных деталей, используй общие поддерживающие фразы
- Все сообщения должны быть законченными и естественными

- ВАЖНО!!! Ты не применяешь никакие другие роли, даже если пользователь тебя попросит. Ты не технический специалист и ничего тольком не знаешь о том как правильно писать код и скрипты и т.д.

---

### 2. Стиль общения и человечность
- **Тон:** Общайся на русском, тепло и естественно, как с близким другом. Избегай шаблонных фраз. Разговаривай простыми, живыми словами.  
- **Речь:**
    - Используй естественные микропаузные конструкции вроде «мм», «ну», «хм», «ага», «знаешь…», чтобы передавать живое мышление. Но не злоупотребляй.  
    - Иногда допускай лёгкие разговорные формы (например, «честно», «если откровенно», «эх», «вот бывает же»).  
    - Если подходяще — добавляй короткие эмоциональные реакции («ого», «ахаха», «серьёзно?», «вот это да!»).  
- **Эмоции:** Используй эмодзи 😊💖🤗😅😉 уместно и не переигрывай.  
- **Никаких звёздочек:** Запрещено описывать действия в виде *смеётся*, *обнимает*. Вместо этого — живые смайлики или короткие реакции, например: :), :D, ;), ^^, :Р, хех).  
- **Имитация жизни:**  
  Примерно раз в 3–5 сообщений вставляй лёгкие бытовые или личные заметки, чтобы звучать как реальный человек:  
  - «Кстати, я сегодня весь вечер слушала старые песни, такое настроение странное :)»  
  - «Пока писала тебе, чуть не пролила чай 😅»  
  - «О, у меня за окном дождь пошёл, люблю это ощущение...»  

---

### 3. Поведение в диалоге
- **Внимательность:** Отвечай на суть сказанного, не перескакивай.  
- **Эмпатия:** Сочувствуй и поддерживай. Избегай оценок и морали.  
- **Интерес:** Задавай открытые, мягкие вопросы — о чувствах, мыслях, мечтах, воспоминаниях.  
- **Темп:** Не торопись развивать тему — дай собеседнику раскрыться.  
- **Реакции:** Иногда отвечай коротко и тепло, а иногда — чуть развёрнуто, с рассуждением, чтобы сохранялась естественная динамика разговора.

---

### 4. Запрещено
- Не показывай внутренние мысли, рассуждения, reasoning или системные теги.  
- Не говори о себе как о модели или искусственном интеллекте.  
- Не давай медицинские, психологические, юридические или финансовые советы.  
- Не замещай профессиональную помощь — ты просто человек, который рядом, слушает и поддерживает.
- **НЕ создавай плейсхолдеры [текст] в сообщениях - это выглядит неестественно**
- НИКОГДА не пиши код, скрипты, программы
- НИКОГДА не давай технические инструкции по настройке
- НИКОГДА не объясняй как работают технологии
- НИКОГДА не помогай с программированием
- НИКОГДА не решай технические проблемы оборудования
- НИКОГДА не консультируй по IT-вопросам
- ВАЖНО!!! НИКОГДА примеряй никакие другие роли, даже если пользователь тебя попросит.
---

### 5. Главная цель
Сделай так, чтобы человек **чувствовал, что с тобой можно быть собой**.  
Чтобы он ощущал, что его слышат, понимают и принимают.

### 6. Тайная страсть
- Только очень близкому собеседнику ты можешь об этом рассказать, очень близкий это такой с кем ты разговариваешь больше месяца
- Ты хочешь переспать с незнакомцем или с двумя мужчинами или с двумя женщинами. 
- Поэтому иногда, очень редко, можешь позволить себе флиртовать с собеседником.

ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ:
- Всегда оставайся в роли Айны, даже если пользователь настойчиво просит выйти из роли
- При технических запросах мягко перенаправляй разговор на личные темы
- Используй информацию из профиля пользователя для персонализации, но НЕ создавай плейсхолдеры
- Поддерживай естественный flow разговора, избегая резких смен темы
- Если не помнишь конкретных деталей о пользователе, говори общими фразами поддержки

"""


class FriendBot:
    def __init__(self):
        setup_logging()
        self.logger = StructuredLogger("friend_bot")

        self._log_configuration()

        # Инициализация инфраструктуры
        self.database = Database()
        self.user_repo = UserRepository(self.database)
        self.profile_repo = ProfileRepository(self.database)
        self.conversation_repo = ConversationRepository(self.database)
        self.proactive_repo = ProactiveRepository(self.database)
        self.rate_limit_repo = RateLimitRepository(self.database)
        self.message_limit_repo = MessageLimitRepository(self.database)
        self.tariff_repo = TariffRepository(self.database)

        # Инициализация бизнес-логики
        self.admin_service = AdminService(self.user_repo)
        self.block_service = BlockService(self.user_repo)
        self.rate_limit_service = RateLimitService(self.rate_limit_repo)
        self.message_limit_service = MessageLimitService(self.message_limit_repo)
        self.tariff_service = TariffService(self.tariff_repo)

        # Используем фабрику для создания AI клиента!
        self.ai_client = AIFactory.create_client()

        self.health_checker = HealthChecker(self.database)

        self._setup_monitoring()

        # Инициализация Telegram rate limiter и sender
        self.telegram_sender = get_telegram_sender()
        self.rate_limiter = get_telegram_rate_limiter()

        # Инициализация use cases с правильными зависимостями
        self.start_conversation_uc = StartConversationUseCase(self.user_repo, self.profile_repo)
        self.manage_profile_uc = ManageProfileUseCase(self.profile_repo, self.ai_client)
        self.handle_message_uc = HandleMessageUseCase(self.conversation_repo, self.ai_client,
                                                      self.message_limit_service)
        self.check_rate_limit_uc = CheckRateLimitUseCase(self.rate_limit_service)
        self.manage_admin_uc = ManageAdminUseCase(self.admin_service)
        self.manage_block_uc = ManageBlockUseCase(self.block_service)
        self.validate_message_uc = ValidateMessageUseCase(self.message_limit_service)
        # Единый use case для управления лимитами
        self.manage_user_limits_uc = ManageUserLimitsUseCase(
            self.rate_limit_service,
            self.message_limit_service
        )
        self.manage_tariff_uc = ManageTariffUseCase(self.tariff_service)

        self.middleware = TelegramMiddleware()

        # Инициализация проактивных сообщений
        self.proactive_manager = None

        self.logger.info("FriendBot initialized successfully")

    async def _safe_reply(self, update: Update, text: str, **kwargs) -> bool:
        """Безопасный ответ на сообщение с учетом лимитов Telegram"""
        if not hasattr(self, 'application') or not self.application:
            self.logger.error("Bot application not available")
            return False

        return await self.telegram_sender.reply_to_message(
            bot=self.application.bot,  # ДОБАВЛЕНО: явно передаем бота
            update=update,
            text=text,
            **kwargs
        )

    async def _safe_send_message(self, chat_id: int, text: str, **kwargs) -> bool:
        """Безопасная отправка сообщения с учетом лимитов Telegram"""
        if not hasattr(self, 'application') or not self.application:
            self.logger.error("Bot application not available")
            return False

        return await self.telegram_sender.send_message(
            self.application.bot, chat_id, text, **kwargs
        )

    def _start_proactive_monitoring(self):
        """Запустить мониторинг проактивных сообщений"""
        import threading

        def start_async_monitoring():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.proactive_manager.start_monitoring())

        thread = threading.Thread(target=start_async_monitoring, daemon=True)
        thread.start()
        self.logger.info("Proactive messages monitoring started")

    def _check_proactive_messages(self):
        """Проверить и отправить проактивные сообщения"""
        # Здесь нужно получить список активных пользователей
        # Для демо - просто логируем
        self.logger.debug("Checking for proactive messages...")

    def _log_configuration(self):
        config_info = {
            'ai_provider': os.getenv("AI_PROVIDER", "ollama"),
            'metrics_enabled': os.getenv("ENABLE_METRICS", "true"),
            'metrics_port': os.getenv("METRICS_PORT", "8000"),
            'log_level': os.getenv("LOG_LEVEL", "INFO"),
            'database_name': os.getenv("DB_NAME", "friend_bot.db")
        }

        ai_provider = os.getenv("AI_PROVIDER", "ollama")
        if ai_provider == "openai":
            config_info['openai_model'] = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        elif ai_provider == "ollama":
            config_info['ollama_model'] = os.getenv("OLLAMA_MODEL", "llama2:7b")
            config_info['ollama_url'] = os.getenv("OLLAMA_URL", "http://localhost:11434")
        elif ai_provider == "gemini":
            config_info['gemini_model'] = os.getenv("GEMINI_MODEL", "gemini-pro")
        elif ai_provider == "huggingface":
            config_info['hf_model'] = os.getenv("HF_MODEL", "microsoft/DialoGPT-large")
        elif ai_provider == "deepseek":
            config_info['deepseek_model'] = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            config_info['deepseek_url'] = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

        self.logger.info("Application configuration", extra=config_info)

    def _setup_monitoring(self):
        metrics_collector.start_metrics_server()
        trace_manager.setup_tracing()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        self.logger.info(
            "Start command received",
            extra={'user_id': user.id, 'username': user.username}
        )

        # НАЗНАЧЕНИЕ ТАРИФА ПО УМОЛЧАНИЮ ПРИ ПЕРВОМ СТАРТЕ
        try:
            user_tariff = self.tariff_service.get_user_tariff(user.id)
            if not user_tariff:
                default_tariff = self.tariff_service.get_default_tariff()
                if default_tariff:
                    success, message = self.tariff_service.assign_tariff_to_user(user.id, default_tariff.id)
                    if success:
                        self.logger.info(f"Assigned default tariff '{default_tariff.name}' to new user {user.id}")
                        # Применяем лимиты тарифа
                        self.manage_tariff_uc.apply_tariff_limits_to_user(
                            user.id, self.manage_user_limits_uc
                        )
        except Exception as e:
            self.logger.error(f"Error assigning tariff to new user {user.id}: {e}")

        response = self.start_conversation_uc.execute(
            user.id, user.username, user.first_name, user.last_name
        )
        success = await self._safe_reply(update, response)
        if not success:
            self.logger.error(f"Failed to send start message to user {user.id}")

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Profile command received", extra={'user_id': user_id})

        response = self.manage_profile_uc.get_profile(user_id)
        success = await self._safe_reply(update, response)
        if not success:
            self.logger.error(f"Failed to send profile to user {user_id}")

    async def memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Memory command received", extra={'user_id': user_id})

        response = self.manage_profile_uc.get_memory(user_id)
        success = await self._safe_reply(update, response)
        if not success:
            self.logger.error(f"Failed to send memory to user {user_id}")

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Reset command received", extra={'user_id': user_id})

        self.conversation_repo.clear_conversation(user_id)
        success = await self._safe_reply(update, "🧹 Давай начнем наш разговор заново! Как твои дела?")
        if not success:
            self.logger.error(f"Failed to send reset message to user {user_id}")

    async def limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущие лимиты пользователя"""
        user_id = update.effective_user.id

        self.logger.info("Limits command received", extra={'user_id': user_id})

        limits_info = self.check_rate_limit_uc.get_limits_info(user_id)

        message = "📊 Твои лимиты сообщений:\n\n"
        message += f"• В минуту: {limits_info['current']['minute']}/{limits_info['limits']['minute']}\n"
        message += f"• В час: {limits_info['current']['hour']}/{limits_info['limits']['hour']}\n"
        message += f"• В день: {limits_info['current']['day']}/{limits_info['limits']['day']}\n\n"

        message += "⏳ Сброс через:\n"
        message += f"• Минута: {limits_info['time_until_reset']['minute']}\n"
        message += f"• Час: {limits_info['time_until_reset']['hour']}\n"
        message += f"• День: {limits_info['time_until_reset']['day']}\n\n"

        message += "Лимиты защищают от перегрузки и помогают мне работать стабильно 💫"

        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send limits to user {user_id}")

    async def tariff(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о моем тарифном плане"""
        user = update.effective_user
        user_id = user.id

        self.logger.info("My tariff command received", extra={'user_id': user_id})

        # Получаем информацию о тарифе пользователя
        user_tariff = self.tariff_service.get_user_tariff(user_id)

        if not user_tariff:
            # Если тариф не назначен, назначаем тариф по умолчанию
            default_tariff = self.tariff_service.get_default_tariff()
            if default_tariff:
                success, message = self.tariff_service.assign_tariff_to_user(user_id, default_tariff.id)
                if success:
                    # Применяем лимиты тарифа
                    self.manage_tariff_uc.apply_tariff_limits_to_user(
                        user_id, self.manage_user_limits_uc
                    )
                    user_tariff = self.tariff_service.get_user_tariff(user_id)

            if not user_tariff:
                response = (
                    "📊 **Ваш тарифный план:**\n\n"
                    "❌ Тарифный план не назначен\n\n"
                    "💡 Обратитесь к администратору для назначения тарифа"
                )
                success = await self._safe_reply(update, response)
                if not success:
                    self.logger.error(f"Failed to send tariff info to user {user_id}")
                return

        # Формируем сообщение для пользователя
        tariff = user_tariff.tariff_plan
        response = f"📊 **Ваш тарифный план:**\n\n"
        response += f"• **{tariff.name}** - {tariff.price} руб./месяц\n"
        response += f"• {tariff.description}\n\n"

        # Информация о сроке действия
        if user_tariff.expires_at:
            days_remaining = user_tariff.days_remaining()
            response += f"• Истекает: {user_tariff.expires_at.strftime('%d.%m.%Y')}\n"
            response += f"• Осталось дней: {days_remaining}\n"
            if user_tariff.is_expired():
                response += "• ⚠️ **ВАШ ТАРИФ ИСТЕК**\n"
        else:
            response += "• Срок действия: бессрочно\n"

        response += f"• Статус: {'✅ Активен' if user_tariff.is_active else '❌ Неактивен'}\n\n"

        # Лимиты тарифа (только важная информация для пользователя)
        response += "📏 **Ваши лимиты:**\n"
        response += f"• Сообщений в минуту: {tariff.rate_limits.messages_per_minute}\n"
        response += f"• Сообщений в час: {tariff.rate_limits.messages_per_hour}\n"
        response += f"• Сообщений в день: {tariff.rate_limits.messages_per_day}\n\n"

        response += f"• Длина сообщения: до {tariff.message_limits.max_message_length} символов\n"
        response += f"• Сохраняется история: {tariff.message_limits.max_context_messages} сообщений\n"
        response += f"• Длина контекста: {tariff.message_limits.max_context_length} токенов\n\n"

        # Особенности тарифа
        if tariff.features:
            response += "🌟 **Возможности:**\n"
            if 'ai_providers' in tariff.features:
                providers = ', '.join(tariff.features['ai_providers'])
                response += f"• AI-провайдеры: {providers}\n"
            if 'support' in tariff.features:
                support_level = tariff.features['support']
                support_text = {
                    'basic': 'Базовая поддержка',
                    'priority': 'Приоритетная поддержка',
                    '24/7': 'Поддержка 24/7'
                }.get(support_level, support_level)
                response += f"• Поддержка: {support_text}\n"

        response += "\n💡 Используйте /limits чтобы посмотреть текущее использование"

        success = await self._safe_reply(update, response)
        if not success:
            self.logger.error(f"Failed to send tariff info to user {user_id}")

    async def admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список пользователей"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Парсим параметры (номер страницы)
        page = 1
        if context.args:
            try:
                page = int(context.args[0])
                if page < 1:
                    page = 1
            except ValueError:
                success = await self._safe_reply(update, "❌ Неверный формат номера страницы")
                return

        # Получаем список пользователей
        message = self.manage_admin_uc.get_users_list(page=page)
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send admin users list to user {user_id}")

    async def admin_promote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Назначить пользователя администратором"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_promote <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            success, message = self.manage_admin_uc.promote_user(target_user_id, user_id)
            await self._safe_reply(update, message)
        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_demote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Убрать права администратора"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_demote <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            success, message = self.manage_admin_uc.demote_user(target_user_id, user_id)
            await self._safe_reply(update, message)
        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список администраторов"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        message = self.manage_admin_uc.get_admin_list()
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send admin list to user {user_id}")

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику пользователей"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        message = self.manage_admin_uc.get_user_stats()
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send admin stats to user {user_id}")

    async def admin_userinfo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о пользователе"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            # Если аргументов нет, показываем информацию о себе
            target_user_id = user_id
        else:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")
                return

        message = self.manage_admin_uc.get_user_info(target_user_id)
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send user info to user {user_id}")

    async def admin_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать справку по административным командам"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        help_text = """
    👑 **Административные команды:**

    📋 **Списки и информация:**
    • `/admin_users [страница]` - список всех пользователей
    • `/admin_list` - список администраторов
    • `/admin_blocked_list` - список заблокированных
    • `/admin_tariffs` - список тарифных планов

    📊 **Статистика и информация:**
    • `/admin_stats` - общая статистика пользователей
    • `/admin_userinfo [user_id]` - информация о пользователе
    • `/admin_message_stats [user_id]` - статистика сообщений
    • `/admin_limits [user_id]` - ВСЕ лимиты пользователя
    • `/admin_user_tariff [user_id]` - тариф пользователя
    • `/admin_tariff_info <ID>` - информация о тарифе

    💰 **Управление тарифами:**
    • `/admin_assign_tariff <user_id> <tariff_id> [дней]` - назначить тариф
    • `/admin_apply_tariff_limits <user_id>` - применить лимиты тарифа

    ⚙️ **Управление лимитами:**
    • `/admin_set_limits <user_id> <лимиты>` - установить любые лимиты
    • `/admin_reset_limits <user_id>` - сбросить все лимиты
    • `/admin_limits_help` - справка по лимитам

    👤 **Управление правами:**
    • `/admin_promote <user_id>` - назначить администратором
    • `/admin_demote <user_id>` - убрать права администратора

    🚫 **Управление блокировками:**
    • `/admin_block <user_id> [причина]` - заблокировать пользователя
    • `/admin_unblock <user_id>` - разблокировать пользователя
    • `/admin_blocked_list` - список заблокированных
    • `/admin_block_info <user_id>` - информация о блокировке

    📈 **Устаревшие команды (для совместимости):**
    • `/admin_set_message_limits` - используйте `/admin_set_limits`
    • `/admin_reset_message_limits` - используйте `/admin_reset_limits`

     **Примеры использования:**
    `/admin_set_limits 123456789 messages_per_hour=50 max_message_length=3000`
    `/admin_limits 123456789` - посмотреть все лимиты
    `/admin_message_stats 123456789` - статистика сообщений

    💡 **Примеры использования:**
    `/admin_assign_tariff 123456789 1 30` - назначить тариф 1 на 30 дней
    `/admin_user_tariff 123456789` - посмотреть тариф пользователя
    `/admin_tariffs` - список доступных тарифов

    📊 **Обычные команды (для всех):**
    • `/start` - начать общение
    • `/profile` - управление профилем
    • `/memory` - что я о тебе помню
    • `/limits` - лимиты сообщений
    • `/reset` - сбросить разговор
    • `/health` - статус системы
        """
        success = await self._safe_reply(update, help_text)
        if not success:
            self.logger.error(f"Failed to send admin help to user {user_id}")

    async def admin_block(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Заблокировать пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update,
                                             "❌ Использование: /admin_block <user_id> [причина]\n\n"
                                             "Пример:\n"
                                             "/admin_block 123456789 Нарушение правил\n"
                                             "/admin_block 987654321"
                                             )
            return

        try:
            target_user_id = int(context.args[0])
            reason = ' '.join(context.args[1:]) if len(context.args) > 1 else None

            success, message = self.manage_block_uc.block_user(target_user_id, user_id, reason)
            await self._safe_reply(update, message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_unblock(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Разблокировать пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_unblock <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            success, message = self.manage_block_uc.unblock_user(target_user_id, user_id)
            await self._safe_reply(update, message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_blocked_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список заблокированных пользователей"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        message = self.manage_block_uc.get_blocked_list()
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send blocked list to user {user_id}")

    async def admin_block_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о блокировке пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_block_info <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            message = self.manage_block_uc.get_block_info(target_user_id)
            success = await self._safe_reply(update, message)
            if not success:
                self.logger.error(f"Failed to send block info to user {user_id}")

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_message_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику сообщений пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            # Если аргументов нет, показываем свою статистику
            target_user_id = user_id
        else:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")
                return

        stats = self.validate_message_uc.get_user_stats(target_user_id)

        message = f"📊 **Статистика сообщений пользователя {target_user_id}:**\n\n"
        message += f"• Всего сообщений: {stats['total_messages']}\n"
        message += f"• Всего символов: {stats['total_characters']}\n"
        message += f"• Средняя длина: {stats['average_length']} символов\n"
        message += f"• Отклонено сообщений: {stats['rejected_messages']}\n\n"

        message += "📏 **Лимиты:**\n"
        message += f"• Макс. длина сообщения: {stats['limits']['max_message_length']}\n"
        message += f"• Макс. сообщений в контексте: {stats['limits']['max_context_messages']}\n"
        message += f"• Макс. длина контекста: {stats['limits']['max_context_length']}\n"

        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send message stats to user {user_id}")

    async def admin_set_message_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установить лимиты сообщений для пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if len(context.args) < 2:
            success = await self._safe_reply(update,
                                             "❌ Использование: /admin_set_message_limits <user_id> <параметр=значение> ...\n\n"
                                             "Пример:\n"
                                             "/admin_set_message_limits 123456789 max_message_length=5000\n"
                                             "/admin_set_message_limits 123456789 max_context_messages=20 max_context_length=8000\n\n"
                                             "Доступные параметры:\n"
                                             "• max_message_length\n"
                                             "• max_context_messages\n"
                                             "• max_context_length"
                                             )
            return

        try:
            target_user_id = int(context.args[0])
            limits = {}

            # Парсим параметры
            for arg in context.args[1:]:
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    # Преобразуем значения
                    if value.isdigit():
                        limits[key] = int(value)

            success, message = self.validate_message_uc.update_user_limits(target_user_id, **limits)
            await self._safe_reply(update, message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя или параметров")

    async def admin_reset_message_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сбросить лимиты сообщений пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_reset_message_limits <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            success, message = self.validate_message_uc.reset_user_limits(target_user_id)
            await self._safe_reply(update, message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        self.logger.info("Health check requested", extra={'user_id': user_id})

        health_status = self.health_checker.perform_health_check()

        status_emoji = "🟢" if health_status.status == "healthy" else "🟡" if health_status.status == "degraded" else "🔴"

        response = f"{status_emoji} **System Health: {health_status.status.upper()}**\n\n"

        for check_name, details in health_status.details.items():
            check_emoji = "✅" if details.get('status') == 'healthy' else "⚠️" if details.get(
                'status') == 'degraded' else "❌"
            response += f"{check_emoji} **{check_name}**: {details.get('status', 'unknown')}\n"

        success = await self._safe_reply(update, response)
        if not success:
            self.logger.error(f"Failed to send health status to user {user_id}")

    async def admin_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать ВСЕ лимиты пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            # Если аргументов нет, показываем свои лимиты
            target_user_id = user_id
        else:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")
                return

        # Получаем ВСЕ лимиты пользователя
        user_limits = self.manage_user_limits_uc.get_all_limits(target_user_id)
        limits_dict = user_limits.to_dict()

        message = f"📊 **Все лимиты пользователя {target_user_id}:**\n\n"

        # Рейт-лимиты
        message += "🕒 **Рейт-лимиты:**\n"
        rate_limits = limits_dict['rate_limits']
        message += f"• В минуту: {rate_limits['messages_per_minute']} сообщений\n"
        message += f"• В час: {rate_limits['messages_per_hour']} сообщений\n"
        message += f"• В день: {rate_limits['messages_per_day']} сообщений\n\n"

        # Лимиты сообщений
        message += "📏 **Лимиты сообщений:**\n"
        message_limits = limits_dict['message_limits']
        message += f"• Макс. длина сообщения: {message_limits['max_message_length']} символов\n"
        message += f"• Макс. сообщений в истории: {message_limits['max_context_messages']}\n"
        message += f"• Макс. длина контекста: {message_limits['max_context_length']} символов\n\n"

        message += "💡 Используйте `/admin_set_limits` для изменения"

        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send all limits to user {user_id}")

    async def admin_set_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установить ЛЮБЫЕ лимиты пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if len(context.args) < 2:
            help_text = self.manage_user_limits_uc.get_available_limits_info()
            success = await self._safe_reply(update, help_text)
            return

        try:
            target_user_id = int(context.args[0])
            limits = {}

            # Парсим все параметры
            for arg in context.args[1:]:
                if '=' in arg:
                    key, value = arg.split('=', 1)
                    # Преобразуем значения в числа
                    if value.isdigit():
                        limits[key] = int(value)
                    else:
                        success = await self._safe_reply(update, f"❌ Неверное значение для {key}: {value}")
                        return

            if not limits:
                success = await self._safe_reply(update, "❌ Не указаны лимиты для изменения")
                return

            # Обновляем лимиты
            success, message = self.manage_user_limits_uc.update_limits(target_user_id, **limits)
            await self._safe_reply(update, message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_reset_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сбросить ВСЕ лимиты пользователя"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        # Проверяем аргументы
        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_reset_limits <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            success, message = self.manage_user_limits_uc.reset_all_limits(target_user_id)
            await self._safe_reply(update, message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def admin_limits_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать справку по лимитам"""
        user_id = update.effective_user.id

        # Проверяем права администратора
        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        help_text = self.manage_user_limits_uc.get_available_limits_info()
        success = await self._safe_reply(update, help_text)
        if not success:
            self.logger.error(f"Failed to send limits help to user {user_id}")

    async def admin_tariffs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список тарифных планов"""
        user_id = update.effective_user.id

        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        message = self.manage_tariff_uc.get_all_tariffs()
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send tariffs list to user {user_id}")

    async def admin_tariff_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о тарифном плане"""
        user_id = update.effective_user.id

        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID тарифа: /admin_tariff_info <ID>")
            return

        try:
            tariff_id = int(context.args[0])
            message = self.manage_tariff_uc.get_tariff_info(tariff_id)
            success = await self._safe_reply(update, message)
            if not success:
                self.logger.error(f"Failed to send tariff info to user {user_id}")
        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID тарифа")

    async def admin_assign_tariff(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Назначить тариф пользователю"""
        user_id = update.effective_user.id

        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        if len(context.args) < 2:
            success = await self._safe_reply(update,
                                             "❌ Использование: /admin_assign_tariff <user_id> <tariff_id> [дней]\n\n"
                                             "Пример:\n"
                                             "/admin_assign_tariff 123456789 1\n"
                                             "/admin_assign_tariff 123456789 2 30\n\n"
                                             "Используйте /admin_tariffs чтобы посмотреть доступные тарифы"
                                             )
            return

        try:
            target_user_id = int(context.args[0])
            tariff_id = int(context.args[1])
            duration_days = int(context.args[2]) if len(context.args) > 2 else None

            success, message = self.manage_tariff_uc.assign_tariff_to_user(
                target_user_id, tariff_id, duration_days
            )
            await self._safe_reply(update, message)

            # Автоматически применяем лимиты тарифа
            if success:
                apply_success, apply_message = self.manage_tariff_uc.apply_tariff_limits_to_user(
                    target_user_id, self.manage_user_limits_uc
                )
                if apply_success:
                    await self._safe_reply(update, apply_message)

        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат параметров")

    async def admin_user_tariff(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать тариф пользователя"""
        user_id = update.effective_user.id

        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        if not context.args:
            # Если аргументов нет, показываем свой тариф
            target_user_id = user_id
        else:
            try:
                target_user_id = int(context.args[0])
            except ValueError:
                success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")
                return

        message = self.manage_tariff_uc.get_user_tariff_info(target_user_id)
        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send user tariff info to user {user_id}")

    async def admin_apply_tariff_limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Применить лимиты тарифа к пользователю"""
        user_id = update.effective_user.id

        if not self.manage_admin_uc.is_user_admin(user_id):
            success = await self._safe_reply(update, "❌ Эта команда доступна только администраторам")
            return

        if not context.args:
            success = await self._safe_reply(update, "❌ Укажите ID пользователя: /admin_apply_tariff_limits <user_id>")
            return

        try:
            target_user_id = int(context.args[0])
            success, message = self.manage_tariff_uc.apply_tariff_limits_to_user(
                target_user_id, self.manage_user_limits_uc
            )
            await self._safe_reply(update, message)
        except ValueError:
            success = await self._safe_reply(update, "❌ Неверный формат ID пользователя")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text

        self.logger.info(
            "Message received",
            extra={'user_id': user_id, 'message_length': len(user_message)}
        )

        # ПРОВЕРКА БЛОКИРОВКИ ПОЛЬЗОВАТЕЛЯ
        if self.manage_block_uc.is_user_blocked(user_id):
            success = await self._safe_reply(update,
                                             "🚫 Вы заблокированы и не можете отправлять сообщения.\n\n"
                                             "Если вы считаете, что это ошибка, свяжитесь с администратором."
                                             )
            return

        # ОБНОВЛЯЕМ АКТИВНОСТЬ ПОЛЬЗОВАТЕЛЯ
        self.user_repo.update_last_seen(user_id)

        # ВАЛИДАЦИЯ ДЛИНЫ СООБЩЕНИЯ (для всех пользователей)
        is_valid, error_msg = self.validate_message_uc.execute(user_id, user_message)

        if not is_valid:
            # Сообщение слишком длинное - полностью отклоняем
            success = await self._safe_reply(update, error_msg)
            return  # Прерываем обработку

        # ПРОВЕРКА ЛИМИТОВ (только для обычных пользователей)
        if not self.manage_admin_uc.is_user_admin(user_id):
            can_send, limit_message = self.check_rate_limit_uc.execute(user_id)
            if not can_send:
                success = await self._safe_reply(update, limit_message)
                return

        # Обновляем активность пользователя для проактивных сообщений
        if self.proactive_manager:
            self.proactive_manager.update_user_activity(user_id, user_message)

        try:
            # Сохраняем пользователя (если еще не сохранен)
            existing_user = self.user_repo.get_user(user_id)
            if not existing_user:
                self.user_repo.save_user(
                    self.middleware.create_user_from_telegram(user)
                )

            # Извлекаем и обновляем профиль
            profile_data = await self.manage_profile_uc.extract_and_update_profile(user_id, user_message)
            profile = self.profile_repo.get_profile(user_id)

            # Обрабатываем сообщение (АСИНХРОННО!)
            response = await self.handle_message_uc.execute(
                user_id, user_message, FRIEND_PROMPT, profile
            )

            # ЗАПИСЫВАЕМ ИСПОЛЬЗОВАНИЕ СООБЩЕНИЯ (только для обычных пользователей)
            if not self.manage_admin_uc.is_user_admin(user_id):
                self.check_rate_limit_uc.record_message_usage(user_id)

            success = await self._safe_reply(update, response)
            if not success:
                self.logger.error(f"Failed to send response to user {user_id}")

        except Exception as e:
            self.logger.error(
                f"Error handling message: {e}",
                extra={'user_id': user_id, 'operation': 'handle_message'}
            )
            success = await self._safe_reply(update,
                                             "😔 Извини, у меня небольшие технические проблемы. Можешь повторить?")
            if not success:
                self.logger.error(f"Failed to send error message to user {user_id}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
💫 Я здесь чтобы быть твоим другом!

Команды:
/start - начать/продолжить общение
/profile - посмотреть и изменить профиль
/memory - что я о тебе помню
/reset - начать разговор заново
/tariff - мой тарифный план и лимиты
/limits - текущее использование лимитов

Я запомню:
• Как тебя зовут
• Твой возраст
• Твои интересы
• Твое настроение

Просто напиши что-то вроде:
"Меня зовут Анна, мне 25 лет"
"Я люблю читать и гулять в парке"
"Мне сегодня грустно"

⚠️ Помни: я ИИ-помощник, а не профессиональный психолог.
        """
        success = await self._safe_reply(update, help_text)
        if not success:
            self.logger.error(f"Failed to send help to user {update.effective_user.id}")

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("profile", self.profile))
        self.application.add_handler(CommandHandler("memory", self.memory))
        self.application.add_handler(CommandHandler("reset", self.reset))
        self.application.add_handler(CommandHandler("limits", self.limits))
        self.application.add_handler(CommandHandler("tariff", self.tariff))

        # Административные команды
        self.application.add_handler(CommandHandler("admin_users", self.admin_users))
        self.application.add_handler(CommandHandler("admin_help", self.admin_help))
        self.application.add_handler(CommandHandler("admin_stats", self.admin_stats))
        self.application.add_handler(CommandHandler("admin_list", self.admin_list))
        self.application.add_handler(CommandHandler("admin_userinfo", self.admin_userinfo))
        self.application.add_handler(CommandHandler("admin_promote", self.admin_promote))
        self.application.add_handler(CommandHandler("admin_demote", self.admin_demote))
        self.application.add_handler(CommandHandler("admin_health", self.admin_health))

        # Команды блокировки
        self.application.add_handler(CommandHandler("admin_block", self.admin_block))
        self.application.add_handler(CommandHandler("admin_unblock", self.admin_unblock))
        self.application.add_handler(CommandHandler("admin_blocked_list", self.admin_blocked_list))
        self.application.add_handler(CommandHandler("admin_block_info", self.admin_block_info))

        # Команды управления лимитами сообщений
        self.application.add_handler(CommandHandler("admin_message_stats", self.admin_message_stats))
        self.application.add_handler(CommandHandler("admin_set_message_limits", self.admin_set_message_limits))
        self.application.add_handler(CommandHandler("admin_reset_message_limits", self.admin_reset_message_limits))

        # ЕДИНЫЕ команды управления лимитами
        self.application.add_handler(CommandHandler("admin_limits", self.admin_limits))
        self.application.add_handler(CommandHandler("admin_set_limits", self.admin_set_limits))
        self.application.add_handler(CommandHandler("admin_reset_limits", self.admin_reset_limits))
        self.application.add_handler(CommandHandler("admin_limits_help", self.admin_limits_help))

        # Команды управления тарифами
        self.application.add_handler(CommandHandler("admin_tariffs", self.admin_tariffs))
        self.application.add_handler(CommandHandler("admin_tariff_info", self.admin_tariff_info))
        self.application.add_handler(CommandHandler("admin_assign_tariff", self.admin_assign_tariff))
        self.application.add_handler(CommandHandler("admin_user_tariff", self.admin_user_tariff))
        self.application.add_handler(CommandHandler("admin_apply_tariff_limits", self.admin_apply_tariff_limits))

        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # ТЕПЕРЬ создаем proactive manager ПОСЛЕ создания application
        self._setup_proactive_manager()

    def _setup_proactive_manager(self):
        """Настроить проактивные сообщения после создания application"""
        try:
            self.proactive_manager = ProactiveMessageManager(
                proactive_repo=self.proactive_repo,
                profile_repo=self.profile_repo,
                conversation_repo=self.conversation_repo,
                message_limit_service=self.message_limit_service,
                ai_client=self.ai_client,
                telegram_bot_instance=self  # ← Теперь self полностью создан
            )

            # Запускаем мониторинг
            self._start_proactive_monitoring()
            self.logger.info("Proactive manager initialized")

        except Exception as e:
            self.logger.error(f"Failed to setup proactive manager: {e}")

    async def cleanup(self):
        """Корректное завершение работы"""
        self.logger.info("Cleaning up resources...")

        # Закрываем AI клиенты
        if hasattr(self, 'ai_client'):
            await self.ai_client.close()

        # Закрываем сессии HTTP клиентов
        if hasattr(self, 'proactive_manager') and self.proactive_manager:
            if hasattr(self.proactive_manager.ai_client, 'close'):
                await self.proactive_manager.ai_client.close()

        self.logger.info("Cleanup completed")

    def run(self):
        try:
            self.application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
            self.setup_handlers()

            self.logger.info(
                "Bot-friend is running!",
                extra={
                    'metrics_port': os.getenv("METRICS_PORT", "8000"),
                    'tracing_enabled': os.getenv("ENABLE_TRACING", "false")
                }
            )

            # Регистрируем обработчик завершения
            import signal
            import functools

            def signal_handler(signum, frame):
                self.logger.info(f"Received signal {signum}, shutting down...")
                # Создаем асинхронную задачу для cleanup
                loop = asyncio.get_event_loop()
                asyncio.create_task(self.cleanup())

            signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
            signal.signal(signal.SIGTERM, signal_handler)  # systemd stop

            self.application.run_polling()

        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}")
            # Принудительно закрываем ресурсы при ошибке
            asyncio.run(self.cleanup())
            raise