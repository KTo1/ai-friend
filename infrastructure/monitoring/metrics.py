import time
import os
from typing import Dict, Any, Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY
from prometheus_client.exposition import start_http_server
from infrastructure.monitoring.logging import StructuredLogger


class MetricsCollector:
    """Сборщик метрик для приложения"""

    def __init__(self):
        self.logger = StructuredLogger("metrics")
        self._server_started = False

        self.messages_received = Counter(
            'bot_messages_received_total',
            'Total number of messages received',
            ['type']
        )

        self.messages_processed = Counter(
            'bot_messages_processed_total',
            'Total number of messages processed',
            ['status']
        )

        self.openai_requests = Counter(
            'openai_requests_total',
            'Total number of OpenAI API requests',
            ['status']
        )

        self.message_processing_time = Histogram(
            'message_processing_duration_seconds',
            'Time spent processing message',
            ['operation']
        )

        self.openai_response_time = Histogram(
            'openai_response_duration_seconds',
            'Time spent waiting for OpenAI response'
        )

        self.active_users = Gauge(
            'bot_active_users',
            'Number of active users'
        )

        self.conversation_length = Histogram(
            'conversation_message_count',
            'Number of messages in conversation',
            buckets=[1, 2, 5, 10, 20, 50]
        )

        # Метрики для Telegram rate limiting
        self.telegram_send_metrics = Counter(
            'telegram_messages_sent_total',
            'Total number of messages sent to Telegram',
            ['status']
        )

        self.telegram_rate_limit_hits = Counter(
            'telegram_rate_limit_hits_total',
            'Total number of Telegram rate limit hits'
        )

        self.telegram_retry_attempts = Counter(
            'telegram_retry_attempts_total',
            'Total number of Telegram retry attempts'
        )

        # Метрики для аналитики по пользователям (будем использовать Gauge для уникальных значений)
        self.paywall_user_reached = Gauge('paywall_user_reached', 'Users who reached paywall', ['user_id', 'character_id'])

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
            except Exception as e:
                self.logger.error(f"Failed to start metrics server: {e}")

    def record_message_received(self, message_type: str = "text"):
        self.messages_received.labels(type=message_type).inc()

    def record_message_processed(self, status: str = "success"):
        self.messages_processed.labels(status=status).inc()

    def record_openai_request(self, status: str = "success"):
        self.openai_requests.labels(status=status).inc()

    def record_processing_time(self, operation: str, duration: float):
        self.message_processing_time.labels(operation=operation).observe(duration)

    def record_openai_response_time(self, duration: float):
        self.openai_response_time.observe(duration)

    def update_active_users(self, count: int):
        self.active_users.set(count)

    def record_conversation_length(self, length: int):
        self.conversation_length.observe(length)

    # Метрики для Telegram rate limiting
    def record_telegram_send(self, status: str = "success"):
        """Записать метрику отправки Telegram сообщения"""
        self.telegram_send_metrics.labels(status=status).inc()

    def record_telegram_rate_limit_hit(self):
        """Записать попадание в лимит Telegram"""
        self.telegram_rate_limit_hits.inc()

    def record_telegram_retry(self):
        """Записать повторную попытку отправки в Telegram"""
        self.telegram_retry_attempts.inc()

    def get_telegram_metrics(self) -> Dict[str, Any]:
        """Получить метрики Telegram для отладки"""
        return {
            'sent_success': self.telegram_send_metrics.labels(status='success')._value.get(),
            'sent_rate_limit_exceeded': self.telegram_send_metrics.labels(status='rate_limit_exceeded')._value.get(),
            'sent_retry_after': self.telegram_send_metrics.labels(status='retry_after')._value.get(),
            'sent_timeout': self.telegram_send_metrics.labels(status='timeout')._value.get(),
            'rate_limit_hits': self.telegram_rate_limit_hits._value.get(),
            'retry_attempts': self.telegram_retry_attempts._value.get()
        }

    # Детальная метрика для аналитики по пользователям
    def record_user_reached_paywall(self, user_id: int, character_id: int):
        # Устанавливаем 1 для указания, что пользователь достиг paywall
        # Метрика останется в истории Prometheus
        self.paywall_user_reached.labels(
            user_id=str(user_id),
            character_id=str(character_id)
        ).set(1)
        self.logger.info('User reached paywall', extra={
            'user_id': user_id,
            'character_id': character_id,
            'metric_type': 'paywall_user_reached'
        })

class Timer:
    """Контекстный менеджер для измерения времени"""

    def __init__(self, metrics: MetricsCollector, operation: str):
        self.metrics = metrics
        self.operation = operation
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.metrics.record_processing_time(self.operation, duration)
        self.duration = duration


metrics_collector = MetricsCollector()