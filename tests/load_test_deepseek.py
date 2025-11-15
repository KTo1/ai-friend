import asyncio
import random
import time
import json
import os
import sys
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class DeepSeekLoadTester:
    def __init__(self, total_users: int = 50, messages_per_second: int = 1):
        self.total_users = total_users
        self.messages_per_second = messages_per_second
        self.results = {
            'successful': 0,
            'failed': 0,
            'rate_limited': 0,
            'ai_errors': 0,
            'total_messages': 0,
            'start_time': None,
            'end_time': None
        }

        # Устанавливаем DeepSeek как провайдера
        os.environ['AI_PROVIDER'] = 'deepseek'

        # Инициализируем компоненты бота
        self._initialize_bot_components()

        # Тестовые сообщения (оптимизированы для DeepSeek)
        self.test_messages = [
            "Привет",
            "Как дела?",
            "Что нового?",
            "Расскажи о себе",
            "Как настроение?",
            "Что умеешь?",
            "Помоги",
            "Какая погода?",
            "Что посоветуешь?",
            "Как день?",
            "Расскажи шутку",
            "Сколько времени?",
            "Что делаешь?",
            "Как тебя зовут?",
            "Где ты?"
        ]

    def _initialize_bot_components(self):
        """Инициализация всех компонентов бота"""
        try:
            print("🔧 Initializing bot components with DeepSeek...")

            # Инициализация базы данных
            from infrastructure.database.database import Database
            self.database = Database()

            # Инициализация репозиториев
            from infrastructure.database.repositories.user_repository import UserRepository
            from infrastructure.database.repositories.profile_repository import ProfileRepository
            from infrastructure.database.repositories.conversation_repository import ConversationRepository
            from infrastructure.database.repositories.rate_limit_repository import RateLimitRepository
            from infrastructure.database.repositories.message_limit_repository import MessageLimitRepository

            self.user_repo = UserRepository(self.database)
            self.profile_repo = ProfileRepository(self.database)
            self.conversation_repo = ConversationRepository(self.database)
            self.rate_limit_repo = RateLimitRepository(self.database)
            self.message_limit_repo = MessageLimitRepository(self.database)

            # Инициализация AI клиента (DeepSeek)
            from infrastructure.ai.ai_factory import AIFactory
            self.ai_client = AIFactory.create_client()

            # Инициализация сервисов
            from domain.service.rate_limit_service import RateLimitService
            from domain.service.message_limit_service import MessageLimitService
            from domain.service.admin_service import AdminService
            from domain.service.block_service import BlockService
            from domain.service.profile_service import ProfileService

            self.rate_limit_service = RateLimitService(self.rate_limit_repo)
            self.message_limit_service = MessageLimitService(self.message_limit_repo)
            self.admin_service = AdminService(self.user_repo)
            self.block_service = BlockService(self.user_repo)
            self.profile_service = ProfileService(self.ai_client)

            # Инициализация Use Cases
            from application.use_case.start_conversation import StartConversationUseCase
            from application.use_case.manage_profile import ManageProfileUseCase
            from application.use_case.handle_message import HandleMessageUseCase
            from application.use_case.check_rate_limit import CheckRateLimitUseCase
            from application.use_case.validate_message import ValidateMessageUseCase

            self.start_conversation_uc = StartConversationUseCase(self.user_repo, self.profile_repo)
            self.manage_profile_uc = ManageProfileUseCase(self.profile_repo, self.ai_client)
            self.handle_message_uc = HandleMessageUseCase(
                self.conversation_repo, self.ai_client, self.message_limit_service
            )
            self.check_rate_limit_uc = CheckRateLimitUseCase(self.rate_limit_service)
            self.validate_message_uc = ValidateMessageUseCase(self.message_limit_service)

            print("✅ Bot components initialized with DeepSeek")

        except Exception as e:
            print(f"❌ Error initializing bot components: {e}")
            raise

    async def process_user_message(self, user_id: int, message_text: str):
        """Обработка сообщения пользователя с DeepSeek"""
        try:
            start_time = time.time()

            # 1. Проверка блокировки
            if self.block_service.is_user_blocked(user_id):
                self.results['failed'] += 1
                print(f"❌ User {user_id}: Blocked")
                return False

            # 2. Проверка rate limiting
            can_send, rate_limit_msg = self.check_rate_limit_uc.execute(user_id)
            if not can_send:
                self.results['rate_limited'] += 1
                print(f"⏰ User {user_id}: Rate limited")
                return False

            # 3. Валидация сообщения
            is_valid, validation_msg = self.validate_message_uc.execute(user_id, message_text)
            if not is_valid:
                self.results['failed'] += 1
                print(f"❌ User {user_id}: Message validation failed")
                return False

            # 4. Обновляем активность
            self.user_repo.update_last_seen(user_id)

            # 5. Извлекаем профиль (быстро, без глубокого анализа)
            try:
                name, age, interests, mood = await self.manage_profile_uc.extract_and_update_profile(
                    user_id, message_text
                )
            except:
                # Игнорируем ошибки извлечения профиля для тестов
                pass

            # 6. Упрощенный системный промпт для тестов
            system_prompt = "Ты — Айна, дружелюбный ассистент. Отвечай кратко (1-2 предложения)."

            # 7. Обрабатываем сообщение через DeepSeek
            profile_data = self.profile_repo.get_profile(user_id)

            try:
                response = await self.handle_message_uc.execute(
                    user_id, message_text, system_prompt, profile_data
                )

                # Проверяем что ответ не пустой
                if not response or len(response.strip()) < 5:
                    raise Exception("Empty AI response")

            except Exception as ai_error:
                self.results['ai_errors'] += 1
                print(f"🤖 User {user_id}: AI Error - {str(ai_error)}")
                # Fallback ответ
                response = "Привет! Как твои дела? 😊"

            # 8. Записываем использование сообщения
            self.check_rate_limit_uc.record_message_usage(user_id)

            processing_time = time.time() - start_time

            self.results['successful'] += 1
            self.results['total_messages'] += 1

            print(f"✅ User {user_id}: '{message_text}' → ({processing_time:.2f}s)")

            return True

        except Exception as e:
            self.results['failed'] += 1
            self.results['total_messages'] += 1
            print(f"❌ User {user_id}: Error - {str(e)}")
            return False

    async def run_load_test(self, duration_seconds: int = 60):
        """Запуск нагрузочного теста с DeepSeek"""
        print(f"🚀 Starting DeepSeek Load Test")
        print(f"📊 Users: {self.total_users}, Messages/sec: {self.messages_per_second}")
        print(f"⏱️ Duration: {duration_seconds}s")
        print(f"🤖 AI Provider: DeepSeek")
        print("=" * 60)

        # Проверяем доступность DeepSeek
        if not await self._check_deepseek_availability():
            print("❌ DeepSeek is not available. Check your API key and network.")
            return

        self.results['start_time'] = datetime.now().isoformat()
        start_time = time.time()
        tasks = []

        # Создаем тестовых пользователей в базе
        await self._create_test_users()

        for second in range(duration_seconds):
            print(f"⏱️ Second {second + 1}/{duration_seconds}")

            # Создаем задачи для текущей секунды
            for user_offset in range(self.messages_per_second):
                user_id = (second * self.messages_per_second + user_offset) % self.total_users + 1
                message_text = random.choice(self.test_messages)

                task = asyncio.create_task(
                    self.process_user_message(user_id, message_text)
                )
                tasks.append(task)

            # Поддерживаем точную частоту
            elapsed = time.time() - start_time
            wait_time = max(0, (second + 1) - elapsed)
            await asyncio.sleep(wait_time)

        # Ожидаем завершения всех задач
        await asyncio.gather(*tasks, return_exceptions=True)

        self.results['end_time'] = datetime.now().isoformat()
        total_duration = time.time() - start_time
        self.results['total_duration'] = total_duration
        self.results['messages_per_second'] = self.results['total_messages'] / total_duration

        self._print_results()

        # Очищаем тестовых пользователей
        await self._cleanup_test_users()

    async def _check_deepseek_availability(self) -> bool:
        """Проверка доступности DeepSeek API"""
        try:
            print("🔍 Checking DeepSeek availability...")

            # Простой тестовый запрос
            test_messages = [{"role": "user", "content": "Привет, ответь 'тест успешен'"}]
            response = await self.ai_client.generate_response(test_messages, max_tokens=10)

            if response and len(response) > 0:
                print("✅ DeepSeek is available")
                return True
            else:
                print("❌ DeepSeek returned empty response")
                return False

        except Exception as e:
            print(f"❌ DeepSeek check failed: {e}")
            return False

    async def _create_test_users(self):
        """Создание тестовых пользователей в базе"""
        print("👥 Creating test users...")
        from domain.entity.user import User

        for user_id in range(1, self.total_users + 1):
            user = User(
                user_id=user_id,
                username=f"testuser{user_id}",
                first_name=f"TestUser{user_id}",
                last_name="Test"
            )
            self.user_repo.save_user(user)

        print(f"✅ Created {self.total_users} test users")

    async def _cleanup_test_users(self):
        """Очистка тестовых пользователей и связанных данных"""
        print("🧹 Cleaning up test users and related data...")

        try:
            # Удаляем данные в правильном порядке (обратном созданию)
            for user_id in range(1, self.total_users + 1):
                try:
                    # 1. Удаляем conversation_context (первая зависимость)
                    self.database.execute_query(
                        'DELETE FROM conversation_context WHERE user_id = %s',
                        (user_id,)
                    )

                    # 2. Удаляем user_activity
                    self.database.execute_query(
                        'DELETE FROM user_activity WHERE user_id = %s',
                        (user_id,)
                    )

                    # 3. Удаляем user_message_limits
                    self.database.execute_query(
                        'DELETE FROM user_message_limits WHERE user_id = %s',
                        (user_id,)
                    )

                    # 4. Удаляем user_rate_limits
                    self.database.execute_query(
                        'DELETE FROM user_rate_limits WHERE user_id = %s',
                        (user_id,)
                    )

                    # 5. Удаляем user_profiles
                    self.database.execute_query(
                        'DELETE FROM user_profiles WHERE user_id = %s',
                        (user_id,)
                    )

                    # 6. Удаляем user_tariffs (если есть)
                    self.database.execute_query(
                        'DELETE FROM user_tariffs WHERE user_id = %s',
                        (user_id,)
                    )

                    # 7. Теперь удаляем самого пользователя
                    self.user_repo.delete_user(user_id)

                except Exception as e:
                    print(f"⚠️  Error cleaning up user {user_id}: {e}")
                    continue

            print("✅ Test users and related data cleaned up")

        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

    def _print_results(self):
        """Вывод результатов"""
        print("\n" + "=" * 60)
        print("📊 DEEPSEEK LOAD TEST RESULTS")
        print("=" * 60)
        print(f"Total Users: {self.total_users}")
        print(f"Target Messages/Sec: {self.messages_per_second}")
        print(f"Actual Messages/Sec: {self.results['messages_per_second']:.2f}")
        print(f"Total Duration: {self.results['total_duration']:.2f}s")
        print(f"Total Messages: {self.results['total_messages']}")
        print(f"Successful: {self.results['successful']}")
        print(f"Rate Limited: {self.results['rate_limited']}")
        print(f"AI Errors: {self.results['ai_errors']}")
        print(f"Failed: {self.results['failed']}")

        if self.results['total_messages'] > 0:
            success_rate = (self.results['successful'] / self.results['total_messages']) * 100
            print(f"Success Rate: {success_rate:.1f}%")

        # Сохраняем результаты
        filename = f"deepseek_load_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"💾 Results saved to {filename}")


async def main():
    """Основная функция тестирования"""

    # Убедитесь что DEEPSEEK_API_KEY установлен в .env
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("❌ DEEPSEEK_API_KEY is not set in environment variables")
        print("💡 Add to your .env file: DEEPSEEK_API_KEY=your_key_here")
        return

    # Сценарии тестирования (осторожные для DeepSeek)
    scenarios = [
        {"users": 5, "messages_per_second": 1, "duration": 30},
        # {"users": 10, "messages_per_second": 1, "duration": 30},
        # {"users": 20, "messages_per_second": 1, "duration": 30},
        # {"users": 30, "messages_per_second": 1, "duration": 30},
        # {"users": 10, "messages_per_second": 2, "duration": 20},  # Более агрессивный
    ]

    for scenario in scenarios:
        print(f"\n🎯 Testing scenario: {scenario['users']} users, "
              f"{scenario['messages_per_second']} msg/sec, {scenario['duration']}s")

        tester = DeepSeekLoadTester(
            total_users=scenario['users'],
            messages_per_second=scenario['messages_per_second']
        )

        await tester.run_load_test(duration_seconds=scenario['duration'])

        # Пауза между сценариями (чтобы не превысить лимиты DeepSeek)
        print("💤 Waiting 10 seconds before next scenario...")
        await asyncio.sleep(10)


if __name__ == "__main__":
    # Настройка окружения для тестов
    os.environ['AI_PROVIDER'] = 'deepseek'
    os.environ['LOG_LEVEL'] = 'ERROR'  # Уменьшаем логи для тестов
    os.environ['DEEPSEEK_MODEL'] = 'deepseek-chat'

    # Загружаем .env файл если есть
    from dotenv import load_dotenv

    load_dotenv()

    asyncio.run(main())