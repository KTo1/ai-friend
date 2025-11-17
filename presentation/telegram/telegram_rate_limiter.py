import asyncio
import time
from typing import Dict, Optional
from dataclasses import dataclass
from contextlib import asynccontextmanager
from infrastructure.monitoring.logging import StructuredLogger


@dataclass
class TelegramRateLimitConfig:
    """Конфигурация лимитов Telegram API"""
    messages_per_second: int = 30  # Общий лимит Telegram
    burst_limit: int = 5  # Максимум сообщений в короткий период


class TelegramRateLimiter:
    """
    Асинхронный rate limiter для Telegram API
    Обрабатывает глобальные лимиты Telegram
    """

    def __init__(self, config: TelegramRateLimitConfig = None):
        self.config = config or TelegramRateLimitConfig()
        self.logger = StructuredLogger("telegram_rate_limiter")

        # Глобальные счетчики
        self._global_tokens = self.config.messages_per_second
        self._last_global_refill = time.time()
        self._global_lock = asyncio.Lock()

        # Бурст-защита
        self._burst_messages: Dict[int, list] = {}  # Временные метки сообщений по чатам
        self._burst_lock = asyncio.Lock()

    async def _refill_global_tokens(self):
        """Пополнение глобальных токенов"""
        now = time.time()
        elapsed = now - self._last_global_refill

        if elapsed >= 1.0:
            self._global_tokens = self.config.messages_per_second
            self._last_global_refill = now
        else:
            # Добавляем пропорционально прошедшему времени
            new_tokens = elapsed * self.config.messages_per_second
            self._global_tokens = min(
                self.config.messages_per_second,
                self._global_tokens + new_tokens
            )
            self._last_global_refill = now

    async def _check_burst_limit(self, chat_id: int) -> bool:
        """Проверка бурст-лимита для предотвращения спама"""
        async with self._burst_lock:
            now = time.time()

            if chat_id not in self._burst_messages:
                self._burst_messages[chat_id] = []

            # Удаляем старые записи (старше 10 секунд)
            self._burst_messages[chat_id] = [
                ts for ts in self._burst_messages[chat_id]
                if now - ts < 10.0
            ]

            # Проверяем лимит
            if len(self._burst_messages[chat_id]) >= self.config.burst_limit:
                return False

            # Добавляем текущее сообщение
            self._burst_messages[chat_id].append(now)
            return True

    @asynccontextmanager
    async def acquire_for_chat(self, chat_id: int, operation: str = "send_message"):
        """
        Асинхронный контекстный менеджер для получения разрешения на отправку

        Args:
            chat_id: ID чата
            operation: Тип операции (для логирования)

        Yields:
            bool: True если можно отправлять, False если нужно ждать
        """
        wait_time = 0

        try:
            # 1. Проверяем бурст-лимит
            if not await self._check_burst_limit(chat_id):
                wait_time = 1.0
                await asyncio.sleep(wait_time)
                # После ожидания снова проверяем
                if not await self._check_burst_limit(chat_id):
                    self.logger.warning(f"Burst limit exceeded for chat {chat_id}")
                    yield False
                    return

            # 2. Проверяем глобальный лимит
            async with self._global_lock:
                await self._refill_global_tokens()

                if self._global_tokens < 1:
                    # Ждем до пополнения токенов
                    wait_until = self._last_global_refill + 1.0
                    wait_time = max(0, wait_until - time.time())
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                        await self._refill_global_tokens()

                if self._global_tokens >= 1:
                    self._global_tokens -= 1
                    global_acquired = True
                else:
                    global_acquired = False

            if not global_acquired:
                self.logger.warning("Global Telegram rate limit exceeded")
                yield False
                return

            # Все проверки пройдены
            if wait_time > 0:
                self.logger.info(f"Telegram rate limit wait: {wait_time:.2f}s for {operation} to chat {chat_id}")

            yield True

        except Exception as e:
            self.logger.error(f"Telegram rate limiter error: {e}")
            yield False

    async def get_status(self, chat_id: int) -> Dict:
        """Получить статус лимитов для отладки"""
        async with self._global_lock:
            global_tokens = self._global_tokens
            time_to_global_refill = max(0, 1.0 - (time.time() - self._last_global_refill))

        async with self._burst_lock:
            burst_count = len(self._burst_messages.get(chat_id, []))

        return {
            "global_tokens": global_tokens,
            "time_to_global_refill": time_to_global_refill,
            "burst_messages": burst_count,
            "burst_limit": self.config.burst_limit
        }

    async def cleanup_old_chats(self, older_than_hours: int = 24):
        """Очистка старых записей о чатах"""
        async with self._burst_lock:
            now = time.time()
            cutoff = now - (older_than_hours * 3600)

            chats_to_remove = [
                chat_id for chat_id, timestamps in self._burst_messages.items()
                if not timestamps or max(timestamps) < cutoff
            ]

            for chat_id in chats_to_remove:
                del self._burst_messages[chat_id]

        if chats_to_remove:
            self.logger.info(f"Cleaned up {len(chats_to_remove)} old chat records")