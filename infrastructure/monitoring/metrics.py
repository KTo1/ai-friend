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