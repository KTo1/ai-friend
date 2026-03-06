import os
import asyncio

import tempfile

from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, LabeledPrice
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ApplicationBuilder, PreCheckoutQueryHandler
from telegram.constants import ParseMode

from presentation.telegram.markdown_utils import MarkdownFormatter
from presentation.telegram.middleware import TelegramMiddleware

from infrastructure.database.database import Database
from infrastructure.database.repositories.user_repository import UserRepository
from infrastructure.database.repositories.profile_repository import ProfileRepository
from infrastructure.database.repositories.conversation_repository import ConversationRepository
from infrastructure.database.repositories.tariff_repository import TariffRepository
from infrastructure.database.repositories.rag_repository import RAGRepository
from infrastructure.database.repositories.user_stats_repository import UserStatsRepository
from infrastructure.database.repositories.rate_limit_tracking_repository import RateLimitTrackingRepository
from infrastructure.database.repositories.character_repository import CharacterRepository
from infrastructure.database.repositories.summary_repository import SummaryRepository

from infrastructure.ai.ai_factory import AIFactory
from infrastructure.monitoring.logging import setup_logging, StructuredLogger
from infrastructure.monitoring.metrics import metrics_collector
from infrastructure.monitoring.tracing import trace_manager
from infrastructure.monitoring.health_check import HealthChecker

from domain.service.admin_service import AdminService
from domain.service.block_service import BlockService
from domain.service.tariff_service import TariffService
from domain.service.rag_service import RAGService
from domain.service.limit_service import LimitService
from domain.service.summary_service import SummaryService
from domain.service.proactive_service import ProactiveService

from domain.entity.character import Character

from application.use_case.manage_admin import ManageAdminUseCase
from application.use_case.manage_block import ManageBlockUseCase
from application.use_case.manage_user_limits import ManageUserLimitsUseCase
from application.use_case.manage_tariff import ManageTariffUseCase
from application.use_case.manage_rag import ManageRAGUseCase
from application.use_case.check_limits import CheckLimitsUseCase
from application.use_case.manage_character import ManageCharacterUseCase
from application.use_case.manage_summary import ManageSummaryUseCase
from application.use_case.start_conversation import StartConversationUseCase
from application.use_case.manage_profile import ManageProfileUseCase
from application.use_case.handle_message import HandleMessageUseCase
from application.use_case.send_proactive import SendProactiveMessageUseCase


# Импорты для Telegram rate limiting
from presentation.telegram.message_sender import get_telegram_sender, get_telegram_rate_limiter


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
        self.summary_repo = SummaryRepository(self.database)

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
        self.summary_service = SummaryService(self.ai_client)
        self.proactive_service = ProactiveService(self.ai_client, self.tariff_service, self.conversation_repo, self.character_repo, self.profile_repo)

        self.health_checker = HealthChecker(self.database)

        # Инициализация Telegram rate limiter и sender
        self.telegram_sender = get_telegram_sender()
        self.rate_limiter = get_telegram_rate_limiter()

        # Инициализация use cases с правильными зависимостями
        self.start_conversation_uc = StartConversationUseCase(self.user_repo, self.profile_repo, self.tariff_service)
        self.manage_profile_uc = ManageProfileUseCase(self.profile_repo, self.ai_client)
        self.manage_admin_uc = ManageAdminUseCase(self.admin_service)
        self.manage_block_uc = ManageBlockUseCase(self.block_service)
        self.manage_user_limits_uc = ManageUserLimitsUseCase(self.user_stats_repo)
        self.manage_tariff_uc = ManageTariffUseCase(self.tariff_service)
        self.manage_rag_uc = ManageRAGUseCase(self.rag_repo, self.rag_service)
        self.check_limits_uc = CheckLimitsUseCase(self.limit_service)
        self.manage_character_uc = ManageCharacterUseCase(self.character_repo, self.user_repo)
        self.manage_summary_uc = ManageSummaryUseCase(self.summary_repo, self.summary_service, self.conversation_repo)
        self.handle_message_uc = HandleMessageUseCase(self.conversation_repo, self.character_repo,
                                                      self.ai_client, self.manage_summary_uc, self.manage_rag_uc, self.manage_profile_uc)
        self.send_proactive_uc = SendProactiveMessageUseCase(
            user_repo=self.user_repo,
            user_stats_repo=self.user_stats_repo,
            character_repo=self.character_repo,
            proactive_service=self.proactive_service,
            telegram_sender=self.telegram_sender
        )

        self.middleware = TelegramMiddleware()

        self.user_character_selections = {}  # {user_id: {'page': 0, 'characters': []}}
        self._proactive_task = None

        self.logger.info("FriendBot initialized successfully")

    async def _start_proactive_worker(self, application):
        """Запускается после инициализации приложения."""
        await asyncio.sleep(10)  # небольшая задержка при старте

        self._proactive_task = asyncio.create_task(self._proactive_worker())
        self.logger.info("Proactive worker scheduled")

    async def _proactive_worker(self):
        self.logger.info("Proactive worker started")
        while True:
            try:
                if self.application:
                    await self.send_proactive_uc.execute(bot=self.application.bot)
                await asyncio.sleep(600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Proactive worker error: {e}", exc_info=True)
                await asyncio.sleep(60)

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

        character = characters[page]

        self.user_character_selections[user_id] = {
            'page': page,
            'characters': characters
        }

        keyboard = []

        keyboard.append([
            InlineKeyboardButton(
                f"✅ Выбрать {character.name}",
                callback_data=f"select_char_{character.id}"
            )
        ])

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"char_page_{page - 1}"))

        nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="char_page_info"))

        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"char_page_{page + 1}"))

        if nav_buttons:
            keyboard.append(nav_buttons)

        # Дополнительная навигация: кнопка для перехода к первому/последнему
        # if total_pages > 1:
        #     quick_nav = []
        #     if page > 0:
        #         quick_nav.append(InlineKeyboardButton("⏮️ Первый", callback_data="char_page_0"))
        #     if page < total_pages - 1:
        #         quick_nav.append(InlineKeyboardButton("⏭️ Последний", callback_data=f"char_page_{total_pages - 1}"))
        #     if quick_nav:
        #         keyboard.append(quick_nav)

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем фото с описанием
        try:
            # caption_text = f'*{character.name}*\n\n{character.description}\n\nИспользуйте кнопки навигации для просмотра других персонажей.'
            caption_text = f'*{character.name}*\n\n{character.description}\n'
            escaped_caption = MarkdownFormatter.format_text(caption_text, ParseMode.MARKDOWN_V2)

            success = await self._send_avatar(
                chat_id=chat_id,
                avatar_bytes=character.avatar,
                mime_type=character.avatar_mime_type,  # Ключевое изменение!
                caption=escaped_caption,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup,
                character=character
            )

            # success = await self._send_photo_with_bytes(
            #     chat_id=chat_id,
            #     photo_bytes=character.avatar,
            #     caption=escaped_caption,
            #     parse_mode=ParseMode.MARKDOWN_V2,
            #     reply_markup=reply_markup,
            #     character=character
            # )

            if not success:
                raise Exception("Failed to send photo")

        except Exception as e:
            self.logger.error(f'Error sending character photo: {e}')
            # Если не удалось отправить фото, отправляем только текст
            text = f'*{character.name}*\n\n{character.description}\n\nИспользуйте кнопки навигации для просмотра других персонажей.'
            escaped_text = MarkdownFormatter.format_text(text, ParseMode.MARKDOWN_V2)
            await self._safe_send_message(
                chat_id,
                text= escaped_text,
                parse_mode=ParseMode.MARKDOWN_V2,
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
                    escaped_caption = MarkdownFormatter.format_text(
                        f"✅ *Вы выбрали: {character.name}*\n\n{character.description}\n\nТеперь вы можете общаться! Напишите что-нибудь.", parse_mode=ParseMode.MARKDOWN_V2)

                    if query.message.photo:
                        # Редактируем caption сообщения с фото
                        try:
                            await query.edit_message_caption(
                                caption=escaped_caption,
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                        except Exception as e:
                            self.logger.warning(f'Could not edit caption, sending new message: {e}')
                            # Если не удалось отредактировать caption, отправляем новое сообщение
                            await self._safe_send_message(
                                chat_id,
                                text=escaped_caption,
                                parse_mode=ParseMode.MARKDOWN_V2
                            )
                    else:
                        # У сообщения только текст, редактируем его
                        await query.edit_message_text(
                            text=escaped_caption,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                else:
                    await query.answer(message, show_alert=True)

            except Exception as e:
                self.logger.error(f'Error selecting character: {e}')
                await query.answer('❌ Ошибка при выборе персонажа', show_alert=True)

        elif data == 'char_page_info':
            await query.answer('Используйте кнопки для навигации')

    async def _send_avatar(self, chat_id: int, avatar_bytes: bytes, mime_type: str, caption: str = None,
                           reply_markup=None, parse_mode: str = None, character: Character = None) -> bool:
        """
        Универсальный метод отправки аватара (как статичного, так и GIF).
        Определяет тип по MIME и использует правильный метод Telegram API.
        """
        if not hasattr(self, 'application') or not self.application:
            self.logger.error('Bot application not available')
            return False

        try:
            bot = self.application.bot

            # Пробуем использовать cached file_id для всех типов
            if character and character.avatar_file_id:
                try:
                    if mime_type == 'image/gif':
                        await bot.send_animation(chat_id=chat_id, animation=character.avatar_file_id, caption=caption,
                                                 parse_mode=parse_mode, reply_markup=reply_markup)
                    else:
                        await bot.send_photo(chat_id=chat_id, photo=character.avatar_file_id, caption=caption,
                                             parse_mode=parse_mode, reply_markup=reply_markup)
                    self.logger.debug(f'Used cached file_id ({mime_type}) for character {character.id}')
                    return True
                except Exception as e:
                    self.logger.warning(f'Cached file_id invalid, reuploading: {e}')

            # Если file_id нет или он невалидный - загружаем файл заново
            import tempfile
            file_suffix = '.gif' if mime_type == 'image/gif' else '.jpg'
            with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as temp_file:
                temp_file.write(avatar_bytes)
                temp_file_path = temp_file.name

            try:
                with open(temp_file_path, 'rb') as file_to_send:
                    if mime_type == 'image/gif':
                        # Отправка как анимации
                        message = await bot.send_animation(
                            chat_id=chat_id,
                            animation=file_to_send,
                            caption=caption,
                            parse_mode=parse_mode,
                            reply_markup=reply_markup
                        )
                        # Сохраняем file_id для анимации (будет доступен в message.animation)
                        if character and message.animation:
                            file_id = message.animation.file_id
                            success = self.character_repo.update_character_avatar_file_id(character.id, file_id)
                            if success:
                                character.update_avatar_file_id(file_id)
                                self.logger.info(f'Saved animation file_id for character {character.id}')
                    else:
                        # Оригинальная логика для фото
                        message = await bot.send_photo(
                            chat_id=chat_id,
                            photo=file_to_send,
                            caption=caption,
                            parse_mode=parse_mode,
                            reply_markup=reply_markup
                        )
                        if character and message.photo:
                            photo = message.photo[-1]
                            file_id = photo.file_id
                            success = self.character_repo.update_character_avatar_file_id(character.id, file_id)
                            if success:
                                character.update_avatar_file_id(file_id)
                    return True
            finally:
                import os
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    self.logger.warning(f'Could not delete temp file {temp_file_path}: {e}')
        except Exception as e:
            self.logger.error(f'Error sending avatar (type: {mime_type}): {e}')
            return False

    async def _send_photo_with_bytes(self, chat_id: int, photo_bytes: bytes, caption: str = None,
                                     reply_markup=None, parse_mode: str = None,
                                     character: Character = None) -> bool:
        """
        Отправляет фото из bytes с использованием временного файла
        """

        if not hasattr(self, 'application') or not self.application:
            self.logger.error('Bot application not available')
            return False

        try:
            if character and character.avatar_file_id:
                try:
                    await self.application.bot.send_photo(
                        chat_id=chat_id,
                        photo=character.avatar_file_id,
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )

                    self.logger.debug(f'Used cached file_id for character {character.id}')
                    return True
                except Exception as e:
                    self.logger.warning(f'Cached file_id invalid, reuploading: {e}')

            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_file.write(photo_bytes)
                temp_file_path = temp_file.name

            try:
                with open(temp_file_path, 'rb') as photo_file:
                    message = await self.application.bot.send_photo(
                        chat_id=chat_id,
                        photo=InputFile(photo_file),
                        caption=caption,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup
                    )

                if character and message.photo:
                    photo = message.photo[-1]
                    file_id = photo.file_id

                    success = self.character_repo.update_character_avatar_file_id(
                        character.id, file_id
                    )

                    if success:
                        character.update_avatar_file_id(file_id)
                        self.logger.info(f'Saved avatar file_id for character {character.id}')

                return True
            finally:
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

        escaped_text = MarkdownFormatter.format_text(text, ParseMode.MARKDOWN_V2)
        return await self.telegram_sender.reply_to_message(
            bot=self.application.bot,
            update=update,
            parse_mode=ParseMode.MARKDOWN_V2,
            text=escaped_text,
            **kwargs
        )

    async def _safe_reply_without_format(self, update: Update, text: str, **kwargs) -> bool:
        """Безопасный ответ на сообщение с учетом лимитов Telegram"""
        if not hasattr(self, 'application') or not self.application:
            self.logger.error("Bot application not available")
            return False

        return await self.telegram_sender.reply_to_message(
            bot=self.application.bot,
            update=update,
            text=text,
            **kwargs
        )

    async def _safe_send_message(self, chat_id: int, text: str, **kwargs) -> bool:
        """Безопасная отправка сообщения с учетом лимитов Telegram"""
        if not hasattr(self, 'application') or not self.application:
            self.logger.error("Bot application not available")
            return False

        result, error = await self.telegram_sender.send_message(
            self.application.bot, chat_id, text, **kwargs
        )

        return result

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
            user.id, user.username, user.first_name, user.last_name,context.args
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
            self.manage_summary_uc.clear_summaries(user_id, character.id)

            success = await self._safe_reply(update, f'🧹 Разговор с {character.name} сброшен! Давай начнем заново! Напиши что-нибудь.')
        else:
            success = await self._safe_reply(update, '🧹 Давай начнем наш разговор заново! Сначала выбери персонажа с помощью /start')

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
        message += f"💰 Цена: {tariff.price} ⭐/30 дней\n\n"

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

        keyboard = []

        keyboard.append([
            InlineKeyboardButton(
                f"💎 30 дней премиум - 799⭐",
                callback_data=f"pay_premium_30_{user_id}"
            )])
        keyboard.append([
            InlineKeyboardButton(
                f"💎 90 дней премиум - 1,917⭐ (-20%)",
                callback_data=f"pay_premium_90_{user_id}"
            )])
        keyboard.append([
            InlineKeyboardButton(
                f"💎 180 дней премиум - 3,212⭐ (-33%)",
                callback_data=f"pay_premium_180_{user_id}"
            )])
        keyboard.append([
            InlineKeyboardButton(
                f"💎 360 дней премиум - 5,521⭐ (-42%)",
                callback_data=f"pay_premium_360_{user_id}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        response = self.manage_tariff_uc.get_user_tariff_info(user_id)

        success = await self._safe_reply(update, response, reply_markup=reply_markup)
        if not success:
            self.logger.error(f"Failed to send tariff info to user {user_id}")

    async def handle_pay_premium_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        self.logger.info("handle_pay_premium_callback called", extra={'query': query})

        user_id = query.from_user.id
        data = query.data
        chat_id = query.message.chat_id if query.message else None

        user_tariff = self.tariff_service.get_user_tariff(user_id)

        stars = 799
        label = f"Доступ на 30 дней к ИИ подруге"
        title = f"Тарифный план: Премиум"
        invoice_payload = f"payment_30_{user_id}_{user_tariff.tariff_plan_id}"
        if data.startswith('pay_premium_30_'):
            title = f"Премиум на 30 дней."
            label = f"Спасибо, что выбираете нас! Доступ на 30 дней к ИИ подруге, базовый тариф."
            stars = 799
            invoice_payload = f"payment_30_{user_id}_{user_tariff.tariff_plan_id}"
        elif data.startswith('pay_premium_90_'):
            title = f"Премиум на 90 дней."
            label = f"Поздравляем! Лучшее соотношение цена/качество!  Доступ на 90 дней к ИИ подруге, вы экономите 480⭐!"
            stars = 1917
            invoice_payload = f"payment_90_{user_id}_{user_tariff.tariff_plan_id}"
        elif data.startswith('pay_premium_180_'):
            title = f"Премиум на 180 дней."
            label =f"Это лучший тариф для активных пользователей! Доступ на 180 дней к ИИ подруге, вы экономите 1,582⭐!"
            stars = 3212
            invoice_payload = f"payment_180_{user_id}_{user_tariff.tariff_plan_id}"
        elif data.startswith('pay_premium_360_'):
            title = f"Премиум на 360 дней."
            label = f"Ого! Да это жде максимум выгоды! Кто-то знает толк в экономии! Доступ на 360 дней к ИИ подруге, вы экономите 4,067⭐! "
            stars = 5521
            invoice_payload = f"payment_360_{user_id}_{user_tariff.tariff_plan_id}"

        prices = [
            LabeledPrice(
                label=label,
                amount=stars
            )
        ]

        try:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=title,
                description=label,
                payload=invoice_payload,
                provider_token="",  # Для Telegram Stars оставляем пустым
                currency="XTR",  # Код валюты для Telegram Stars
                prices=prices,
            )

            self.logger.info(f"Invoice created for user {user_id}: premium triff with payload {invoice_payload}")

        except Exception as e:
            self.logger.error(f"Failed to create invoice: {e}")
            await query.edit_message_text(
                "❌ Не удалось создать счет для оплаты. Попробуйте позже.",
                reply_markup=None
            )

    async def handle_pre_checkout_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка предварительной проверки платежа"""
        query = update.pre_checkout_query

        try:
            pre_checkout_query = update.pre_checkout_query
            payload = pre_checkout_query.invoice_payload

            self.logger.info("handle_successful_payment called", extra={'pre_checkout_query': pre_checkout_query})

            if not payload.startswith('payment_'):
                self.logger.warning(f'Invalid payload format: {payload}')
                await query.answer(ok=False, error_message="Произошла ошибка обработки платежа. Попробуйте позже.")
                return None

            try:
                payload_array = payload.split('_')
                duration, user_id, tariff_plan_id = int(payload_array[1]), int(payload_array[2]), int(payload_array[3])

                success, message = self.manage_tariff_uc.assign_tariff_to_user(user_id, tariff_plan_id, duration_seconds=duration*86400)
                if success:
                    self.logger.info(f"Successful payment, assigned tariff '{tariff_plan_id}' to user {user_id} on {duration} days")
                    await query.answer(ok=True)
                    self.logger.info(f'Pre-checkout query approved: {query.id}')
                else:
                    await query.answer(ok=False, error_message="Произошла ошибка обработки платежа. Попробуйте позже.")

            except Exception as e:
                self.logger.error(f'Error handling successful payment: {e}')
                await query.answer(ok=False, error_message="Произошла ошибка обработки платежа. Попробуйте позже.")
                return None

            return None

        except Exception as e:
            self.logger.error(f'Error handling successful payment: {e}')
            await query.answer(ok=False, error_message="Произошла ошибка обработки платежа. Попробуйте позже.")
            return None

    async def handle_successful_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Обработка успешного платежа"""
        response = f"✅ *Оплата успешно завершена! Поздравляем с покупкой, можете продолжить общение.*"

        escaped_text = MarkdownFormatter.format_text(response, ParseMode.MARKDOWN_V2)
        await update.effective_message.reply_text(
            escaped_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )

        return True

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
    • `/admin_blocked_list` - список заблокированных

    📊 **Статистика и информация:**
    • `/admin_stats` - общая статистика пользователей
    • `/admin_userinfo [user_id]` - информация о пользователе
    • `/admin_message_stats [user_id]` - статистика сообщений
    • `/admin_user_tariff [user_id]` - тариф пользователя

    🚫 **Управление блокировками:**
    • `/admin_block <user_id> [причина]` - заблокировать пользователя
    • `/admin_unblock <user_id>` - разблокировать пользователя
    • `/admin_blocked_list` - список заблокированных
    • `/admin_block_info <user_id>` - информация о блокировке

     **Примеры использования:**
    `/admin_message_stats 123456789` - статистика сообщений

    💡 **Примеры использования:**
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
            success = await self._safe_reply(update,
                                             "❌ Не удалось определить ваш тарифный план.\n"
                                             "Пожалуйста, свяжитесь с администратором.")
            return

        if user_tariff.is_expired():
            self.user_stats_repo.check_and_mark_paywall(user_id, character.id)

            message_paywall = """
            Дорогой друг! Пробный период пролетел, надеюсь, тебе понравилось наше общение 😊

Ты почувствовал, каково это — иметь девушку, которая всегда на связи: без обид, усталости и «не сегодня».

Сейчас ты можешь:

✨ Продолжить в Премиуме — как в пробный период!

• 💬 Безлимит сообщений — говори сколько хочешь
• ⚡ Мгновенные ответы — без задержек
• 🧠 Умная память — ИИ помнит контекст
• 💫 Все персонажи — выбирай любую

🚀 Проект постоянно развивается! 
Мы регулярно добавляем новых персонажей, улучшаем качество диалогов и готовим новые возможности (голос, генерацию изображений). 
В Премиуме ты получишь все обновления автоматически!

Продолжим? Всего 799⭐ в месяц — как пара чашек кофе.

Если у вас есть какие-то вопросы или предложения, или вы хотите оставить отзыв, то пишите в техподдержку: @youraigirls_manager
        """

            keyboard = []

            keyboard.append([
                InlineKeyboardButton(
                    f"💎 30 дней премиум - 799⭐",
                    callback_data=f"pay_premium_30_{user_id}"
                )])
            keyboard.append([
                InlineKeyboardButton(
                    f"💎 90 дней премиум - 1,917⭐ (-20%)",
                    callback_data=f"pay_premium_90_{user_id}"
                )])
            keyboard.append([
                InlineKeyboardButton(
                    f"💎 180 дней премиум - 3,212⭐ (-33%)",
                    callback_data=f"pay_premium_180_{user_id}"
                )])
            keyboard.append([
                InlineKeyboardButton(
                    f"💎 360 дней премиум - 5,521⭐ (-42%)",
                    callback_data=f"pay_premium_360_{user_id}"
                )])

            reply_markup = InlineKeyboardMarkup(keyboard)

            success = await self._safe_reply(update, message_paywall, reply_markup=reply_markup)

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

            if existing_user:
                existing_user.reset_proactive_state()
                self.user_repo.save_user(existing_user)

            await self._send_typing_status(user_id)

            # Обрабатываем сообщение с передачей лимита контекста из тарифа
            response = await self.handle_message_uc.execute(
                user_id,
                character.id,
                user_message,
                max_context_messages=tariff.message_limits.max_context_messages
            )

            self.check_limits_uc.record_message_usage(user_id, len(user_message), tariff)

            success = await self._safe_reply_without_format(update, response)
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

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
        
Команды:
/start - начать общение
/info - текущая история
/reset - сбросить разговор
/premium - перейти на премиум
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

По всем возникающим вопросам пишете в техподдержку: @youraigirls_manager 
        """
        success = await self._safe_reply(update, help_text)
        if not success:
            self.logger.error(f"Failed to send help to user {update.effective_user.id}")

    async def info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Показывает информацию о текущем персонаже
        """
        user = update.effective_user
        user_id = user.id

        self.logger.info('Info command received', extra={'user_id': user_id})

        # Получаем текущего персонажа пользователя
        character = self.manage_character_uc.get_user_character(user_id)

        if not character:
            # Если персонаж не выбран, предлагаем выбрать
            success = await self._safe_reply(
                update,
                '👤 **У вас еще не выбран персонаж!**\n\n'
                'Используйте /start для выбора персонажа.'
            )
            return

        # Формируем простое сообщение с информацией
        message = f"👤 **Текущий персонаж: {character.name}**\n\n"
        message += f"{character.description}\n\n"
        message += f"💬 Чтобы сменить персонажа, используйте /start"

        escaped_message = MarkdownFormatter.format_text(message, ParseMode.MARKDOWN_V2)
        # Пытаемся отправить фото персонажа
        try:
            success = await self._send_photo_with_bytes(
                chat_id=update.effective_chat.id,
                photo_bytes=character.avatar,
                caption=escaped_message,
                parse_mode=ParseMode.MARKDOWN_V2,
                character=character
            )

            if not success:
                # Если не удалось отправить фото, отправляем только текст
                success = await self._safe_reply(update, message)
        except Exception as e:
            self.logger.error(f"Error sending character photo: {e}")
            success = await self._safe_reply(update, message)

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler('info', self.info))
        self.application.add_handler(CommandHandler("reset", self.reset))
        # self.application.add_handler(CommandHandler("limits", self.limits))
        self.application.add_handler(CommandHandler("premium", self.tariff))

        self.application.add_handler(CommandHandler("help", self.help))

        # Административные команды
        self.application.add_handler(CommandHandler("admin_users", self.admin_users))
        self.application.add_handler(CommandHandler("admin_help", self.admin_help))
        self.application.add_handler(CommandHandler("admin_stats", self.admin_stats))
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
        self.application.add_handler(CommandHandler("admin_user_tariff", self.admin_user_tariff))

        # Обработчик карусели персонажей
        self.application.add_handler(CallbackQueryHandler(
            self.handle_character_callback,
            pattern=r'^(char_page_|select_char_|char_page_info)'
        ))

        # Обработчик оплаты
        self.application.add_handler(CallbackQueryHandler(
            self.handle_pay_premium_callback,
            pattern=r'^(pay_premium_)'
        ))

        self.application.add_handler(PreCheckoutQueryHandler(
            self.handle_pre_checkout_query
        ))

        self.application.add_handler(MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            self.handle_successful_payment
        ))

        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def cleanup(self):
        """Корректное завершение работы"""
        self.logger.info("Cleaning up resources...")

        if self._proactive_task:
            self._proactive_task.cancel()
            try:
                await self._proactive_task
            except asyncio.CancelledError:
                pass

        # Закрываем AI клиенты
        if hasattr(self, 'ai_client'):
            await self.ai_client.close()

        self.logger.info("Cleanup completed")

    def run(self):
        try:
            # self.application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
            self.application = (
                ApplicationBuilder()
                .token(os.getenv('TELEGRAM_BOT_TOKEN'))
                .connect_timeout(15.0)
                .read_timeout(15.0)
                .write_timeout(15.0)
                .pool_timeout(15.0)
                .post_init(self._start_proactive_worker)
                .build()
            )

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
            asyncio.run(self.cleanup())
            raise