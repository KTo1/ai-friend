import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class DatabaseConfig:
    @property
    def name(self):
        return os.getenv("DB_NAME", "friend_bot.db")


@dataclass
class OpenAIConfig:
    @property
    def api_key(self):
        return os.getenv("OPENAI_API_KEY")

    @property
    def model(self):
        return os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    @property
    def max_tokens(self):
        return int(os.getenv("OPENAI_MAX_TOKENS", "500"))

    @property
    def temperature(self):
        return float(os.getenv("OPENAI_TEMPERATURE", "0.7"))


@dataclass
class MonitoringConfig:
    @property
    def log_level(self):
        return os.getenv("LOG_LEVEL", "INFO")

    @property
    def enable_metrics(self):
        return os.getenv("ENABLE_METRICS", "true").lower() == "true"

    @property
    def enable_tracing(self):
        return os.getenv("ENABLE_TRACING", "false").lower() == "true"

    @property
    def metrics_port(self):
        return int(os.getenv("METRICS_PORT", "8000"))

    @property
    def jaeger_host(self):
        return os.getenv("JAEGER_HOST", "localhost")

    @property
    def jaeger_port(self):
        return int(os.getenv("JAEGER_PORT", "6831"))


@dataclass
class BotConfig:
    @property
    def token(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        return token


class Config:
    def __init__(self):
        self._database = DatabaseConfig()
        self._openai = OpenAIConfig()
        self._monitoring = MonitoringConfig()
        self._bot = BotConfig()
        self._deepseek = DeepSeekConfig()

    @property
    def database(self):
        return self._database

    @property
    def openai(self):
        return self._openai

    @property
    def deepseek(self):
        return self._deepseek

    @property
    def monitoring(self):
        return self._monitoring

    @property
    def bot(self):
        return self._bot

    @property
    def rate_limit(self):
        return RateLimitConfig()


@dataclass
class DeepSeekConfig:
    @property
    def api_key(self):
        return os.getenv("DEEPSEEK_API_KEY")

    @property
    def model(self):
        return os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    @property
    def base_url(self):
        return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


@dataclass
class RateLimitConfig:
    @property
    def messages_per_minute(self):
        return int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

    @property
    def messages_per_hour(self):
        return int(os.getenv("RATE_LIMIT_PER_HOUR", "100"))

    @property
    def messages_per_day(self):
        return int(os.getenv("RATE_LIMIT_PER_DAY", "500"))

config = Config()
