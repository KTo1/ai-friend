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
    # Включая восклицательный знак (!)
    MD_V2_SPECIAL_CHARS = r'_*[]()~`>#+-=|{}.!'

    # Шаблоны для поиска разметки MarkdownV2
    BOLD_PATTERN = r'\*(?!\s)(.+?)(?<!\s)\*'
    ITALIC_PATTERN = r'_(?!\s)(.+?)(?<!\s)_'
    CODE_PATTERN = r'`(?!\s)(.+?)(?<!\s)`'

    @staticmethod
    def format_text(text: str, parse_mode: Optional[str] = None) -> str:
        """
        Форматирует текст в соответствии с указанным parse_mode.
        Умное экранирование: сохраняет разметку, экранирует содержимое внутри нее.
        """
        if not text:
            return text

        if parse_mode == ParseMode.MARKDOWN_V2:
            return MarkdownFormatter._format_markdown_v2_smart(text)
        elif parse_mode == ParseMode.HTML:
            return MarkdownFormatter._escape_html(text)
        else:
            return text

    @staticmethod
    def _format_markdown_v2_smart(text: str) -> str:
        """
        Умное форматирование MarkdownV2:
        1. Находит все элементы разметки
        2. Экранирует содержимое внутри разметки
        3. Собирает обратно
        """
        # Находим все элементы разметки с их позициями
        elements = []

        # Ищем жирный текст
        for match in re.finditer(MarkdownFormatter.BOLD_PATTERN, text, re.DOTALL):
            start, end = match.span()
            content = match.group(1)
            # Экранируем содержимое
            escaped_content = MarkdownFormatter._escape_all_special_chars(content)
            elements.append(('bold', start, end, escaped_content))

        # Ищем курсив
        for match in re.finditer(MarkdownFormatter.ITALIC_PATTERN, text, re.DOTALL):
            start, end = match.span()
            content = match.group(1)
            escaped_content = MarkdownFormatter._escape_all_special_chars(content)
            elements.append(('italic', start, end, escaped_content))

        # Ищем код
        for match in re.finditer(MarkdownFormatter.CODE_PATTERN, text, re.DOTALL):
            start, end = match.span()
            content = match.group(1)
            escaped_content = MarkdownFormatter._escape_all_special_chars(content)
            elements.append(('code', start, end, escaped_content))

        # Если нет разметки, просто экранируем весь текст
        if not elements:
            return MarkdownFormatter._escape_all_special_chars(text)

        # Сортируем элементы по позиции
        elements.sort(key=lambda x: x[1])

        # Собираем результат
        result = []
        last_pos = 0

        for elem_type, start, end, content in elements:
            # Добавляем текст перед элементом (экранированный)
            if start > last_pos:
                plain_text = text[last_pos:start]
                escaped_plain = MarkdownFormatter._escape_all_special_chars(plain_text)
                result.append(escaped_plain)

            # Добавляем элемент с экранированным содержимым
            if elem_type == 'bold':
                result.append(f'*{content}*')
            elif elem_type == 'italic':
                result.append(f'_{content}_')
            elif elem_type == 'code':
                result.append(f'`{content}`')

            last_pos = end

        # Добавляем оставшийся текст после последнего элемента
        if last_pos < len(text):
            plain_text = text[last_pos:]
            escaped_plain = MarkdownFormatter._escape_all_special_chars(plain_text)
            result.append(escaped_plain)

        return ''.join(result)

    @staticmethod
    def _escape_all_special_chars(text: str) -> str:
        """Экранирует все специальные символы MarkdownV2."""
        for char in MarkdownFormatter.MD_V2_SPECIAL_CHARS:
            # Экранируем каждый специальный символ
            text = text.replace(char, f'\\{char}')
        return text

    @staticmethod
    def _escape_html(text: str) -> str:
        """Экранирует HTML-сущности."""
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&#39;')
        return text

    @staticmethod
    def format_bold(text: str) -> str:
        """Форматирует текст как жирный для MarkdownV2."""
        escaped = MarkdownFormatter._escape_all_special_chars(text)
        return f'*{escaped}*'

    @staticmethod
    def format_italic(text: str) -> str:
        """Форматирует текст как курсив для MarkdownV2."""
        escaped = MarkdownFormatter._escape_all_special_chars(text)
        return f'_{escaped}_'

    @staticmethod
    def format_code(text: str) -> str:
        """Форматирует текст как инлайн-код для MarkdownV2."""
        escaped = MarkdownFormatter._escape_all_special_chars(text)
        return f'`{escaped}`'

    @staticmethod
    def format_pre(code: str, language: str = '') -> str:
        """Форматирует текст как блок кода для MarkdownV2."""
        escaped = MarkdownFormatter._escape_all_special_chars(code)
        return f'```{language}\n{escaped}\n```'

    @staticmethod
    def format_link(text: str, url: str) -> str:
        """Форматирует ссылку для MarkdownV2."""
        escaped_text = MarkdownFormatter._escape_all_special_chars(text)
        escaped_url = MarkdownFormatter._escape_all_special_chars(url)
        return f'[{escaped_text}]({escaped_url})'

    @staticmethod
    def test_formatting() -> List[Tuple[str, str]]:
        """Тестовая функция для проверки форматирования."""
        test_cases = [
            ("*Добро пожаловать!*", "Должен сохранить жирный текст"),
            ("_Курсивный текст!_", "Должен сохранить курсив"),
            ("`код с ! внутри`", "Должен сохранить код"),
            ("Простой текст с !", "Должен экранировать !"),
            ("Текст со *жирным* и _курсивом_", "Должен сохранить оба типа разметки"),
        ]

        results = []
        for text, description in test_cases:
            formatted = MarkdownFormatter.format_text(text, ParseMode.MARKDOWN_V2)
            results.append((text, formatted, description))

        return results