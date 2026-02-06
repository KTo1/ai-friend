#!/usr/bin/env python3
"""
Скрипт для анализа взаимодействий пользователей с персонажами.
Извлекает диалоги из базы данных и формирует промпты для улучшения персонажей.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import asyncio

# Добавляем путь к проекту для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import config
    from infrastructure.database.database import Database
    from domain.entity.character import Character
    from infrastructure.database.repositories.character_repository import CharacterRepository
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что вы запускаете скрипт из корневой директории проекта")
    sys.exit(1)


@dataclass
class ConversationAnalysis:
    """Анализ диалога пользователя с персонажем"""
    user_id: int
    character_id: int
    character_name: str
    total_messages: int
    user_messages: List[Dict[str, Any]]
    bot_messages: List[Dict[str, Any]]
    first_message_time: datetime
    last_message_time: datetime
    user_info: Optional[Dict[str, Any]] = None


class ConversationAnalyzer:
    """Анализатор диалогов для улучшения промптов персонажей"""

    def __init__(self, database: Database):
        self.db = database
        self.character_repo = CharacterRepository(database)
        self.output_dir = Path("character_analyses")
        self.output_dir.mkdir(exist_ok=True)

    def get_all_characters(self) -> List[Character]:
        """Получить всех персонажей"""
        return self.character_repo.get_all_characters(active_only=False)

    def get_character_conversations(self, character_id: int,
                                    days_back: int = 30,
                                    min_messages: int = 5) -> List[Dict[str, Any]]:
        """
        Получить все диалоги для персонажа

        Args:
            character_id: ID персонажа
            days_back: сколько дней назад анализировать
            min_messages: минимальное количество сообщений для анализа
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        query = """
                SELECT cc.user_id, \
                       u.username, \
                       u.first_name, \
                       u.last_name, \
                       COUNT(*)                                               as total_messages, \
                       SUM(CASE WHEN cc.role = 'user' THEN 1 ELSE 0 END)      as user_message_count, \
                       SUM(CASE WHEN cc.role = 'assistant' THEN 1 ELSE 0 END) as bot_message_count, \
                       MIN(cc.timestamp)                                      as first_message_time, \
                       MAX(cc.timestamp)                                      as last_message_time
                FROM conversation_context cc
                         LEFT JOIN users u ON cc.user_id = u.user_id
                WHERE cc.character_id = %s
                  AND cc.deleted_at IS NULL
                  AND cc.timestamp >= %s
                GROUP BY cc.user_id, u.username, u.first_name, u.last_name
                HAVING COUNT(*) >= %s
                ORDER BY total_messages DESC \
                """

        results = self.db.fetch_all(query, (character_id, cutoff_date, min_messages))
        return results if results else []

    def get_conversation_messages(self, user_id: int, character_id: int,
                                  limit: int = 100) -> List[Dict[str, Any]]:
        """Получить конкретные сообщения из диалога"""
        query = """
                SELECT role, \
                       content, timestamp
                FROM conversation_context
                WHERE user_id = %s
                  AND character_id = %s
                  AND deleted_at IS NULL
                ORDER BY timestamp ASC
                    LIMIT %s \
                """

        results = self.db.fetch_all(query, (user_id, character_id, limit))
        return results if results else []

    def analyze_conversation(self, user_id: int, character_id: int,
                             character_name: str, limit: int = 50) -> Optional[ConversationAnalysis]:
        """Проанализировать конкретный диалог"""
        messages = self.get_conversation_messages(user_id, character_id, limit)

        if not messages:
            return None

        user_messages = [m for m in messages if m['role'] == 'user']
        bot_messages = [m for m in messages if m['role'] == 'assistant']

        if not user_messages or not bot_messages:
            return None

        timestamps = [m['timestamp'] for m in messages]

        # Получаем информацию о пользователе
        user_info_query = """
                          SELECT username, first_name, last_name, created_at, last_seen
                          FROM users
                          WHERE user_id = %s \
                          """
        user_info = self.db.fetch_one(user_info_query, (user_id,))

        return ConversationAnalysis(
            user_id=user_id,
            character_id=character_id,
            character_name=character_name,
            total_messages=len(messages),
            user_messages=user_messages,
            bot_messages=bot_messages,
            first_message_time=min(timestamps),
            last_message_time=max(timestamps),
            user_info=user_info
        )

    def create_analysis_prompt(self, analysis: ConversationAnalysis,
                               character: Character) -> str:
        """Создать промпт для анализа на основе диалога"""

        prompt = f"""# Анализ диалога для улучшения персонажа "{character.name}"

## Информация о персонаже:
- ID: {character.id}
- Текущий промпт: {character.system_prompt[:200]}...
- Описание: {character.description[:200]}...

## Информация о пользователе:
- ID: {analysis.user_id}
- Имя: {analysis.user_info.get('first_name', 'Не указано') if analysis.user_info else 'Неизвестно'}
- Username: @{analysis.user_info.get('username', 'нет') if analysis.user_info else 'нет'}
- Активность: {analysis.first_message_time.strftime('%Y-%m-%d')} - {analysis.last_message_time.strftime('%Y-%m-%d')}
- Всего сообщений: {analysis.total_messages} (пользователь: {len(analysis.user_messages)}, бот: {len(analysis.bot_messages)})

## Диалог (последние {len(analysis.user_messages)} сообщений пользователя):
"""

        # Добавляем диалог
        for i, (user_msg, bot_msg) in enumerate(zip(analysis.user_messages, analysis.bot_messages)):
            if i >= 10:  # Ограничиваем длину
                prompt += f"\n... и еще {len(analysis.user_messages) - 10} сообщений"
                break

            prompt += f"\n### Сообщение {i + 1}:"
            prompt += f"\n**Пользователь:** {user_msg['content'][:300]}"
            prompt += f"\n**Ответ бота:** {bot_msg['content'][:300]}"
            prompt += f"\n---"

        # Добавляем задачи для анализа
        prompt += f"""

## Задачи для анализа:

1. **Тон и стиль общения:**
   - Соответствует ли стиль ответов бота характеру персонажа "{character.name}"?
   - Поддерживается ли единый тон на протяжении всего диалога?
   - Как пользователь реагирует на стиль общения бота?

2. **Контекст и память:**
   - Сохраняется ли контекст разговора между сообщениями?
   - Используются ли ранее упомянутые факты о пользователе?
   - Есть ли повторения или противоречия в ответах?

3. **Эмоциональная составляющая:**
   - Насколько ответы бота эмоционально окрашены?
   - Соответствует ли уровень эмпатии ожиданиям от персонажа?
   - Как бот реагирует на эмоциональные сообщения пользователя?

4. **Содержательность ответов:**
   - Даются ли развернутые, содержательные ответы?
   - Есть ли шаблонные или общие фразы?
   - Насколько ответы соответствуют запросам пользователя?

5. **Предложения по улучшению:**
   - Какие аспекты промпта нужно усилить?
   - Какие слабые места в ответах бота?
   - Конкретные примеры улучшений из этого диалога.

## Рекомендации по улучшению промпта:
(Предложите конкретные изменения в system_prompt персонажа на основе этого диалога)
"""

        return prompt

    def create_summary_prompt(self, character: Character,
                              conversations: List[ConversationAnalysis]) -> str:
        """Создать суммарный промпт для анализа всех диалогов персонажа"""

        if not conversations:
            return f"Нет данных для анализа персонажа '{character.name}'"

        total_users = len(set(c.user_id for c in conversations))
        total_messages = sum(c.total_messages for c in conversations)
        avg_messages = total_messages / len(conversations) if conversations else 0

        # Анализ тем разговоров (простейший)
        common_topics = self._extract_common_topics(conversations)

        prompt = f"""# Сводный анализ взаимодействий с персонажем "{character.name}"

## Общая статистика:
- ID персонажа: {character.id}
- Проанализировано диалогов: {len(conversations)}
- Уникальных пользователей: {total_users}
- Всего сообщений: {total_messages}
- Средняя длина диалога: {avg_messages:.1f} сообщений
- Период анализа: {min(c.first_message_time for c in conversations).strftime('%Y-%m-%d')} - {max(c.last_message_time for c in conversations).strftime('%Y-%m-%d')}

## Текущий промпт персонажа:
        
{character.system_prompt}

## Основные темы разговоров:
{common_topics}

## Анализ успешных взаимодействий:

### 1. Что работает хорошо:
(На основе анализа наиболее длительных диалогов)

### 2. Проблемные области:
(На основе коротких или прерванных диалогов)

### 3. Ожидания пользователей:
(На основе анализа запросов пользователей)

### 4. Консистентность характера:
(Насколько стабилен характер персонажа в разных диалогах)

## Конкретные примеры для анализа:
(Приложены в отдельных файлах для каждого пользователя)

## Рекомендации по улучшению:

### 1. Изменения в промпте:
(Конкретные предложения по изменению system_prompt)

### 2. Добавление новых черт характера:
(На основе анализа пользовательских предпочтений)

### 3. Улучшение контекстной памяти:
(Предложения по лучшему использованию истории диалога)

### 4. Оптимизация тона и стиля:
(Настройка эмоциональной составляющей)
"""

        return prompt

    def _extract_common_topics(self, conversations: List[ConversationAnalysis]) -> str:
        """Извлечь общие темы из диалогов"""
        topics = []

        # Простейший анализ ключевых слов
        common_words = [
            "привет", "как дела", "как жизнь", "чем занимаешься",
            "расскажи", "совет", "помоги", "мне грустно", "мне весело",
            "люблю", "нравится", "хочу", "мечта", "планы"
        ]

        topic_counts = {word: 0 for word in common_words}

        for conv in conversations:
            for user_msg in conv.user_messages:
                content_lower = user_msg['content'].lower()
                for word in common_words:
                    if word in content_lower:
                        topic_counts[word] += 1

        # Форматируем результат
        result = []
        for word, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                result.append(f"- {word}: {count} упоминаний")

        return "\n".join(result) if result else "Не удалось определить общие темы"

    def save_analysis(self, character_name: str, user_id: int,
                     prompt: str, summary: bool = False):
        """Сохранить анализ в файл"""

        # Очищаем имя персонажа для использования в пути
        safe_name = "".join(c for c in character_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')

        # Создаем директорию для персонажа
        char_dir = self.output_dir / safe_name
        char_dir.mkdir(exist_ok=True)

        # Создаем поддиректорию для исходных данных
        raw_dir = char_dir / "raw_conversations"
        raw_dir.mkdir(exist_ok=True)

        # Определяем имя файла
        if summary:
            filename = f"summary_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = char_dir / filename
        else:
            filename = f"user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = raw_dir / filename

        # Сохраняем файл
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(prompt)

        return filepath

    def analyze_all_characters(self, days_back: int = 30,
                              min_conversations: int = 3,
                              min_messages: int = 5):
        """Проанализировать всех персонажей"""

        print("🔍 Начинаю анализ взаимодействий...")
        characters = self.get_all_characters()
        print(f"Найдено персонажей: {len(characters)}")

        results = {}

        for character in characters:
            print(f"\n📊 Анализирую персонажа: {character.name} (ID: {character.id})")

            # Получаем диалоги для персонажа
            conversations_data = self.get_character_conversations(
                character.id, days_back, min_messages
            )

            if not conversations_data:
                print(f"  Нет диалогов для анализа (минимум {min_messages} сообщений)")
                continue

            print(f"  Найдено диалогов для анализа: {len(conversations_data)}")

            # Анализируем каждый диалог
            detailed_analyses = []
            for i, conv_data in enumerate(conversations_data[:10]):  # Ограничиваем для производительности
                print(f"  Анализ диалога {i+1}/{min(10, len(conversations_data))}...")

                analysis = self.analyze_conversation(
                    conv_data['user_id'],
                    character.id,
                    character.name,
                    limit=50
                )

                if analysis:
                    detailed_analyses.append(analysis)

                    # Создаем и сохраняем промпт для отдельного диалога
                    prompt = self.create_analysis_prompt(analysis, character)
                    filepath = self.save_analysis(
                        character.name,
                        conv_data['user_id'],
                        prompt,
                        summary=False
                    )
                    print(f"    → Сохранен: {filepath.name}")

            # Создаем и сохраняем суммарный анализ
            if detailed_analyses:
                summary_prompt = self.create_summary_prompt(character, detailed_analyses)
                summary_path = self.save_analysis(
                    character.name,
                    0,  # 0 для сводного файла
                    summary_prompt,
                    summary=True
                )
                print(f"  📄 Сводный анализ сохранен: {summary_path.name}")

                results[character.name] = {
                    'total_conversations': len(conversations_data),
                    'analyzed_conversations': len(detailed_analyses),
                    'summary_file': str(summary_path)
                }

        # Сохраняем общий отчет
        self.save_report(results)

        return results

    def save_report(self, results: Dict[str, Any]):
        """Сохранить общий отчет"""
        report_path = self.output_dir / f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report = {
            'generated_at': datetime.now().isoformat(),
            'total_characters_analyzed': len(results),
            'results': results,
            'output_directory': str(self.output_dir.absolute())
        }

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n📋 Общий отчет сохранен: {report_path}")

        # Также создаем текстовый отчет
        txt_report = self.create_text_report(results)
        txt_path = self.output_dir / f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(txt_report)

        return report_path

    def create_text_report(self, results: Dict[str, Any]) -> str:
        """Создать текстовый отчет"""
        report = f"""# Отчет анализа взаимодействий с персонажами

Дата генерации: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Всего проанализировано персонажей: {len(results)}

{'='*60}

"""

        for char_name, data in results.items():
            report += f"## Персонаж: {char_name}\n"
            report += f"- Всего диалогов: {data['total_conversations']}\n"
            report += f"- Проанализировано: {data['analyzed_conversations']}\n"
            report += f"- Сводный файл: {data['summary_file']}\n"
            report += f"- Папка с диалогами: character_analyses/{''.join(c for c in char_name if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(' ', '_')}/\n"
            report += "\n"

        report += f"""
{'='*60}

## Структура папок:
character_analyses/
├── Имя_Персонажа_1/
│   ├── summary_analysis_YYYYMMDD_HHMMSS.txt
│   └── raw_conversations/
│       ├── user_123456789_YYYYMMDD_HHMMSS.txt
│       └── ...
├── Имя_Персонажа_2/
│   └── ...
└── analysis_report_YYYYMMDD_HHMMSS.json

## Использование данных:
1. Сводные файлы (summary_analysis_*.txt) содержат общий анализ по персонажу
2. Файлы в raw_conversations/ содержат детальные диалоги с пользователями
3. Файлы можно передавать LLM для анализа и предложений по улучшению промптов
"""

        return report


def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(
        description='Анализ диалогов пользователей с персонажами для улучшения промптов'
    )
    parser.add_argument('--days', type=int, default=30,
                       help='За сколько дней анализировать диалоги (по умолчанию: 30)')
    parser.add_argument('--min-conversations', type=int, default=3,
                       help='Минимальное количество диалогов для анализа персонажа (по умолчанию: 3)')
    parser.add_argument('--min-messages', type=int, default=5,
                       help='Минимальное количество сообщений в диалоге (по умолчанию: 5)')
    parser.add_argument('--output-dir', type=str, default='character_analyses',
                       help='Директория для сохранения результатов (по умолчанию: character_analyses)')

    args = parser.parse_args()

    print("🚀 Запуск анализатора диалогов...")
    print(f"📅 Анализируем диалоги за последние {args.days} дней")
    print(f"📊 Минимум диалогов для анализа: {args.min_conversations}")
    print(f"💬 Минимум сообщений в диалоге: {args.min_messages}")

    try:
        # Инициализируем базу данных
        database = Database()

        # Создаем анализатор
        analyzer = ConversationAnalyzer(database)
        analyzer.output_dir = Path(args.output_dir)

        # Запускаем анализ
        results = analyzer.analyze_all_characters(
            days_back=args.days,
            min_conversations=args.min_conversations,
            min_messages=args.min_messages
        )

        print("\n✅ Анализ завершен!")
        print(f"\n📁 Результаты сохранены в: {analyzer.output_dir.absolute()}")

        if results:
            print("\n📈 Статистика:")
            for char_name, data in results.items():
                print(f"  {char_name}: {data['analyzed_conversations']} диалогов проанализировано")

        print("\n🎯 Используйте сгенерированные файлы для:")
        print("  1. Анализа успешных взаимодействий")
        print("  2. Улучшения промптов персонажей")
        print("  3. Понимания ожиданий пользователей")
        print("  4. Обучения новых версий персонажей")

    except Exception as e:
        print(f"❌ Ошибка при анализе: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()