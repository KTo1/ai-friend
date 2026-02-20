import asyncio
from typing import Optional, Dict, Any
from telegram import Update, Bot
from telegram.error import TelegramError, RetryAfter, TimedOut, Forbidden
from infrastructure.monitoring.logging import StructuredLogger
from infrastructure.monitoring.metrics import metrics_collector
from .telegram_rate_limiter import TelegramRateLimiter
from domain.exception.telegram import TelegramExceptions

class TelegramMessageSender:
    """
    Обертка для безопасной отправки сообщений через Telegram API
    с учетом лимитов и автоматическими повторами
    """

    def __init__(self, rate_limiter: TelegramRateLimiter):
        self.rate_limiter = rate_limiter
        self.logger = StructuredLogger("telegram_sender")
        self._max_retries = 3
        self._base_delay = 1.0

    async def send_typing_status(self, bot: Bot, chat_id: int):
        try:
            # Получаем разрешение от rate limiter
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception as e:
            # Неожиданные ошибки
            self.logger.error(f"Unexpected error sending status to chat {chat_id}: {e}")
            metrics_collector.record_telegram_send("unexpected_error")

            return False

    async def send_invoice(self, bot: Bot, chat_id: int):
        try:
            # Получаем разрешение от rate limiter
            await bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception as e:
            # Неожиданные ошибки
            self.logger.error(f"Unexpected error sending status to chat {chat_id}: {e}")
            metrics_collector.record_telegram_send("unexpected_error")

            return False

    async def send_message(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        **kwargs
    ) -> tuple[bool, TelegramExceptions | None]:
        """
        Безопасная отправка сообщения с учетом лимитов Telegram

        Returns:
            bool: Успешно ли отправлено сообщение
        """
        for attempt in range(self._max_retries):
            try:
                # Получаем разрешение от rate limiter
                async with self.rate_limiter.acquire_for_chat(chat_id, "send_message") as allowed:
                    if not allowed:
                        if attempt == self._max_retries - 1:
                            self.logger.error(f"Failed to send message to {chat_id}: rate limit exceeded")
                            metrics_collector.record_telegram_send("rate_limit_exceeded")
                            return False, None
                        continue

                # Отправляем сообщение
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id,
                    **kwargs
                )

                metrics_collector.record_telegram_send("success")
                self.logger.debug(f"Message sent to chat {chat_id}", extra={
                    'chat_id': chat_id,
                    'text_length': len(text),
                    'attempt': attempt + 1
                })
                return True, None

            except RetryAfter as e:
                # Telegram просит подождать
                wait_time = e.retry_after
                self.logger.warning(f"Telegram RetryAfter: waiting {wait_time}s for chat {chat_id}")
                metrics_collector.record_telegram_send("retry_after")

                if attempt < self._max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Failed to send message after {self._max_retries} retries")
                    return False, TelegramExceptions.RetryAfter

            except TimedOut as e:
                # Таймаут - пробуем снова
                self.logger.warning(f"Telegram timeout for chat {chat_id}, attempt {attempt + 1}")
                metrics_collector.record_telegram_send("timeout")

                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Failed to send message due to timeout after {self._max_retries} attempts")
                    return False, TelegramExceptions.TimedOut

            except Forbidden as e:
                self.logger.warning(f"User was blocked bot for chat {chat_id}, attempt {attempt + 1}")
                metrics_collector.record_telegram_send("forbidden")

                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"Failed to send message due to timeout after {self._max_retries} attempts")
                    return False, TelegramExceptions.Forbidden

            except TelegramError as e:
                # Другие ошибки Telegram
                self.logger.error(f"Telegram error for chat {chat_id}: {e}")
                metrics_collector.record_telegram_send(f"error_{e.__class__.__name__}")

                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    return False, TelegramExceptions.TelegramError

            except Exception as e:
                # Неожиданные ошибки
                self.logger.error(f"Unexpected error sending to chat {chat_id}: {e}")
                metrics_collector.record_telegram_send("unexpected_error")

                if attempt < self._max_retries - 1:
                    delay = self._base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    return False, TelegramExceptions.Other

        return False, None

    async def reply_to_message(
        self,
        bot: Bot,
        update: Update,
        text: str,
        parse_mode: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Безопасный ответ на сообщение"""
        if not update.message:
            self.logger.warning("No message to reply to")
            return False

        result, error = await self.send_message(
            bot=bot,
            chat_id=update.message.chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_to_message_id=update.message.message_id,
            **kwargs
        )
        return result


# Синглтон для глобального использования
_global_rate_limiter = TelegramRateLimiter()
_global_message_sender = TelegramMessageSender(_global_rate_limiter)


def get_telegram_sender() -> TelegramMessageSender:
    """Получить глобальный экземпляр отправителя сообщений"""
    return _global_message_sender


def get_telegram_rate_limiter() -> TelegramRateLimiter:
    """Получить глобальный экземпляр rate limiter"""
    return _global_rate_limiter