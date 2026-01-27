"""
Утилиты для форматирования MarkdownV2 в Telegram.
Версия 2 Markdown требует экранирования специальных символов.
"""
from typing import Optional, List, Tuple
from telegram.helpers import escape_markdown
from telegram.constants import ParseMode
import re

class MarkdownFormatter:
    """Форматирование текста для MarkdownV2 в Telegram."""

    # Специальные символы, которые нужно экранировать в MarkdownV2
    MD_V2_SPECIAL_CHARS = r'_*[]()~`>#+-=|{}.!'

    @staticmethod
    def format_text(text: str, parse_mode: Optional[str] = None) -> str:
        """
        Форматирует текст в соответствии с указанным parse_mode.

        ВАЖНО: Для MarkdownV2 не экранируем звездочки внутри разметки.
        """
        if not text:
            return text

        if parse_mode == ParseMode.MARKDOWN_V2:
            # Разбиваем текст на части: разметка и обычный текст
            return MarkdownFormatter._format_markdown_v2_smart(text)
        elif parse_mode == ParseMode.HTML:
            # Экранируем HTML-сущности
            return MarkdownFormatter._escape_html(text)
        else:
            # Без форматирования
            return text

    @staticmethod
    def _format_markdown_v2_smart(text: str) -> str:
        """
        Умное форматирование MarkdownV2:
        - Сохраняет существующую разметку (*жирный*, _курсив_ и т.д.)
        - Экранирует только неразмеченный текст
        """
        # Регулярное выражение для поиска разметки MarkdownV2
        # Ищем *жирный*, _курсив_, `код`, ```блок кода```
        patterns = [
            (r'\*\*(.*?)\*\*', r'*\1*'),  # **жирный** -> *жирный* (поддержка старого синтаксиса)
            (r'__(.*?)__', r'_\1_'),      # __курсив__ -> _курсив_ (поддержка старого синтаксиса)
        ]

        # Сначала конвертируем старый синтаксис в новый
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text, flags=re.DOTALL)

        # Теперь обрабатываем разметку MarkdownV2
        # Разбиваем текст на части: разметка и обычный текст
        parts = []
        i = 0
        n = len(text)

        while i < n:
            # Ищем начало разметки
            if text[i] == '*' and i + 1 < n and text[i+1] != ' ':
                # Нашли жирный текст
                j = i + 1
                while j < n and text[j] != '*':
                    j += 1
                if j < n:  # Нашли закрывающую звездочку
                    # Это разметка, не экранируем
                    parts.append(text[i:j+1])
                    i = j + 1
                    continue
            elif text[i] == '_' and i + 1 < n and text[i+1] != ' ':
                # Нашли курсив
                j = i + 1
                while j < n and text[j] != '_':
                    j += 1
                if j < n:  # Нашли закрывающее подчеркивание
                    # Это разметка, не экранируем
                    parts.append(text[i:j+1])
                    i = j + 1
                    continue
            elif text[i] == '`':
                # Нашли код
                j = i + 1
                while j < n and text[j] != '`':
                    j += 1
                if j < n:  # Нашли закрывающий обратный апостроф
                    # Это разметка, не экранируем
                    parts.append(text[i:j+1])
                    i = j + 1
                    continue

            # Это обычный текст, экранируем
            start = i
            while i < n and text[i] not in '*_`':
                i += 1
            if start < i:
                plain_text = text[start:i]
                escaped_text = MarkdownFormatter._escape_markdown_v2_plain(plain_text)
                parts.append(escaped_text)

        return ''.join(parts)

    @staticmethod
    def _escape_markdown_v2_plain(text: str) -> str:
        """Экранирует только обычный текст (без разметки)."""
        # Экранируем специальные символы, но не трогаем те, что внутри разметки
        for char in MarkdownFormatter.MD_V2_SPECIAL_CHARS:
            # Не экранируем символы, которые могут быть частью разметки
            if char in '*_`':
                continue
            text = text.replace(char, f'\\{char}')
        return text

    @staticmethod
    def _escape_html(text: str) -> str:
        """Экранирует HTML-сущности."""
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        return text

    @staticmethod
    def format_bold(text: str) -> str:
        """Форматирует текст как жирный для MarkdownV2."""
        escaped = MarkdownFormatter._escape_markdown_v2_plain(text)
        return f'*{escaped}*'

    @staticmethod
    def format_italic(text: str) -> str:
        """Форматирует текст как курсив для MarkdownV2."""
        escaped = MarkdownFormatter._escape_markdown_v2_plain(text)
        return f'_{escaped}_'

    @staticmethod
    def format_code(text: str) -> str:
        """Форматирует текст как инлайн-код для MarkdownV2."""
        escaped = MarkdownFormatter._escape_markdown_v2_plain(text)
        return f'`{escaped}`'

    @staticmethod
    def format_pre(code: str, language: str = '') -> str:
        """Форматирует текст как блок кода для MarkdownV2."""
        escaped = MarkdownFormatter._escape_markdown_v2_plain(code)
        return f'```{language}\n{escaped}\n```'

    @staticmethod
    def format_link(text: str, url: str) -> str:
        """Форматирует ссылку для MarkdownV2."""
        escaped_text = MarkdownFormatter._escape_markdown_v2_plain(text)
        escaped_url = MarkdownFormatter._escape_markdown_v2_plain(url)
        return f'[{escaped_text}]({escaped_url})'