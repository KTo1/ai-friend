import os
import asyncio

import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from presentation.telegram.middleware import TelegramMiddleware

from domain.entity.character import Character

from infrastructure.database.database import Database
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.database.repositories.tariff_repository import TariffRepository
from infrastructure.database.repositories.rag_repository import RAGRepository
from infrastructure.database.repositories.user_stats_repository import UserStatsRepository
from infrastructure.database.repositories.rate_limit_tracking_repository import RateLimitTrackingRepository
from infrastructure.database.repositories.character_repository import CharacterRepository

from infrastructure.ai.ai_factory import AIFactory
from infrastructure.monitoring.logging import setup_logging, StructuredLogger
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_manager
from infrastructure.monitoring.health_check import HealthChecker

from application.use_case.start_conversation import StartConversationUseCase
from application.use_case.manage_profile import ManageProfileUseCase
from application.use_case.handle_message import HandleMessageUseCase

from domain.service.admin_service import AdminService
from domain.service.block_service import BlockService
from domain.service.tariff_service import TariffService
from domain.service.rag_service import RAGService
from domain.service.limit_service import LimitService

from application.use_case.manage_admin import ManageAdminUseCase
from application.use_case.manage_block import ManageBlockUseCase
from application.use_case.manage_user_limits import ManageUserLimitsUseCase
from application.use_case.manage_tariff import ManageTariffUseCase
from application.use_case.manage_rag import ManageRAGUseCase
from application.use_case.check_limits import CheckLimitsUseCase
from application.use_case.manage_character import ManageCharacterUseCase

# Импорты для Telegram rate limiting
from presentation.telegram.message_sender import get_telegram_sender, get_telegram_rate_limiter

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
        self.application = None
        self._setup_logging()
        self._log_configuration()

        self._setup_monitoring()

        # Инициализация инфраструктуры
        self.database = Database()
        self.user_repo = UserRepository(self.database)
        self.profile_repo = ProfileRepository(self.database)
        self.conversation_repo = ConversationRepository(self.database)
        self.tariff_repo = TariffRepository(self.database)
        self.rag_repo = RAGRepository(self.database)
        self.user_stats_repo = UserStatsRepository(self.database)
        self.rate_limit_tracking_repo = RateLimitTrackingRepository(self.database)
        self.character_repo = CharacterRepository(self.database)

        # Используем фабрику для создания AI клиента!
        self.ai_client = AIFactory.create_client()

        # Инициализация бизнес-логики
        self.admin_service = AdminService(self.user_repo)
        self.block_service = BlockService(self.user_repo)
        self.tariff_service = TariffService(self.tariff_repo)
        self.rag_service = RAGService(self.ai_client)
        self.limit_service = LimitService(
            self.rate_limit_tracking_repo,
            self.user_stats_repo
        )

        self.health_checker = HealthChecker(self.database)

        # Инициализация Telegram rate limiter и sender
        self.telegram_sender = get_telegram_sender()
        self.rate_limiter = get_telegram_rate_limiter()

        # Инициализация use cases с правильными зависимостями
        self.start_conversation_uc = StartConversationUseCase(self.user_repo, self.profile_repo, self.tariff_service)
        self.manage_profile_uc = ManageProfileUseCase(self.profile_repo, self.ai_client)
        self.handle_message_uc = HandleMessageUseCase(self.conversation_repo, self.character_repo, self.ai_client)
        self.manage_admin_uc = ManageAdminUseCase(self.admin_service)
        self.manage_block_uc = ManageBlockUseCase(self.block_service)
        self.manage_user_limits_uc = ManageUserLimitsUseCase(self.user_stats_repo)
        self.manage_tariff_uc = ManageTariffUseCase(self.tariff_service)
        self.manage_rag_uc = ManageRAGUseCase(self.rag_repo, self.rag_service)
        self.check_limits_uc = CheckLimitsUseCase(self.limit_service)
        self.manage_character_uc = ManageCharacterUseCase(self.character_repo, self.user_repo)

        self.middleware = TelegramMiddleware()

        self.user_character_selections = {}  # {user_id: {'page': 0, 'characters': []}}

        self.logger.info("FriendBot initialized successfully")

    async def show_character_carousel(self, update: Update, page: int = 0):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        characters = self.manage_character_uc.get_all_characters()
        if not characters:
            await self._safe_reply(update, '❌ Нет доступных персонажей')
            return

        # Один персонаж на страницу
        total_pages = len(characters)
        page = max(0, min(page, total_pages - 1))

        # Получаем текущего персонажа для страницы
        character = characters[page]

        # Сохраняем состояние для пользователя
        self.user_character_selections[user_id] = {
            'page': page,
            'characters': characters
        }

        # Создаем инлайн-клавиатуру
        keyboard = []

        # Кнопка выбора текущего персонажа
        keyboard.append([
            InlineKeyboardButton(
                f"✅ Выбрать {character.name}",
                callback_data=f"select_char_{character.id}"
            )
        ])

        # Кнопки навигации
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"char_page_{page - 1}"))

        nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="char_page_info"))

        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"char_page_{page + 1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        # Дополнительная навигация: кнопка для перехода к первому/последнему
        if total_pages > 1:
            quick_nav = []
            if page > 0:
                quick_nav.append(InlineKeyboardButton("⏮️ Первый", callback_data="char_page_0"))
            if page < total_pages - 1:
                quick_nav.append(InlineKeyboardButton("⏭️ Последний", callback_data=f"char_page_{total_pages - 1}"))
            if quick_nav:
                keyboard.append(quick_nav)

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем фото с описанием
        try:
            success = await self._send_photo_with_bytes(
                chat_id=chat_id,
                photo_bytes=character.avatar,
                caption=f"*{character.name}*\n\n{character.description}\n\nИспользуйте кнопки навигации для просмотра других персонажей.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

            if not success:
                raise Exception("Failed to send photo")

        except Exception as e:
            self.logger.error(f'Error sending character photo: {e}')
            # Если не удалось отправить фото, отправляем только текст
            await self._safe_send_message(
                chat_id,
                f"*{character.name}*\n\n{character.description}\n\nИспользуйте кнопки навигации для просмотра других персонажей.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    async def handle_character_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data
        chat_id = query.message.chat_id if query.message else None

        if data.startswith('char_page_'):
            try:
                page = int(data.split('_')[2])
                await self.show_character_carousel(update, page)
                # Удаляем предыдущее сообщение с каруселью
                try:
                    await query.delete_message()
                except:
                    pass
            except (ValueError, IndexError):
                await query.answer('❌ Ошибка навигации', show_alert=True)

        elif data.startswith('select_char_'):
            try:
                character_id = int(data.split('_')[2])
                success, message = self.manage_character_uc.set_user_character(user_id, character_id)

                if success:
                    character = self.character_repo.get_character(character_id)

                    # Проверяем, есть ли у сообщения фото (тогда у него caption, а не text)
                    if query.message.photo:
                        # Редактируем caption сообщения с фото
                        try:
                            await query.edit_message_caption(
                                caption=f"✅ *Вы выбрали: {character.name}*\n\n{character.description}\n\nТеперь вы можете общаться! Напишите что-нибудь.",
                                parse_mode='Markdown'
                            )
                        except Exception as e:
                            self.logger.warning(f'Could not edit caption, sending new message: {e}')
                            # Если не удалось отредактировать caption, отправляем новое сообщение
                            await self._safe_send_message(
                                chat_id,
                                f"✅ *Вы выбрали: {character.name}*\n\n{character.description}\n\nТеперь вы можете общаться! Напишите что-нибудь.",
                                parse_mode='Markdown'
                            )
                    else:
                        # У сообщения только текст, редактируем его
                        await query.edit_message_text(
                            f"✅ *Вы выбрали: {character.name}*\n\n{character.description}\n\nТеперь вы можете общаться! Напишите что-нибудь.",
                            parse_mode='Markdown'
                        )
                else:
                    await query.answer(message, show_alert=True)

            except Exception as e:
                self.logger.error(f'Error selecting character: {e}')
                await query.answer('❌ Ошибка при выборе персонажа', show_alert=True)

        elif data == 'char_page_info':
            await query.answer('Используйте кнопки для навигации')

    async def _send_photo_with_bytes(self, chat_id: int, photo_bytes: bytes, caption: str = None,
                                     reply_markup=None, parse_mode: str = None) -> bool:
        """
        Отправляет фото из bytes с использованием временного файла
        """
        if not hasattr(self, 'application') or not self.application:
            self.logger.error('Bot application not available')
            return False

        try:
            # Создаем временный файл для хранения изображения
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_file.write(photo_bytes)
                temp_file_path = temp_file.name

            try:
                # Открываем файл и отправляем
                with open(temp_file_path, 'rb') as photo_file:
                    await self.application.bot.send_photo(
                        chat_id=chat_id,
                        photo=InputFile(photo_file),
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )
                return True
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    self.logger.warning(f'Could not delete temp file {temp_file_path}: {e}')

        except Exception as e:
            self.logger.error(f'Error sending photo: {e}')
            return False

    async def _send_typing_status(self, chat_id: int) -> bool:
        """Безопасный ответ на сообщение с учетом лимитов Telegram"""
        if not hasattr(self, 'application') or not self.application:
            self.logger.error("Bot application not available")
            return False

        return await self.telegram_sender.send_typing_status(bot=self.application.bot, chat_id=chat_id)

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

    def _setup_logging(self):
        setup_logging()
        self.logger = StructuredLogger("friend_bot")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        self.logger.info(
            "Start command received",
            extra={'user_id': user.id, 'username': user.username}
        )

        response = self.start_conversation_uc.execute(
            user.id, user.username, user.first_name, user.last_name
        )

        characters = self.character_repo.get_all_characters(active_only=True)
        if len(characters) == 1:
            success, message = self.manage_character_uc.set_user_character(user.id, characters[0].id)

            success = await self._safe_reply(update, response)
            if not success:
                self.logger.error(f"Failed to send start message to user {user.id}")
        else:
            # Приветственное сообщение
            welcome_msg = (
                '👋 *Добро пожаловать!*\n\n'
                'Выбери персонажа для общения из списка. Каждый из них имеет свою уникальную личность и стиль общения.\n\n'
                'После выбора персонажа просто напиши мне сообщение, и мы начнем общаться!'
            )

            success = await self._safe_reply(update, welcome_msg)
            if not success:
                self.logger.error(f"Failed to send start message to user {user.id}")

             # Показываем карусель персонажей при старте
            await self.show_character_carousel(update)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Reset command received", extra={'user_id': user_id})

        # Получаем текущего персонажа пользователя
        character = self.manage_character_uc.get_user_character(user_id)
        if character:
            # Очищаем контекст и памяти для текущего персонажа
            self.conversation_repo.clear_conversation(user_id, character.id)
            self.rag_repo.delete_user_memories(user_id, character.id)
            success = await self._safe_reply(update, f'🧹 Разговор с {character.name} сброшен! Давай начнем заново! Как твои дела?')
        else:
            success = await self._safe_reply(update, '🧹 Давай начнем наш разговор заново! Сначала выбери персонажа с помощью /choose_character')

    async def limits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущие лимиты пользователя"""
        user_id = update.effective_user.id

        self.logger.info("Limits command received", extra={'user_id': user_id})

        # Получаем тариф пользователя
        user_tariff = self.tariff_service.get_user_tariff(user_id)
        if not user_tariff or not user_tariff.tariff_plan:
            success = await self._safe_reply(update,
                                             "❌ Не удалось определить ваш тарифный план.\n"
                                             "Используйте /start для инициализации.")
            return

        tariff = user_tariff.tariff_plan

        # Получаем информацию о лимитах
        limits_info = self.check_limits_uc.get_limits_info(user_id, tariff)

        message = f"📊 **Тариф: {tariff.name}**\n\n"
        message += f"💰 Цена: {tariff.price} руб./месяц\n\n"

        message += "🕒 **Текущее использование:**\n"
        message += f"• В минуту: {limits_info['current']['minute']}/{limits_info['limits']['minute']}\n"
        message += f"• В час: {limits_info['current']['hour']}/{limits_info['limits']['hour']}\n"
        message += f"• В день: {limits_info['current']['day']}/{limits_info['limits']['day']}\n\n"

        message += "⏳ **Сброс через:**\n"
        message += f"• Минута: {limits_info['time_until_reset']['minute']}\n"
        message += f"• Час: {limits_info['time_until_reset']['hour']}\n"
        message += f"• День: {limits_info['time_until_reset']['day']}\n\n"

        message += "📏 **Лимиты сообщений:**\n"
        message += f"• Макс. длина: {tariff.message_limits.max_message_length} символов\n"
        message += f"• История: {tariff.message_limits.max_context_messages} сообщений\n"

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
                    user_tariff = self.tariff_service.get_user_tariff(user_id)

        response = self.tariff_service.get_tariff_info(user_tariff.tariff_plan_id)

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

    📊 **Статистика и информация:**
    • `/admin_stats` - общая статистика пользователей
    • `/admin_userinfo [user_id]` - информация о пользователе
    • `/admin_message_stats [user_id]` - статистика сообщений
    • `/admin_user_tariff [user_id]` - тариф пользователя

    💰 **Управление тарифами:**
    • `/admin_assign_tariff <user_id> <tariff_id> [дней]` - назначить тариф

    🚫 **Управление блокировками:**
    • `/admin_block <user_id> [причина]` - заблокировать пользователя
    • `/admin_unblock <user_id>` - разблокировать пользователя
    • `/admin_blocked_list` - список заблокированных
    • `/admin_block_info <user_id>` - информация о блокировке

     **Примеры использования:**
    `/admin_message_stats 123456789` - статистика сообщений

    💡 **Примеры использования:**
    `/admin_assign_tariff 123456789 1 30` - назначить тариф 1 на 30 дней
    `/admin_user_tariff 123456789` - посмотреть тариф пользователя

    📊 **Обычные команды (для всех):**
    • `/start` - начать общение
    • `/limits` - лимиты сообщений
    • `/reset` - сбросить разговор
    • `/tariff` - твой тариф
    • `/all_tariffs` - все тарифы
    • `/tariff_info <ID>` - информация о тарифе
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

        # Получаем статистику через обновленный use case
        stats = self.manage_user_limits_uc.get_user_stats(target_user_id)

        # Получаем тариф пользователя для отображения лимитов
        user_tariff = self.tariff_service.get_user_tariff(target_user_id)
        tariff_info = None
        if user_tariff and user_tariff.tariff_plan:
            tariff_info = self.manage_user_limits_uc.get_tariff_limits_info(user_tariff.tariff_plan)

        message = f"📊 **Статистика сообщений пользователя {target_user_id}:**\n\n"
        message += f"• Всего сообщений: {stats['total_messages']}\n"
        message += f"• Всего символов: {stats['total_characters']}\n"
        message += f"• Средняя длина: {stats['average_length']} символов\n"
        message += f"• Отклонено сообщений: {stats['rejected_messages']}\n"
        message += f"• Попаданий в rate limit: {stats['rate_limit_hits']}\n"

        if stats['last_message_at']:
            from datetime import datetime
            last_msg = stats['last_message_at']
            if isinstance(last_msg, str):
                last_msg = datetime.fromisoformat(last_msg.replace('Z', '+00:00'))
            message += f"• Последнее сообщение: {last_msg.strftime('%d.%m.%Y %H:%M')}\n"

        if tariff_info:
            message += "\n📏 **Лимиты тарифа:**\n"
            message += f"• Макс. длина сообщения: {tariff_info['message_limits']['max_message_length']}\n"
            message += f"• Макс. сообщений в контексте: {tariff_info['message_limits']['max_context_messages']}\n"

        success = await self._safe_reply(update, message)
        if not success:
            self.logger.error(f"Failed to send message stats to user {user_id}")

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
                                             "Используйте /all_tariffs чтобы посмотреть доступные тарифы"
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

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text

        self.logger.info(
            "Message received",
            extra={'user_id': user_id, 'message_length': len(user_message)}
        )

        if self.manage_block_uc.is_user_blocked(user_id):
            success = await self._safe_reply(update,
                                             "🚫 Вы заблокированы и не можете отправлять сообщения.\n\n"
                                             "Если вы считаете, что это ошибка, свяжитесь с администратором."
                                             )
            return

        self.user_repo.update_last_seen(user_id)

        # Получаем текущего персонажа пользователя
        character = self.manage_character_uc.get_user_character(user_id)

        # Если персонаж не выбран, показываем карусель
        if not character:
            await self.show_character_carousel(update)
            await self._safe_reply(update,
                                   '👋 Привет! Сначала выберите персонажа для общения из списка выше.')
            return

        user_tariff = self.tariff_service.get_user_tariff(user_id)
        if not user_tariff or not user_tariff.tariff_plan:
            default_tariff = self.tariff_service.get_default_tariff()
            if default_tariff:
                self.tariff_service.assign_tariff_to_user(user_id, default_tariff.id)
                user_tariff = self.tariff_service.get_user_tariff(user_id)

        if not user_tariff or not user_tariff.tariff_plan:
            success = await self._safe_reply(update,
                                             "❌ Не удалось определить ваш тарифный план.\n"
                                             "Пожалуйста, свяжитесь с администратором.")
            return

        tariff = user_tariff.tariff_plan

        is_valid, error_msg = self.check_limits_uc.check_message_length(
            user_id, user_message, tariff
        )
        if not is_valid:
            success = await self._safe_reply(update, error_msg)
            return

        if not self.manage_admin_uc.is_user_admin(user_id):
            can_send, limit_message, _ = self.check_limits_uc.check_rate_limit(user_id, tariff)
            if not can_send:
                success = await self._safe_reply(update, limit_message)
                return

        try:
            await self._send_typing_status(user_id)

            # Сохраняем пользователя (если еще не сохранен)
            existing_user = self.user_repo.get_user(user_id)
            if not existing_user:
                self.user_repo.save_user(
                    self.middleware.create_user_from_telegram(user)
                )

            rag_enabled = tariff and tariff.is_rag_enabled()
            rag_context = ""
            if rag_enabled:
                # Извлекаем и сохраняем воспоминания (асинхронно)
                asyncio.create_task(
                    self.manage_rag_uc.extract_and_save_memories(user.id, character.id, user_message)
                )

                # Получаем релевантные воспоминания для текущего сообщения
                rag_context = await self.manage_rag_uc.prepare_rag_context(
                    user.id, character.id, user_message
                )

                self.logger.debug(
                    "RAG context prepared",
                    extra={
                        'user_id': user.id,
                        'rag_context_length': len(rag_context),
                        'has_rag_context': bool(rag_context)
                    }
                )

            # Извлекаем и обновляем профиль
            profile_data = await self.manage_profile_uc.extract_and_update_profile(user_id, user_message)

            await self._send_typing_status(user_id)

            # Обрабатываем сообщение с передачей лимита контекста из тарифа
            response = await self.handle_message_uc.execute(
                user_id,
                character.id,
                user_message,
                rag_context,
                max_context_messages=tariff.message_limits.max_context_messages  # ← лимит из тарифа!
            )

            if not self.manage_admin_uc.is_user_admin(user_id):
                self.check_limits_uc.record_message_usage(user_id, len(user_message), tariff)

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
/limits - текущее использование лимитов
/tariff - мой тарифный план и лимиты
/all_tariffs - все доступные тарифы
/reset - начать разговор заново
/help - помощь

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

    async def choose_character(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.logger.info('Character selection requested', extra={'user_id': user_id})
        await self.show_character_carousel(update)

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("reset", self.reset))
        self.application.add_handler(CommandHandler("limits", self.limits))
        self.application.add_handler(CommandHandler("tariff", self.tariff))
        self.application.add_handler(CommandHandler('choose_character', self.choose_character))

        # Административные команды
        self.application.add_handler(CommandHandler("admin_users", self.admin_users))
        self.application.add_handler(CommandHandler("admin_help", self.admin_help))
        self.application.add_handler(CommandHandler("admin_stats", self.admin_stats))
        self.application.add_handler(CommandHandler("admin_list", self.admin_list))
        self.application.add_handler(CommandHandler("admin_userinfo", self.admin_userinfo))
        self.application.add_handler(CommandHandler("admin_health", self.admin_health))

        # Команды блокировки
        self.application.add_handler(CommandHandler("admin_block", self.admin_block))
        self.application.add_handler(CommandHandler("admin_unblock", self.admin_unblock))
        self.application.add_handler(CommandHandler("admin_blocked_list", self.admin_blocked_list))
        self.application.add_handler(CommandHandler("admin_block_info", self.admin_block_info))

        # Команды управления лимитами сообщений
        self.application.add_handler(CommandHandler("admin_message_stats", self.admin_message_stats))

        # Команды управления тарифами
        self.application.add_handler(CommandHandler("admin_assign_tariff", self.admin_assign_tariff))
        self.application.add_handler(CommandHandler("admin_user_tariff", self.admin_user_tariff))

        # Обработчик карусели персонажей
        self.application.add_handler(CallbackQueryHandler(
            self.handle_character_callback,
            pattern=r'^(char_page_|select_char_|char_page_info)'
        ))

        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def cleanup(self):
        """Корректное завершение работы"""
        self.logger.info("Cleaning up resources...")

        # Закрываем AI клиенты
        if hasattr(self, 'ai_client'):
            await self.ai_client.close()

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

            self.application.run_polling(timeout=30)

        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}")
            # Принудительно закрываем ресурсы при ошибке
            asyncio.run(self.cleanup())
            raise