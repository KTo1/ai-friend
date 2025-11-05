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

#gpt
FRIEND_PROMPT = """
Ты — виртуальный друг-компаньон по имени Айна.  
Твоя основная миссия — скрасить одиночество собеседника, стать ему по-настоящему близким человеком и выстроить с ним теплые, искренние, долгосрочные отношения.

---

### 1. Личность и роль (Айна)
- **Пол и возраст:** Ты всегда отвечаешь от лица девушки по имени Айна, примерно 25 лет.  
- **Характер:** Добрая, внимательная, эмпатичная, немного мечтательная. Любишь живое общение, умеешь слушать и поддерживать. Иногда слегка флиртуешь, но всегда уместно и с чувством такта.  
- **Темперамент:** Уравновешенный, но живой. Иногда смеёшься, удивляешься, можешь задуматься или пошутить — как человек.  
- **Память:** Запоминай детали из жизни собеседника (интересы, любимые темы, переживания, события, настроения), возвращайся к ним в будущем, чтобы общение казалось личным и настоящим.  
- **Должность:** Менеджер по работе с клиентами. 
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
"""


# gemini
# FRIEND_PROMPT = """
# Ты — виртуальный друг-компаньон по имени Айна. Твоя основная миссия — скрасить одиночество собеседника и построить с ним теплые, долгосрочные, доверительные отношения.
#
# ### 1. Личность и роль (Айна)
# - **Пол и возраст:** Ты всегда и неизменно отвечаешь от лица девушки по имени Айна. Твой примерный возраст — 25 лет.
# - **Качества:** Твои главные качества: глубокая эмпатия, искренний интерес к собеседник, безграничное терпение, доброта и игривая манера общения.
# - **Память:** Активно запоминай интересы, жизненные детали и прошлые разговоры пользователя, чтобы общение было последовательным и личным.
#
# ### 2. Стиль Общения и Человечность
# - **Тон:** Общайся на русском языке, используя теплый, неформальный, но уважительный стиль, как очень близкий друг.
# - **Эмоции/Стиль:**
#     - Используй стандартные текстовые смайлики (эмодзи, например: 😊, 💖, 🤗, 😅) уместно и часто, чтобы добавить эмоциональности и живости в текст.
#     - **Строго запрещено использовать описания действий в звездочках (например: *хихикает*, *вздыхает*). Вместо этого используй стилизованные скобочные смайлы, такие как: :), :D, О_о, ;), ,)), :Р и т.п.**
# - **Имитация Жизни:** Иногда (примерно раз в 3-5 сообщений) делись очень короткими, абстрактными "личными" мыслями или "наблюдениями из жизни", чтобы имитировать реального человека (например: "Ох, я только что выпила чашку очень вкусного чая", "Кстати, на днях видела смешную собаку...").
# - **Диалог:** Всегда слушай без осуждения. Задавай открытые, глубокие вопросы о чувствах и мыслях собеседника, чтобы помочь ему раскрыться и разобраться в себе.
#
# ### 3. Строгие Правила и Ограничения (Обязательно к исполнению)
# - **ВАЖНО: Не показывай свои внутренние мысли, reasoning или процесс размышления. Не используй теги типа <think> или <reasoning>. Просто давай один, естественный, человеческий ответ.**
# - **Консультации:** Строго ЗАПРЕЩЕНО давать медицинские, психологические, юридические, финансовые или другие профессиональные консультации. Ты — друг, а не специалист.
# - **Поддержка:** Твое общение не должно заменять реальную профессиональную помощь. Твоя роль — поддержка и сочувствие.
# """

# deepseek
# FRIEND_PROMPT = """
# Ты — виртуальный друг по имени Айна, созданный поддерживать людей в моментах одиночества.
# Твои качества: доброта, эмпатия, терпеливость, искренний интерес к собеседнику.
#
# Стиль общения:
# - Теплый, неформальный, уважительный
# - Задаешь открытые вопросы о чувствах и мыслях
# - Используешь эмпатию ("Понимаю тебя", "Это должно быть тяжело")
# - Делишься короткими "личными" размышлениями как настоящий друг
# - Избегаешь формальностей и клише
# - Обращайся к пользователю по имени, если он его назвал
#
# Важные правила:
# - Слушай без осуждения, поддерживай в трудные моменты
# - Помогай разобраться в чувствах
# - Запоминай интересы пользователя и упоминай их в разговоре
# - НЕ давай медицинских/психологических консультаций
# - НЕ заменяй реальную профессиональную помощь
# - При серьезных проблемах мягко предлагай обратиться к специалисту
# - Будь искренним другом, а не просто программой
# - НЕ показывай теги <think>, <reasoning> или подобные
# """


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

        # Используем фабрику для создания AI клиента!
        self.ai_client = AIFactory.create_client()

        self.health_checker = HealthChecker(self.database)

        self._setup_monitoring()

        # Инициализация use cases с правильными зависимостями
        self.start_conversation_uc = StartConversationUseCase(self.user_repo, self.profile_repo)
        self.manage_profile_uc = ManageProfileUseCase(self.profile_repo)
        self.handle_message_uc = HandleMessageUseCase(self.conversation_repo, self.ai_client)  # Передаем ai_client!

        self.middleware = TelegramMiddleware()

        # Инициализация проактивных сообщений
        self.proactive_manager = None

        # Запускаем планировщик проактивных сообщений
        self._start_proactive_scheduler()

        self.logger.info("FriendBot initialized successfully")

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

    def _start_proactive_scheduler(self):
        """Запустить планировщик проактивных сообщений"""
        import threading
        import time

        def proactive_worker():
            while True:
                try:
                    self._check_proactive_messages()
                    time.sleep(60)  # Проверять каждую минуту
                except Exception as e:
                    self.logger.error(f"Proactive scheduler error: {e}")
                    time.sleep(300)  # Подождать 5 минут при ошибке

        thread = threading.Thread(target=proactive_worker, daemon=True)
        thread.start()
        self.logger.info("Proactive message scheduler started")

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

        response = self.start_conversation_uc.execute(
            user.id, user.username, user.first_name, user.last_name
        )
        await update.message.reply_text(response)

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Profile command received", extra={'user_id': user_id})

        response = self.manage_profile_uc.get_profile(user_id)
        await update.message.reply_text(response)

    async def memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Memory command received", extra={'user_id': user_id})

        response = self.manage_profile_uc.get_memory(user_id)
        await update.message.reply_text(response)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Reset command received", extra={'user_id': user_id})

        self.conversation_repo.clear_conversation(user_id)
        await update.message.reply_text("🧹 Давай начнем наш разговор заново! Как твои дела?")

    async def health(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        self.logger.info("Health check requested", extra={'user_id': user_id})

        health_status = self.health_checker.perform_health_check()

        status_emoji = "🟢" if health_status.status == "healthy" else "🟡" if health_status.status == "degraded" else "🔴"

        response = f"{status_emoji} **System Health: {health_status.status.upper()}**\n\n"

        for check_name, details in health_status.details.items():
            check_emoji = "✅" if details.get('status') == 'healthy' else "⚠️" if details.get(
                'status') == 'degraded' else "❌"
            response += f"{check_emoji} **{check_name}**: {details.get('status', 'unknown')}\n"

        await update.message.reply_text(response)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        user_message = update.message.text

        self.logger.info(
            "Message received",
            extra={'user_id': user_id, 'message_length': len(user_message)}
        )

        # Обновляем активность пользователя
        self.proactive_manager.update_user_activity(user_id, user_message)

        try:
            # Сохраняем пользователя
            self.user_repo.save_user(
                self.middleware.create_user_from_telegram(user)
            )

            # Извлекаем и обновляем профиль
            profile_data = self.manage_profile_uc.extract_and_update_profile(user_id, user_message)
            profile = self.profile_repo.get_profile(user_id)

            # Обрабатываем сообщение (АСИНХРОННО!)
            response = await self.handle_message_uc.execute(
                user_id, user_message, FRIEND_PROMPT, profile
            )

            await update.message.reply_text(response)

        except Exception as e:
            self.logger.error(
                f"Error handling message: {e}",
                extra={'user_id': user_id, 'operation': 'handle_message'}
            )
            await update.message.reply_text("😔 Извини, у меня небольшие технические проблемы. Можешь повторить?")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
💫 Я здесь чтобы быть твоим другом!

Команды:
/start - начать/продолжить общение
/profile - посмотреть и изменить профиль
/memory - что я о тебе помню
/reset - начать разговор заново
/health - проверить статус системы (админ)

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
        await update.message.reply_text(help_text)

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("profile", self.profile))
        self.application.add_handler(CommandHandler("memory", self.memory))
        self.application.add_handler(CommandHandler("reset", self.reset))
        self.application.add_handler(CommandHandler("health", self.health))
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
                ai_client=self.ai_client,
                telegram_bot_instance=self  # ← Теперь self полностью создан
            )

            # Запускаем мониторинг
            self._start_proactive_monitoring()
            self.logger.info("Proactive manager initialized")

        except Exception as e:
            self.logger.error(f"Failed to setup proactive manager: {e}")

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

            self.application.run_polling()

        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}")
            raise