import asyncio
import random
import time
import json
import os
import sys
from datetime import datetime
from statistics import mean
from typing import Dict, List, Optional
from dataclasses import dataclass, field

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
    response_times: List[float] = field(default_factory=list)
    processing_times: List[float] = field(default_factory=list)
    concurrent_requests: int = 0
    max_concurrent: int = 0


class DeepSeekAdvancedLoadTester:
    def __init__(self, total_users: int = 50, messages_per_second: int = 1):
        self.total_users = total_users
        self.target_messages_per_second = messages_per_second

        # Список созданных тестовых пользователей
        self.created_user_ids = []

        # Результаты теста
        self.results = TestResult()

        # Семафор для контроля параллелизма
        self.semaphore = asyncio.Semaphore(100)

        # Устанавливаем DeepSeek как провайдера
        os.environ['AI_PROVIDER'] = 'deepseek'
        os.environ['LOG_LEVEL'] = 'ERROR'

        # Компоненты бота
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

    async def initialize(self):
        """Инициализация всех компонентов бота"""
        print("🔧 Initializing bot components with advanced architecture...")

        try:
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

            # Инициализация сервисов
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

            # Инициализация Use Cases
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

            print("✅ Bot components initialized with advanced architecture")

        except Exception as e:
            print(f"❌ Error initializing bot components: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def cleanup(self):
        """Корректная очистка ресурсов"""
        print("🧹 Cleaning up resources...")

        if self.ai_client and hasattr(self.ai_client, 'close'):
            await self.ai_client.close()
            print("✅ AI client closed")

        # НЕ закрываем базу данных, так как нет метода close
        print("⚠️ Database connection left open (no close method)")

    async def create_test_users(self):
        """Создание тестовых пользователей в реальной базе"""
        print(f"👥 Creating {self.total_users} test users...")

        from domain.entity.user import User
        from domain.entity.profile import UserProfile

        # Получаем дефолтный тариф
        default_tariff = self.services['tariff'].get_default_tariff()

        if not default_tariff:
            print("❌ No default tariff found, checking available tariffs...")
            all_tariffs = self.services['tariff'].get_all_tariffs(active_only=True)
            if all_tariffs:
                default_tariff = all_tariffs[0]
                print(f"✅ Using first available tariff: {default_tariff.name}")
            else:
                print("⚠️ No tariffs found, users will be created without tariffs")

        # Генерируем ID от 1000000
        base_id = 1000000

        for i in range(self.total_users):
            user_id = base_id + i

            try:
                # Создаем пользователя
                user = User(
                    user_id=user_id,
                    username=f"loadtest_{user_id}",
                    first_name=f"LoadTest_{user_id}",
                    last_name="Bot"
                )
                self.repositories['user'].save_user(user)

                # Создаем профиль
                profile = UserProfile(user_id=user_id)
                self.repositories['profile'].save_profile(profile)

                # Назначаем тариф если есть
                if default_tariff:
                    success, message = self.services['tariff'].assign_tariff_to_user(
                        user_id,
                        default_tariff.id
                    )
                    if not success:
                        print(f"⚠️ Failed to assign tariff for user {user_id}: {message}")
                    else:
                        # Обнуляем счетчики лимитов для тестовых пользователей
                        self.repositories['rate_limit'].db.execute_query(
                            '''
                            INSERT INTO user_rate_limit_tracking
                            (user_id, minute_counter, hour_counter, day_counter,
                             last_minute_reset, last_hour_reset, last_day_reset, updated_at)
                            VALUES (%s, 0, 0, 0, NOW(), NOW(), NOW(), NOW()) ON CONFLICT (user_id) DO
                            UPDATE SET
                                minute_counter = 0,
                                hour_counter = 0,
                                day_counter = 0,
                                last_minute_reset = NOW(),
                                last_hour_reset = NOW(),
                                last_day_reset = NOW()
                            ''',
                            (user_id,)
                        )

                self.created_user_ids.append(user_id)

                if (i + 1) % 10 == 0:
                    print(f"  Created {i + 1}/{self.total_users} users...")

            except Exception as e:
                print(f"⚠️ Error creating user {user_id}: {e}")

        print(f"✅ Created {len(self.created_user_ids)} test users")

    async def cleanup_test_users(self):
        """Удаление тестовых пользователей из базы"""
        if not self.created_user_ids:
            print("⚠️ No test users to clean up")
            return

        print(f"🧹 Cleaning up {len(self.created_user_ids)} test users...")

        for user_id in self.created_user_ids:
            try:
                # Удаляем в правильном порядке (с учетом foreign keys)
                self.database.execute_query(
                    'DELETE FROM conversation_context WHERE user_id = %s',
                    (user_id,)
                )

                self.database.execute_query(
                    'DELETE FROM user_rag_memories WHERE user_id = %s',
                    (user_id,)
                )

                self.database.execute_query(
                    'DELETE FROM user_rate_limit_tracking WHERE user_id = %s',
                    (user_id,)
                )

                self.database.execute_query(
                    'DELETE FROM user_stats WHERE user_id = %s',
                    (user_id,)
                )

                self.database.execute_query(
                    'DELETE FROM user_tariffs WHERE user_id = %s',
                    (user_id,)
                )

                self.database.execute_query(
                    'DELETE FROM user_profiles WHERE user_id = %s',
                    (user_id,)
                )

                self.database.execute_query(
                    'DELETE FROM users WHERE user_id = %s',
                    (user_id,)
                )

            except Exception as e:
                print(f"⚠️ Error cleaning up user {user_id}: {e}")

        print("✅ Test users cleaned up")

    async def test_deepseek_connection(self):
        """Тестирование соединения с DeepSeek"""
        print("🔍 Testing DeepSeek connection...")

        try:
            test_messages = [{"role": "user", "content": "Привет, ответь 'тест успешен'"}]
            start_time = time.time()
            response = await self.ai_client.generate_response(test_messages, max_tokens=10)
            response_time = time.time() - start_time

            if response and len(response) > 0:
                print(f"✅ DeepSeek connected, response time: {response_time:.2f}s")
                print(f"   Response: {response[:50]}...")
                return True
            else:
                print("❌ DeepSeek returned empty response")
                return False

        except Exception as e:
            print(f"❌ DeepSeek connection failed: {e}")
            return False

    async def process_single_message(self, user_id: int, message_text: str) -> bool:
        """Обработка одного сообщения (полная имитация бота)"""
        async with self.semaphore:
            try:
                # Отслеживаем параллельные запросы
                self.results.concurrent_requests += 1
                self.results.max_concurrent = max(
                    self.results.max_concurrent,
                    self.results.concurrent_requests
                )

                start_time = time.time()

                # 1. Проверка блокировки пользователя
                if self.services['block'].is_user_blocked(user_id):
                    self.results.block_errors += 1
                    self.results.total_messages += 1
                    return False

                # 2. Получаем тариф пользователя
                user_tariff = self.services['tariff'].get_user_tariff(user_id)
                if not user_tariff or not user_tariff.tariff_plan:
                    # Назначаем дефолтный тариф
                    default_tariff = self.services['tariff'].get_default_tariff()
                    if default_tariff:
                        self.services['tariff'].assign_tariff_to_user(user_id, default_tariff.id)
                        user_tariff = self.services['tariff'].get_user_tariff(user_id)

                if not user_tariff or not user_tariff.tariff_plan:
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

                # 4. Проверка rate limit
                can_send, limit_message, _ = self.services['limit'].check_rate_limit(
                    user_id, tariff
                )
                if not can_send:
                    self.results.rate_limited += 1
                    self.results.total_messages += 1
                    return False

                # 5. Обновляем активность пользователя
                self.repositories['user'].update_last_seen(user_id)

                # 6. Извлекаем профиль
                try:
                    await self.use_cases['manage_profile'].extract_and_update_profile(
                        user_id, message_text
                    )
                except Exception:
                    pass  # Игнорируем ошибки извлечения профиля в тесте

                # 7. Подготавливаем системный промпт (упрощенный для теста)
                system_prompt = "Ты — дружелюбный ассистент. Отвечай кратко."

                # 8. Обработка сообщения через DeepSeek
                try:
                    ai_start_time = time.time()

                    response = await self.use_cases['handle_message'].execute(
                        user_id=user_id,
                        message=message_text,
                        system_prompt=system_prompt,
                        max_context_messages=tariff.message_limits.max_context_messages
                    )

                    ai_response_time = time.time() - ai_start_time
                    self.results.response_times.append(ai_response_time)

                    if not response:
                        raise Exception("Empty response from DeepSeek")

                except Exception as ai_error:
                    self.results.ai_errors += 1
                    if random.random() < 0.05:
                        print(f"🤖 AI Error for user {user_id}: {str(ai_error)[:50]}")
                    response = "Привет! Как дела?"

                # 9. Записываем использование
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

                # Логируем прогресс
                if self.results.successful % 20 == 0 and self.results.response_times:
                    avg_response = mean(self.results.response_times[-20:])
                    print(f"✅ Processed {self.results.successful} messages, "
                          f"avg response: {avg_response:.2f}s, "
                          f"concurrent: {self.results.concurrent_requests}")

                return True

            except Exception as e:
                self.results.failed += 1
                self.results.total_messages += 1
                if random.random() < 0.05:
                    print(f"❌ Error for user {user_id}: {str(e)[:50]}")
                return False
            finally:
                self.results.concurrent_requests -= 1

    async def run_load_test(self, duration_seconds: int = 60):
        """Запуск нагрузочного теста с расширенной архитектурой"""
        print(f"🚀 Starting ADVANCED DeepSeek Load Test")
        print(f"📊 Users: {self.total_users}, Target: {self.target_messages_per_second} msg/sec")
        print(f"⏱️ Duration: {duration_seconds}s")
        print(f"🤖 AI Provider: DeepSeek")
        print(f"💰 Real API calls: YES")
        print(f"🗄️ Real database: YES")
        print("=" * 60)

        test_start = time.time()

        try:
            # Инициализируем компоненты
            await self.initialize()

            # Проверяем соединение с DeepSeek
            if not await self.test_deepseek_connection():
                return

            # Создаем тестовых пользователей
            await self.create_test_users()

            if not self.created_user_ids:
                print("❌ No test users created")
                return

            # Запускаем нагрузку
            print(f"\n🔥 Starting load generation...")
            print(f"   Using {len(self.created_user_ids)} test users")
            print(f"   Target: {self.target_messages_per_second} messages per second")

            self.results.start_time = time.time()
            all_tasks = []

            # Генерируем нагрузку по секундам
            for second in range(duration_seconds):
                second_start = time.time()

                # Создаем задачи для текущей секунды
                tasks_for_second = []
                for _ in range(self.target_messages_per_second):
                    if not self.created_user_ids:
                        continue

                    user_id = random.choice(self.created_user_ids)
                    message = random.choice(self.test_messages)

                    task = asyncio.create_task(
                        self.process_single_message(user_id, message)
                    )
                    tasks_for_second.append(task)
                    all_tasks.append(task)

                # Ждем завершения задач этой секунды
                if tasks_for_second:
                    try:
                        results = await asyncio.gather(
                            *tasks_for_second,
                            return_exceptions=True
                        )

                        successful = sum(1 for r in results if r is True)
                        failed = sum(1 for r in results if r is False)
                        exceptions = sum(1 for r in results if isinstance(r, Exception))

                        print(f"⏱️ Second {second + 1}/{duration_seconds}: "
                              f"{successful} ok, {failed} failed, {exceptions} errors, "
                              f"{self.results.concurrent_requests} concurrent")

                    except Exception as e:
                        print(f"⚠️ Error in second {second + 1}: {e}")

                # Ждем до конца секунды
                elapsed = time.time() - second_start
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)

            # Ждем завершения оставшихся задач
            print("\n🔄 Waiting for remaining tasks...")
            if all_tasks:
                try:
                    await asyncio.wait(all_tasks, timeout=15)
                except Exception as e:
                    print(f"⚠️ Error waiting for tasks: {e}")

            # Вычисляем итоги
            self.results.end_time = time.time()
            total_time = self.results.end_time - self.results.start_time

            # Выводим результаты
            self._print_results(total_time)

        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
        except Exception as e:
            print(f"\n❌ Test error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Очищаем тестовых пользователей
            await self.cleanup_test_users()

            # Закрываем ресурсы
            await self.cleanup()

            print("\n🏁 Test finished")

    def _calculate_statistics(self, total_time: float) -> Dict:
        """Рассчитывает статистику результатов"""
        stats = {
            'total_time': total_time,
            'actual_mps': self.results.total_messages / total_time if total_time > 0 else 0
        }

        if self.results.total_messages > 0:
            stats['success_rate'] = (self.results.successful / self.results.total_messages) * 100
        else:
            stats['success_rate'] = 0

        # Статистика времени ответа
        if self.results.response_times:
            stats['avg_response'] = mean(self.results.response_times)
            stats['min_response'] = min(self.results.response_times)
            stats['max_response'] = max(self.results.response_times)

            # 95-й перцентиль
            if len(self.results.response_times) > 1:
                sorted_times = sorted(self.results.response_times)
                index_95 = int(len(sorted_times) * 0.95)
                stats['response_95'] = sorted_times[index_95]
            else:
                stats['response_95'] = self.results.response_times[0]
        else:
            stats['avg_response'] = 0
            stats['min_response'] = 0
            stats['max_response'] = 0
            stats['response_95'] = 0

        return stats

    def _print_results(self, total_time: float):
        """Вывод результатов теста"""
        stats = self._calculate_statistics(total_time)

        print("\n" + "=" * 60)
        print("📊 ADVANCED LOAD TEST RESULTS")
        print("=" * 60)

        print(f"\n⏱️  TIMING:")
        print(f"  Test duration: {total_time:.1f}s")
        print(f"  Target messages/sec: {self.target_messages_per_second}")
        print(f"  Actual messages/sec: {stats['actual_mps']:.2f}")

        print(f"\n📊 MESSAGES:")
        print(f"  Total messages: {self.results.total_messages}")
        print(f"  Successful: {self.results.successful}")
        print(f"  Failed: {self.results.failed}")
        print(f"  Rate limited: {self.results.rate_limited}")
        print(f"  AI errors: {self.results.ai_errors}")
        print(f"  Message length errors: {self.results.message_length_errors}")
        print(f"  Block errors: {self.results.block_errors}")
        print(f"  Success rate: {stats['success_rate']:.1f}%")

        print(f"\n🚀 PERFORMANCE:")
        print(f"  Max concurrent requests: {self.results.max_concurrent}")
        print(f"  Created test users: {len(self.created_user_ids)}")

        if self.results.response_times:
            print(f"\n⏱️  DEEPSEEK RESPONSE TIMES:")
            print(f"  Average: {stats['avg_response']:.3f}s")
            print(f"  Minimum: {stats['min_response']:.3f}s")
            print(f"  Maximum: {stats['max_response']:.3f}s")
            print(f"  95th percentile: {stats['response_95']:.3f}s")
            print(f"  Total AI requests: {len(self.results.response_times)}")

        # Сохраняем в файл
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"advanced_load_test_{timestamp}.json"

        results_data = {
            'timestamp': datetime.now().isoformat(),
            'scenario': {
                'users': self.total_users,
                'target_mps': self.target_messages_per_second,
                'actual_mps': stats['actual_mps'],
                'duration': total_time,
                'created_users': len(self.created_user_ids)
            },
            'results': {
                'total_messages': self.results.total_messages,
                'successful': self.results.successful,
                'failed': self.results.failed,
                'rate_limited': self.results.rate_limited,
                'ai_errors': self.results.ai_errors,
                'message_length_errors': self.results.message_length_errors,
                'block_errors': self.results.block_errors,
                'success_rate': stats['success_rate'],
                'max_concurrent': self.results.max_concurrent
            },
            'timing': {
                'avg_response': stats['avg_response'],
                'min_response': stats['min_response'],
                'max_response': stats['max_response'],
                'response_95': stats['response_95'],
                'total_ai_requests': len(self.results.response_times)
            }
        }

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Results saved to {filename}")

        # Рекомендации
        print(f"\n💡 RECOMMENDATIONS:")

        if stats['actual_mps'] < self.target_messages_per_second * 0.8:
            print(
                f"  ⚠️  System underperforming: {stats['actual_mps']:.1f} msg/sec vs target {self.target_messages_per_second}")
            print(f"  📈 Consider: Increase concurrent limit from {self.semaphore._value}")
        else:
            print(f"  ✅ System meets performance target")

        if self.results.rate_limited > 0:
            print(f"  ⚠️  {self.results.rate_limited} rate limit hits detected")
            print(f"  📉 Consider: Adjusting tariff rate limits or user distribution")

        if stats['avg_response'] > 2.0:
            print(f"  ⚠️  High AI response time: {stats['avg_response']:.1f}s")
            print(f"  🌐 Check: DeepSeek API latency and network connection")


def main():
    """Основная функция с расширенными настройками"""
    # Проверяем API ключ
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("❌ ERROR: DEEPSEEK_API_KEY is not set!")
        print("💡 Add to your .env file:")
        print("   DEEPSEEK_API_KEY=your_api_key_here")
        return

    print("🤖 ADVANCED DEEPSEEK LOAD TESTER")
    print("=" * 50)

    # Предупреждение
    print("\n⚠️  WARNING: This test will:")
    print("   - Send REAL requests to DeepSeek API")
    print("   - Create REAL users in your database")
    print("   - Use REAL API credits")
    print("   - Store REAL conversation history")
    print("\nThe test environment will be cleaned up after completion.")

    confirm = input("\nContinue? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Test cancelled.")
        return

    # Выбор сценария
    print("\n📋 AVAILABLE TEST SCENARIOS:")
    print("1. Smoke Test (5 users, 1 msg/sec, 10s)")
    print("2. Light Load (20 users, 2 msg/sec, 30s)")
    print("3. Medium Load (50 users, 3 msg/sec, 30s)")
    print("4. Heavy Load (100 users, 5 msg/sec, 30s)")
    print("5. Stress Test (200 users, 10 msg/sec, 20s)")
    print("6. Target load (1000 users, 100 msg/sec, 10s)")
    print("7. Custom Configuration")

    try:
        choice = input("\nSelect scenario (1-7): ").strip()

        if choice == '1':
            users, mps, duration = 5, 1, 10
        elif choice == '2':
            users, mps, duration = 20, 2, 30
        elif choice == '3':
            users, mps, duration = 50, 3, 30
        elif choice == '4':
            users, mps, duration = 100, 5, 30
        elif choice == '5':
            users, mps, duration = 200, 10, 20
        elif choice == '6':
            users, mps, duration = 1000, 100, 10
        elif choice == '7':
            users = int(input("Number of test users: "))
            mps = int(input("Messages per second: "))
            duration = int(input("Test duration (seconds): "))
        else:
            print("Invalid choice, using Medium Load.")
            users, mps, duration = 50, 3, 30

        # Предварительный расчет
        print(f"\n🎯 TEST CONFIGURATION:")
        print(f"  Test users: {users}")
        print(f"  Messages/sec: {mps}")
        print(f"  Duration: {duration}s")
        print(f"  Estimated total messages: {mps * duration}")
        print(f"  Estimated API cost: ~${mps * duration * 0.0001:.4f}")

        confirm_final = input("\nStart test? (yes/no): ").strip().lower()
        if confirm_final != 'yes':
            print("Test cancelled.")
            return

        # Запускаем тест
        tester = DeepSeekAdvancedLoadTester(
            total_users=users,
            messages_per_second=mps
        )

        asyncio.run(tester.run_load_test(duration_seconds=duration))

    except ValueError as e:
        print(f"❌ Invalid input: {e}")
    except KeyboardInterrupt:
        print("\n\n🛑 Test cancelled by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Настройка окружения
    os.environ['AI_PROVIDER'] = 'deepseek'
    os.environ['LOG_LEVEL'] = 'ERROR'
    os.environ['DEEPSEEK_MODEL'] = 'deepseek-chat'

    # Загружаем .env
    from dotenv import load_dotenv

    load_dotenv()

    # Запускаем
    main()