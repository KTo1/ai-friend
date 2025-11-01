import logging
import sys
import json
from datetime import datetime
from typing import Dict, Any
import uuid
import os


class JSONFormatter(logging.Formatter):
    """Форматтер для структурированного JSON-логирования"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'trace_id'):
            log_data['trace_id'] = record.trace_id
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation

        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLogger:
    """Класс для структурированного логирования"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.trace_id = str(uuid.uuid4())

    def set_trace_id(self, trace_id: str):
        self.trace_id = trace_id

    def _log_with_context(self, level: int, message: str, extra: Dict[str, Any] = None):
        extra_data = extra or {}
        extra_data['trace_id'] = self.trace_id

        if 'user_id' in extra_data:
            extra_data['user_id'] = extra_data['user_id']

        self.logger.log(level, message, extra=extra_data)

    def info(self, message: str, extra: Dict[str, Any] = None):
        self._log_with_context(logging.INFO, message, extra)

    def error(self, message: str, extra: Dict[str, Any] = None):
        self._log_with_context(logging.ERROR, message, extra)

    def warning(self, message: str, extra: Dict[str, Any] = None):
        self._log_with_context(logging.WARNING, message, extra)

    def debug(self, message: str, extra: Dict[str, Any] = None):
        self._log_with_context(logging.DEBUG, message, extra)

    def metric(self, name: str, value: float, tags: Dict[str, str] = None):
        """Логирование метрик"""
        extra = {'metric_name': name, 'metric_value': value}
        if tags:
            extra.update(tags)
        self.info(f"METRIC: {name} = {value}", extra=extra)


def setup_logging():
    """Настройка логирования для приложения"""
    root_logger = logging.getLogger()
    log_level = os.getenv("LOG_LEVEL", "INFO")
    root_logger.setLevel(getattr(logging, log_level))

    formatter = JSONFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler('friend_bot.log')
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    return root_logger