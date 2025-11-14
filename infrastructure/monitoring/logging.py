import logging
import sys
import json
import os
from datetime import datetime
from typing import Dict, Any
import uuid
from pythonjsonlogger import jsonlogger


class ELKJSONFormatter(jsonlogger.JsonFormatter):
    """Форматтер для ELK-совместимого JSON-логирования"""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)

        # Стандартные поля для ELK
        log_record['@timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['level'] = record.levelname
        log_record['logger_name'] = record.name
        log_record['service'] = 'friend-bot'
        log_record['environment'] = os.getenv('ENVIRONMENT', 'development')

        # Убираем дублирующиеся поля
        if 'message' in log_record and 'msg' in log_record:
            log_record.pop('msg')
        if 'message' in log_record and 'message' in message_dict:
            log_record.pop('message')


class StructuredLogger:
    """Класс для структурированного логирования с ELK-поддержкой"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.trace_id = str(uuid.uuid4())

    def set_trace_id(self, trace_id: str):
        self.trace_id = trace_id

    def _log_with_context(self, level: int, message: str, extra: Dict[str, Any] = None):
        extra_data = extra or {}
        extra_data['trace_id'] = self.trace_id

        # Добавляем user_id если есть
        if 'user_id' in extra_data:
            extra_data['user_id'] = extra_data['user_id']

        # Добавляем информацию о сервисе
        extra_data['service'] = 'friend-bot'
        extra_data['component'] = self.logger.name

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
        """Логирование метрик для ELK"""
        extra = {
            'metric_name': name,
            'metric_value': value,
            'type': 'metric'
        }
        if tags:
            extra.update(tags)
        self.info(f"METRIC: {name} = {value}", extra=extra)


def setup_logging():
    """Настройка логирования для ELK"""
    root_logger = logging.getLogger()
    log_level = os.getenv("LOG_LEVEL", "INFO")
    root_logger.setLevel(getattr(logging, log_level))

    # Форматтер для ELK
    formatter = ELKJSONFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s',
        rename_fields={
            'level': 'level',
            'name': 'logger_name'
        }
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # File handler для Logstash/Filebeat
    os.makedirs('logs', exist_ok=True)
    file_handler = logging.FileHandler('logs/friend-bot.log')
    file_handler.setFormatter(formatter)

    # Добавляем handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Настраиваем логирование для сторонних библиотек
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return root_logger