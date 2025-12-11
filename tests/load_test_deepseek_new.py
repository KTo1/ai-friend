import asyncio
import random
import time
import json
import os
import sys
from datetime import datetime
from statistics import mean
from typing import Dict, List, Optional
from dataclasses import dataclass

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class TestResult:
    successful: int = 0
    failed: int = 0
    rate_limited: int = 0
    ai_errors: int = 0
    message_length_errors: int = 0
    block_errors: int = 0
    total_messages: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    response_times: List[float] = []
    processing_times: List[float] = []
    concurrent_requests: int = 0
    max_concurrent: int = 0


class DeepSeekLoadTester:
    def __init__(self, total_users: int = 50, messages_per_second: int = 1):
        self.total_users = total_users
        self.target_messages_per_second = messages_per_second
        self.results = TestResult()

        # Семафор для ограничения параллелизма
        self.semaphore = asyncio.Semaphore(50)

        # Устанавливаем DeepSeek как провайдера
        os.environ['AI_PROVIDER'] = 'deepseek'
        os.environ['LOG_LEVEL'] = 'ERROR'  # Уменьшаем логи

        # Инициализируем компоненты
        self.database = None
        self.ai_client = None
        self.services = {}
        self.repositories = {}
        self.use_cases = {}

        # Тестовые сообщения
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

    async def _initialize_components(self):
        """Инициализация всех компонентов бота с новой архитектурой"""
        try:
            print("🔧 Initializing bot components with new architecture...")

            # Инициализация базы данных
            from infrastructure.database.database import Database
            self.database = Database()

            # Инициализация всех репозиториев
            from infrastructure.database.repositories.user_repository import UserRepository
            from infrastructure.database.repositories.profile_repository import ProfileRepository
            from infrastructure.database.repositories.conversation_repository import ConversationRepository
            from infrastructure.database.repositories.tariff_repository import TariffRepository
            from infrastructure.database.repositories.rag_repository import RAGRepository
            from infrastructure.database.repositories.user_stats_repository import UserStatsRepository
            from infrastructure.database.repositories.rate_limit_tracking_repository import RateLimitTrackingRepository

            self.repositories = {
                'user': UserRepository(self.database),
                'profile': ProfileRepository(self.database),
                'conversation': ConversationRepository(self.database),
                'tariff': TariffRepository(self.database),
                'rag': RAGRepository(self.database),
                'user_stats': UserStatsRepository(self.database),
                'rate_limit': RateLimitTrackingRepository(self.database)
            }

            # Инициализация AI клиента
            from infrastructure.ai.ai_factory import AIFactory
            self.ai_client = AIFactory.create_client()

            # Инициализация сервисов (с новой архитектурой)
            from domain.service.admin_service import AdminService
            from domain.service.block_service import BlockService
            from domain.service.tariff_service import TariffService
            from domain.service.limit_service import LimitService
            from domain.service.rag_service import RAGService
            from domain.service.profile_service import ProfileService
            from domain.service.context_service import ContextService

            self.services = {
                'admin': AdminService(self.repositories['user']),
                'block': BlockService(self.repositories['user']),
                'tariff': TariffService(self.repositories['tariff']),
                'limit': LimitService(self.repositories['rate_limit'], self.repositories['user_stats']),
                'rag': RAGService(self.ai_client),
                'profile': ProfileService(self.ai_client),
                'context': ContextService()
            }

            # Инициализация Use Cases (с новой архитектурой)
            from application.use_case.start_conversation import StartConversationUseCase
            from application.use_case.manage_profile import ManageProfileUseCase
            from application.use_case.handle_message import HandleMessageUseCase
            from application.use_case.check_limits import CheckLimitsUseCase
            from application.use_case.manage_tariff import ManageTariffUseCase
            from application.use_case.manage_rag import ManageRAGUseCase
            from application.use_case.manage_user_limits import ManageUserLimitsUseCase

            self.use_cases = {
                'start_conversation': StartConversationUseCase(
                    self.repositories['user'],
                    self.repositories['profile']
                ),
                'manage_profile': ManageProfileUseCase(
                    self.repositories['profile'],
                    self.ai_client
                ),
                'handle_message': HandleMessageUseCase(
                    self.repositories['conversation'],
                    self.ai_client
                ),
                'check_limits': CheckLimitsUseCase(self.services['limit']),
                'manage_tariff': ManageTariffUseCase(self.services['tariff']),
                'manage_rag': ManageRAGUseCase(
                    self.repositories['rag'],
                    self.services['rag']
                ),
                'manage_user_limits': ManageUserLimitsUseCase(
                    self.repositories['user_stats']
                )
            }

            print("✅ Bot components initialized with new architecture")

        except Exception as e:
            print(f"❌ Error initializing bot components: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def _close_resources(self):
        """Корректное закрытие ресурсов"""
        print("🧹 Closing resources...")

        if self.ai_client and hasattr(self.ai_client, 'close'):
            await self.ai_client.close()
            print("✅ AI client closed")

        if self.database and hasattr(self.database, 'close'):
            self.database.close()
            print("✅ Database connection closed")

    async def _check_deepseek_availability(self) -> bool:
        """Проверка доступности DeepSeek API"""
        try:
            print("🔍 Checking DeepSeek availability...")

            if not self.ai_client:
                print("❌ AI client is not initialized")
                return False

            # Простой тестовый запрос
            test_messages = [
                {"role": "user", "content": "Привет, ответь 'тест успешен'"}
            ]

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

    async def _create_test_users_with_tariffs(self):
        """Создание тестовых пользователей с тарифами"""
        try:
            print(f"👥 Creating {self.total_users} test users with tariffs...")

            from domain.entity.user import User
            from domain.entity.profile import UserProfile

            # Получаем дефолтный тариф
            default_tariff = self.services['tariff'].get_default_tariff()
            if not default_tariff:
                print("❌ No default tariff found")
                return False

            for user_id in range(1, self.total_users + 1):
                # Создаем пользователя
                user = User(
                    user_id=user_id,
                    username=f"testuser{user_id}",
                    first_name=f"Test{user_id}",
                    last_name="User"
                )
                self.repositories['user'].save_user(user)

                # Создаем профиль
                profile = UserProfile(user_id=user_id)
                self.repositories['profile'].save_profile(profile)

                # Назначаем дефолтный тариф
                success, message = self.services['tariff'].assign_tariff_to_user(
                    user_id,
                    default_tariff.id
                )

                if not success:
                    print(f"⚠️ Failed to assign tariff for user {user_id}: {message}")

            print(f"✅ Created {self.total_users} test users with tariffs")
            return True

        except Exception as e:
            print(f"❌ Error creating test users: {e}")
            return False

    async def _cleanup_test_data(self):
        """Очистка тестовых данных"""
        try:
            print("🧹 Cleaning up test data...")

            # Удаляем в правильном порядке (с учетом foreign keys)
            for user_id in range(1, self.total_users + 1):
                try:
                    # 1. Удаляем conversation_context
                    self.database.execute_query(
                        'DELETE FROM conversation_context WHERE user_id = %s',
                        (user_id,)
                    )

                    # 2. Удаляем user_rag_memories
                    self.database.execute_query(
                        'DELETE FROM user_rag_memories WHERE user_id = %s',
                        (user_id,)
                    )

                    # 3. Удаляем user_rate_limit_tracking
                    self.database.execute_query(
                        'DELETE FROM user_rate_limit_tracking WHERE user_id = %s',
                        (user_id,)
                    )

                    # 4. Удаляем user_stats
                    self.database.execute_query(
                        'DELETE FROM user_stats WHERE user_id = %s',
                        (user_id,)
                    )

                    # 5. Удаляем user_tariffs
                    self.database.execute_query(
                        'DELETE FROM user_tariffs WHERE user_id = %s',
                        (user_id,)
                    )

                    # 6. Удаляем user_profiles
                    self.database.execute_query(
                        'DELETE FROM user_profiles WHERE user_id = %s',
                        (user_id,)
                    )

                    # 7. Удаляем пользователя
                    self.repositories['user'].delete_user(user_id)

                except Exception as e:
                    print(f"⚠️ Error cleaning up user {user_id}: {e}")

            print("✅ Test data cleaned up")

        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

    async def process_user_message(self, user_id: int, message_text: str) -> bool:
        """Обработка сообщения пользователя (обновленная версия для новой архитектуры)"""
        async with self.semaphore:
            try:
                # Мониторинг параллельных запросов
                self.results.concurrent_requests += 1
                self.results.max_concurrent = max(
                    self.results.max_concurrent,
                    self.results.concurrent_requests
                )

                start_time = time.time()
                ai_response_time = None

                # 1. Проверка блокировки пользователя
                if self.services['block'].is_user_blocked(user_id):
                    self.results.block_errors += 1
                    self.results.total_messages += 1
                    return False

                # 2. Получаем тариф пользователя
                user_tariff = self.services['tariff'].get_user_tariff(user_id)
                if not user_tariff or not user_tariff.tariff_plan:
                    print(f"❌ User {user_id}: No tariff assigned")
                    self.results.failed += 1
                    self.results.total_messages += 1
                    return False

                tariff = user_tariff.tariff_plan

                # 3. Проверка длины сообщения
                is_valid, error_msg = self.services['limit'].check_message_length(
                    user_id, message_text, tariff
                )
                if not is_valid:
                    self.results.message_length_errors += 1
                    self.results.total_messages += 1
                    return False

                # 4. Проверка rate limit (только для обычных пользователей)
                # В тесте мы проверяем всех пользователей
                can_send, limit_message, _ = self.services['limit'].check_rate_limit(
                    user_id, tariff
                )
                if not can_send:
                    self.results.rate_limited += 1
                    self.results.total_messages += 1
                    return False

                # 5. Обновляем активность пользователя
                self.repositories['user'].update_last_seen(user_id)

                # 6. Извлекаем профиль (опционально, для реалистичности)
                try:
                    await self.use_cases['manage_profile'].extract_and_update_profile(
                        user_id, message_text
                    )
                except Exception:
                    pass  # Игнорируем ошибки извлечения профиля в тесте

                # 7. Упрощенный системный промпт для тестов
                system_prompt = "Ты — Айна, дружелюбный ассистент. Отвечай кратко (1-2 предложения)."

                # 8. Обработка сообщения через DeepSeek
                try:
                    # Замеряем время AI ответа
                    ai_start_time = time.time()

                    response = await self.use_cases['handle_message'].execute(
                        user_id=user_id,
                        message=message_text,
                        system_prompt=system_prompt,
                        max_context_messages=tariff.message_limits.max_context_messages
                    )

                    ai_response_time = time.time() - ai_start_time
                    self.results.response_times.append(ai_response_time)

                    # Проверяем что ответ не пустой
                    if not response or len(response.strip()) < 5:
                        raise Exception("Empty AI response")

                except Exception as ai_error:
                    self.results.ai_errors += 1
                    print(f"🤖 User {user_id}: AI Error - {str(ai_error)[:50]}")
                    response = "Привет! Как твои дела? 😊"

                # 9. Записываем использование (как в реальном боте)
                self.services['limit'].record_message_usage(
                    user_id,
                    len(message_text),
                    tariff
                )

                # 10. Сохраняем статистику
                processing_time = time.time() - start_time
                self.results.processing_times.append(processing_time)
                self.results.successful += 1
                self.results.total_messages += 1

                # Выводим информацию о времени
                if random.random() < 0.05:  # Выводим только 5% сообщений
                    time_info = f"({processing_time:.2f}s total"
                    if ai_response_time is not None:
                        time_info += f", {ai_response_time:.2f}s AI"
                    time_info += ")"
                    print(f"✅ User {user_id}: {time_info}")

                return True

            except Exception as e:
                self.results.failed += 1
                self.results.total_messages += 1
                if random.random() < 0.1:  # Выводим только 10% ошибок
                    print(f"❌ User {user_id}: Error - {str(e)[:50]}")
                return False
            finally:
                self.results.concurrent_requests -= 1

    async def run_load_test(self, duration_seconds: int = 60):
        """Запуск нагрузочного теста с новой архитектурой"""
        print(f"🚀 Starting DeepSeek Load Test with new architecture")
        print(f"📊 Users: {self.total_users}, Target Messages/sec: {self.target_messages_per_second}")
        print(f"⏱️ Duration: {duration_seconds}s")
        print(f"🤖 AI Provider: DeepSeek")
        print(f"🔒 Max Concurrent: {self.semaphore._value}")
        print("=" * 60)

        try:
            # 1. Инициализируем компоненты
            await self._initialize_components()

            # 2. Проверяем доступность DeepSeek
            if not await self._check_deepseek_availability():
                print("❌ DeepSeek is not available. Check your API key and network.")
                return

            # 3. Создаем тестовых пользователей с тарифами
            if not await self._create_test_users_with_tariffs():
                print("❌ Failed to create test users")
                return

            # 4. Запускаем нагрузочный тест
            self.results.start_time = time.time()
            start_time = self.results.start_time
            all_tasks = []

            expected_total_messages = self.target_messages_per_second * duration_seconds
            print(f"🎯 Expected total messages: {expected_total_messages}")

            for second in range(duration_seconds):
                print(
                    f"⏱️ Second {second + 1}/{duration_seconds} - Creating {self.target_messages_per_second} messages...")

                # Создаем задачи для текущей секунды
                second_tasks = []
                for _ in range(self.target_messages_per_second):
                    user_id = random.randint(1, self.total_users)
                    message_text = random.choice(self.test_messages)

                    task = asyncio.create_task(
                        self.process_user_message(user_id, message_text)
                    )
                    second_tasks.append(task)
                    all_tasks.append(task)

                # Ждем до конца текущей секунды
                elapsed = time.time() - start_time
                wait_time = max(0, (second + 1) - elapsed)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

                # Выводим прогресс
                completed_this_second = sum(1 for task in second_tasks if task.done())
                print(f"   📈 Completed this second: {completed_this_second}/{self.target_messages_per_second}")

            # 5. Ожидаем завершения всех задач
            print("🔄 Waiting for all tasks to complete...")

            if all_tasks:
                done, pending = await asyncio.wait(
                    all_tasks,
                    timeout=30.0,
                    return_when=asyncio.ALL_COMPLETED
                )

                if pending:
                    print(f"⚠️ {len(pending)} tasks timed out, cancelling...")
                    for task in pending:
                        task.cancel()

            # 6. Сохраняем результаты
            self.results.end_time = time.time()
            total_duration = self.results.end_time - self.results.start_time

            # Рассчитываем реальную скорость
            if total_duration > 0:
                actual_messages_per_second = self.results.total_messages / total_duration
            else:
                actual_messages_per_second = 0

            # Рассчитываем статистику времени
            self._calculate_time_stats(total_duration, actual_messages_per_second)

            # 7. Выводим результаты
            self._print_results()

        except Exception as e:
            print(f"❌ Error during load test: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 8. Очищаем тестовые данные
            await self._cleanup_test_data()

            # 9. Закрываем ресурсы
            await self._close_resources()

    def _calculate_time_stats(self, total_duration: float, actual_messages_per_second: float):
        """Рассчитывает статистику по времени ответов"""
        if self.results.response_times:
            self.results.avg_response_time = mean(self.results.response_times)
            self.results.min_response_time = min(self.results.response_times)
            self.results.max_response_time = max(self.results.response_times)
            if len(self.results.response_times) > 1:
                self.results.response_time_95 = sorted(self.results.response_times)[
                    int(len(self.results.response_times) * 0.95)
                ]
            else:
                self.results.response_time_95 = self.results.response_times[0]
        else:
            self.results.avg_response_time = 0
            self.results.min_response_time = 0
            self.results.max_response_time = 0
            self.results.response_time_95 = 0

        if self.results.processing_times:
            self.results.avg_processing_time = mean(self.results.processing_times)
            self.results.min_processing_time = min(self.results.processing_times)
            self.results.max_processing_time = max(self.results.processing_times)
            if len(self.results.processing_times) > 1:
                self.results.processing_time_95 = sorted(self.results.processing_times)[
                    int(len(self.results.processing_times) * 0.95)
                ]
            else:
                self.results.processing_time_95 = self.results.processing_times[0]
        else:
            self.results.avg_processing_time = 0
            self.results.min_processing_time = 0
            self.results.max_processing_time = 0
            self.results.processing_time_95 = 0

        # Дополнительные метрики
        self.results.total_duration = total_duration
        self.results.actual_messages_per_second = actual_messages_per_second

    def _print_results(self):
        """Вывод результатов"""
        print("\n" + "=" * 60)
        print("📊 DEEPSEEK LOAD TEST RESULTS (NEW ARCHITECTURE)")
        print("=" * 60)
        print(f"Total Users: {self.total_users}")
        print(f"Target Messages/Sec: {self.target_messages_per_second}")
        print(f"Actual Messages/Sec: {self.results.actual_messages_per_second:.2f}")
        print(f"Total Duration: {self.results.total_duration:.2f}s")
        print(f"Total Messages: {self.results.total_messages}")
        print(f"Successful: {self.results.successful}")
        print(f"Failed: {self.results.failed}")
        print(f"Rate Limited: {self.results.rate_limited}")
        print(f"Message Length Errors: {self.results.message_length_errors}")
        print(f"Block Errors: {self.results.block_errors}")
        print(f"AI Errors: {self.results.ai_errors}")
        print(f"Max Concurrent Requests: {self.results.max_concurrent}")

        if self.results.total_messages > 0:
            success_rate = (self.results.successful / self.results.total_messages) * 100
            print(f"Success Rate: {success_rate:.1f}%")

        # Вывод статистики времени
        print("\n⏱️  RESPONSE TIME STATISTICS")
        print("-" * 40)
        if self.results.response_times:
            print(f"AI Response Time (avg): {self.results.avg_response_time:.3f}s")
            print(f"AI Response Time (min): {self.results.min_response_time:.3f}s")
            print(f"AI Response Time (max): {self.results.max_response_time:.3f}s")
            print(f"AI Response Time (95th %): {self.results.response_time_95:.3f}s")
            print(f"Total Processing Time (avg): {self.results.avg_processing_time:.3f}s")
            print(f"Total Processing Time (min): {self.results.min_processing_time:.3f}s")
            print(f"Total Processing Time (max): {self.results.max_processing_time:.3f}s")
            print(f"Total Processing Time (95th %): {self.results.processing_time_95:.3f}s")

            # Разница между общим временем и временем AI
            overhead = self.results.avg_processing_time - self.results.avg_response_time
            print(f"System Overhead: {overhead:.3f}s")
        else:
            print("No response time data available")

        # Ожидаемые vs фактические сообщения
        expected_messages = self.target_messages_per_second * self.results.total_duration
        efficiency = (self.results.total_messages / expected_messages) * 100 if expected_messages > 0 else 0
        print(f"\n🎯 Efficiency: {efficiency:.1f}% of target message rate")

        # Сохраняем результаты в файл
        filename = f"deepseek_load_test_new_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'scenario': {
                    'total_users': self.total_users,
                    'target_messages_per_second': self.target_messages_per_second,
                    'actual_messages_per_second': self.results.actual_messages_per_second,
                    'total_duration': self.results.total_duration
                },
                'results': {
                    'total_messages': self.results.total_messages,
                    'successful': self.results.successful,
                    'failed': self.results.failed,
                    'rate_limited': self.results.rate_limited,
                    'message_length_errors': self.results.message_length_errors,
                    'block_errors': self.results.block_errors,
                    'ai_errors': self.results.ai_errors,
                    'success_rate': success_rate if self.results.total_messages > 0 else 0,
                    'max_concurrent': self.results.max_concurrent
                },
                'timing': {
                    'avg_response_time': self.results.avg_response_time,
                    'min_response_time': self.results.min_response_time,
                    'max_response_time': self.results.max_response_time,
                    'response_time_95': self.results.response_time_95,
                    'avg_processing_time': self.results.avg_processing_time,
                    'min_processing_time': self.results.min_processing_time,
                    'max_processing_time': self.results.max_processing_time,
                    'processing_time_95': self.results.processing_time_95,
                    'system_overhead': overhead
                },
                'timestamp': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Results saved to {filename}")


async def main():
    """Основная функция тестирования"""
    # Проверяем наличие API ключа
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("❌ DEEPSEEK_API_KEY is not set in environment variables")
        print("💡 Add to your .env file: DEEPSEEK_API_KEY=your_key_here")
        return

    # Сценарии тестирования (реалистичные)
    scenarios = [
        # Базовый тест - проверка функциональности
        {"users": 10, "messages_per_second": 1, "duration": 30},

        # Тест средней нагрузки
        {"users": 30, "messages_per_second": 2, "duration": 30},

        # Тест высокой нагрузки
        {"users": 50, "messages_per_second": 3, "duration": 30},

        # Тест максимальной нагрузки (осторожно!)
        {"users": 100, "messages_per_second": 5, "duration": 20},
    ]

    for i, scenario in enumerate(scenarios):
        print(f"\n🎯 Scenario {i + 1}/{len(scenarios)}: {scenario['users']} users, "
              f"{scenario['messages_per_second']} msg/sec, {scenario['duration']}s")

        tester = DeepSeekLoadTester(
            total_users=scenario['users'],
            messages_per_second=scenario['messages_per_second']
        )

        try:
            await tester.run_load_test(duration_seconds=scenario['duration'])
        except Exception as e:
            print(f"❌ Error during test scenario: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Пауза между сценариями (чтобы не превысить лимиты DeepSeek)
            if i < len(scenarios) - 1:
                print("💤 Waiting 10 seconds before next scenario...")
                await asyncio.sleep(10)


if __name__ == "__main__":
    # Настройка окружения для тестов
    os.environ['AI_PROVIDER'] = 'deepseek'
    os.environ['LOG_LEVEL'] = 'ERROR'
    os.environ['DEEPSEEK_MODEL'] = 'deepseek-chat'

    # Загружаем .env файл если есть
    from dotenv import load_dotenv

    load_dotenv()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Load test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        print("🏁 Load test finished")