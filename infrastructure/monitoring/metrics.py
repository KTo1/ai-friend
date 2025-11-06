# infrastructure/monitoring/metrics.py
import time
import os
from typing import Dict, Any
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
from prometheus_client.exposition import start_http_server
from infrastructure.monitoring.logging import StructuredLogger


class MetricsCollector:
    def __init__(self):
        self.logger = StructuredLogger("metrics")
        self._server_started = False

        # ✅ ПРАВИЛЬНО: Используем классы из prometheus_client

        # 📊 ОСНОВНЫЕ МЕТРИКИ
        self.messages_received = Counter(
            'bot_messages_received_total',
            'Total number of messages received',
            ['type']  # labels для группировки
        )

        self.messages_processed = Counter(
            'bot_messages_processed_total',
            'Total number of messages processed',
            ['status']  # success, error
        )

        self.openai_requests = Counter(
            'ai_requests_total',  # Переименовал для универсальности
            'Total number of AI API requests',
            ['provider', 'status']  # openai, gemini, ollama...
        )

        self.message_processing_time = Histogram(
            'message_processing_duration_seconds',
            'Time spent processing message',
            ['operation'],  # handle_message, generate_response, etc
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]  # Кастомные бакеты
        )

        self.conversation_length = Histogram(
            'conversation_message_count',
            'Number of messages in conversation',
            buckets=[1, 2, 5, 10, 20, 50]
        )

        # 🛡️ МЕТРИКИ БЕЗОПАСНОСТИ И ЛИМИТОВ
        self.requests_blocked = Counter(
            'requests_blocked_total',
            'Total number of requests blocked by various checks',
            ['block_reason']  # user_status, message_validation, technical, token_limit, daily_limit
        )

        self.user_usage = Gauge(
            'user_requests_today',
            'Number of requests user made today',
            ['user_id']
        )

        self.banned_users_access_attempts = Counter(
            'banned_users_access_attempts_total',
            'Number of access attempts by banned users'
        )

        self.inactive_users_access_attempts = Counter(
            'inactive_users_access_attempts_total',
            'Number of access attempts by inactive users'
        )

        self.daily_limits_exceeded = Counter(
            'daily_limits_exceeded_total',
            'Number of times daily limits were exceeded'
        )

        self.token_limits_exceeded = Counter(
            'token_limits_exceeded_total',
            'Number of times token limits were exceeded'
        )

        self.tokens_estimated = Histogram(
            'tokens_estimated_per_request',
            'Estimated tokens per request',
            buckets=[100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
        )

        self.user_not_found_attempts = Counter(
            'user_not_found_attempts_total',
            'Number of attempts by non-existent users'
        )

        self.technical_requests_blocked = Counter(
            'technical_requests_blocked_total',
            'Total number of technical requests blocked',
            ['block_level']  # pre_ai, post_ai, prompt
        )

        # 💰 МЕТРИКИ СТОИМОСТИ
        self.api_cost_estimate = Counter(
            'api_cost_estimate_total',
            'Estimated API cost in dollars',
            ['provider']
        )

        self.expensive_requests = Counter(
            'expensive_requests_total',
            'Number of requests over cost threshold',
            ['cost_range']  # over_0.1, over_1.0
        )

        # 🆕 МЕТРИКИ ДЛЯ АДМИНИСТРАТОРА
        self.admin_actions = Counter(
            'admin_actions_total',
            'Total number of admin actions',
            ['action_type']  # ban, unban, set_limits, etc
        )

        # 🔧 ДОБАВИТЬ: метрика для использованных токенов
        self.tokens_used = Histogram(
            'tokens_used_per_request',
            'Number of tokens used per request',
            buckets=[100, 500, 1000, 2000, 5000, 10000, 20000, 50000]
        )

    # 📊 МЕТОДЫ ДЛЯ РЕГИСТРАЦИИ МЕТРИК

    def record_message_received(self, message_type: str = "text"):
        """Записать получение сообщения"""
        self.messages_received.labels(type=message_type).inc()

    def record_message_processed(self, status: str = "success"):
        """Записать обработку сообщения"""
        self.messages_processed.labels(status=status).inc()

    def record_ai_request(self, provider: str, status: str = "success"):
        """Записать запрос к AI"""
        self.openai_requests.labels(provider=provider, status=status).inc()

    def record_processing_time(self, operation: str, duration: float):
        """Записать время обработки"""
        self.message_processing_time.labels(operation=operation).observe(duration)

    def record_conversation_length(self, length: int):
        """Записать длину конверсации"""
        self.conversation_length.observe(length)

    def record_request_blocked(self, reason: str):
        """Записать блокировку запроса"""
        self.requests_blocked.labels(block_reason=reason).inc()

    def record_user_usage(self, user_id: int, requests_count: int):
        """Записать использование пользователя"""
        self.user_usage.labels(user_id=str(user_id)).set(requests_count)

    def record_banned_user_access_attempt(self):
        """Записать попытку доступа забаненного пользователя"""
        self.banned_users_access_attempts.inc()

    def record_inactive_user_access_attempt(self):
        """Записать попытку доступа неактивного пользователя"""
        self.inactive_users_access_attempts.inc()

    def record_daily_limit_exceeded(self):
        """Записать превышение дневного лимита"""
        self.daily_limits_exceeded.inc()

    def record_token_limit_exceeded(self, estimated: int, limit: int):
        """Записать превышение лимита токенов"""
        self.token_limits_exceeded.inc()

    def record_tokens_estimated(self, tokens: int):
        """Записать оценку токенов"""
        self.tokens_estimated.observe(tokens)

    def record_user_not_found(self):
        """Записать попытку доступа несуществующего пользователя"""
        self.user_not_found_attempts.inc()

    def record_technical_block(self, level: str):
        """Записать блокировку технического запроса"""
        self.technical_requests_blocked.labels(block_level=level).inc()

    def record_api_cost(self, provider: str, cost: float):
        """Записать стоимость API запроса"""
        self.api_cost_estimate.labels(provider=provider).inc(cost)

        if cost > 0.1:
            self.expensive_requests.labels(cost_range='over_0.1').inc()
        if cost > 1.0:
            self.expensive_requests.labels(cost_range='over_1.0').inc()

    # 🔧 ДОБАВИТЬ: метод для записи использованных токенов
    def record_tokens_used(self, tokens: int):
        """Записать количество использованных токенов"""
        self.tokens_used.observe(tokens)

    def record_admin_action(self, action_type: str):
        """Записать действие администратора"""
        self.admin_actions.labels(action_type=action_type).inc()

    def record_openai_request(self, status: str):
        """Записать запрос к OpenAI API"""
        # 🔧 Используем существующую метрику ai_requests_total
        self.openai_requests.labels(provider="deepseek", status=status).inc()

    def start_metrics_server(self):
        """Запустить сервер метрик"""
        if self._server_started:
            return

        metrics_port = int(os.getenv("METRICS_PORT", "8000"))
        enable_metrics = os.getenv("ENABLE_METRICS", "true").lower() == "true"

        if enable_metrics:
            try:
                start_http_server(metrics_port)
                self._server_started = True
                self.logger.info(f"Metrics server started on port {metrics_port}")

                # Логируем доступные метрики
                available_metrics = [
                    'bot_messages_received_total',
                    'bot_messages_processed_total',
                    'ai_requests_total',
                    'requests_blocked_total',
                    'api_cost_estimate_total'
                ]
                self.logger.info(f"Available metrics: {', '.join(available_metrics)}")

            except Exception as e:
                self.logger.error(f"Failed to start metrics server: {e}")

    def get_metrics(self) -> str:
        """Получить метрики в текстовом формате для Prometheus"""
        return generate_latest(REGISTRY).decode('utf-8')


# Глобальный инстанс метрик
metrics_collector = MetricsCollector()


class Timer:
    """Контекстный менеджер для измерения времени с автоматической записью в метрики"""

    def __init__(self, operation: str):
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        metrics_collector.record_processing_time(self.operation, duration)