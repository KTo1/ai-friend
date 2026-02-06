#!/usr/bin/env python3
"""
📊 Скрипт для экспорта ВСЕХ диалогов из базы данных для анализа и улучшения промптов персонажей.
Экспортирует ВСЕ диалоги без ограничений для полного анализа.

Использование:
    python analyze_conversations.py --output-dir ./conversation_analysis
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import argparse
from dataclasses import dataclass, asdict
import psycopg2
from psycopg2.extras import RealDictCursor


# ============================================================================
# 📄 analyze_conversations.py
# ============================================================================

@dataclass
class DatabaseConfig:
    """Конфигурация подключения к базе данных"""
    host: str = "localhost"
    port: int = 5433
    database: str = "ai-friend"
    user: str = "not_postgres"
    password: str = "_koa3f7uN-JLH3x@1vR$"

    def get_connection_string(self) -> str:
        """Получить строку подключения PostgreSQL"""
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"


@dataclass
class ConversationMessage:
    """Сообщение из диалога"""
    role: str  # 'user' или 'assistant'
    content: str
    timestamp: datetime
    message_id: int


@dataclass
class CharacterInfo:
    """Информация о персонаже"""
    id: int
    name: str
    description: str
    system_prompt: str
    avatar_mime_type: str
    is_active: bool


@dataclass
class UserDialogue:
    """Диалог конкретного пользователя с персонажем"""
    user_id: int
    character_id: int
    character_name: str
    messages: List[ConversationMessage]
    total_messages: int
    first_message_date: datetime
    last_message_date: datetime
    user_info: Optional[Dict] = None


class ConversationExporter:
    """Экспортер ВСЕХ диалогов из базы данных"""

    def __init__(self, db_config: DatabaseConfig):
        self.db_config = db_config
        self.connection = None
        self.cursor = None

    def connect(self):
        """Подключиться к базе данных"""
        try:
            self.connection = psycopg2.connect(
                self.db_config.get_connection_string(),
                cursor_factory=RealDictCursor
            )
            self.cursor = self.connection.cursor()
            print(f"✅ Подключение к БД установлено: {self.db_config.database}")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к БД: {e}")
            return False

    def disconnect(self):
        """Отключиться от базы данных"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        print("🔌 Отключение от БД")

    def get_all_characters(self) -> Dict[int, CharacterInfo]:
        """Получить ВСЕХ персонажей из базы"""
        query = """
                SELECT id, \
                       name, \
                       description, \
                       system_prompt,
                       avatar_mime_type, \
                       is_active
                FROM characters
                ORDER BY id \
                """

        self.cursor.execute(query)
        characters = {}

        for row in self.cursor.fetchall():
            character = CharacterInfo(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                system_prompt=row['system_prompt'],
                avatar_mime_type=row['avatar_mime_type'],
                is_active=row['is_active']
            )
            characters[character.id] = character

        print(f"📊 Загружено персонажей: {len(characters)}")
        return characters

    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получить информацию о пользователе"""
        query = """
                SELECT user_id, \
                       username, \
                       first_name, \
                       last_name,
                       created_at, \
                       last_seen, \
                       is_admin, \
                       is_blocked
                FROM users
                WHERE user_id = %s \
                """

        try:
            self.cursor.execute(query, (user_id,))
            row = self.cursor.fetchone()
            if row:
                return dict(row)
        except Exception as e:
            print(f"⚠️ Ошибка получения информации о пользователе {user_id}: {e}")

        return None

    def get_conversations_for_character(self, character_id: int) -> List[UserDialogue]:
        """Получить ВСЕ диалоги для конкретного персонажа БЕЗ ЛИМИТОВ"""
        query = """
                SELECT cc.id, \
                       cc.user_id, \
                       cc.character_id, \
                       cc.role,
                       cc.content, \
                       cc.timestamp, \
                       c.name as character_name
                FROM conversation_context cc
                         JOIN characters c ON cc.character_id = c.id
                WHERE cc.character_id = %s
                  AND cc.deleted_at IS NULL
                ORDER BY cc.user_id, cc.timestamp ASC \
                """

        self.cursor.execute(query, (character_id,))
        rows = self.cursor.fetchall()

        # Группируем по пользователям
        user_dialogues = {}

        for row in rows:
            user_id = row['user_id']

            if user_id not in user_dialogues:
                user_dialogues[user_id] = {
                    'user_id': user_id,
                    'character_id': character_id,
                    'character_name': row['character_name'],
                    'messages': [],
                    'first_message_date': None,
                    'last_message_date': None
                }

            message = ConversationMessage(
                role=row['role'],
                content=row['content'],
                timestamp=row['timestamp'],
                message_id=row['id']
            )

            user_dialogues[user_id]['messages'].append(message)

            # Обновляем даты
            if not user_dialogues[user_id]['first_message_date'] or message.timestamp < user_dialogues[user_id][
                'first_message_date']:
                user_dialogues[user_id]['first_message_date'] = message.timestamp

            if not user_dialogues[user_id]['last_message_date'] or message.timestamp > user_dialogues[user_id][
                'last_message_date']:
                user_dialogues[user_id]['last_message_date'] = message.timestamp

        # Преобразуем в объекты UserDialogue
        result = []
        for user_id, data in user_dialogues.items():
            dialogue = UserDialogue(
                user_id=user_id,
                character_id=data['character_id'],
                character_name=data['character_name'],
                messages=data['messages'],
                total_messages=len(data['messages']),
                first_message_date=data['first_message_date'],
                last_message_date=data['last_message_date'],
                user_info=self.get_user_info(user_id)
            )
            result.append(dialogue)

        return result

    def get_all_conversations(self) -> Dict[int, Dict]:
        """Получить ВСЕ диалоги для ВСЕХ персонажей БЕЗ ЛИМИТОВ"""
        characters = self.get_all_characters()
        all_conversations = {}

        for character_id, character in characters.items():
            print(f"📖 Загрузка ВСЕХ диалогов для персонажа: {character.name} (ID: {character_id})")
            conversations = self.get_conversations_for_character(character_id)
            all_conversations[character_id] = {
                'character': character,
                'dialogues': conversations,
                'total_dialogues': len(conversations),
                'total_messages': sum(len(d.messages) for d in conversations)
            }
            print(
                f"   → Загружено диалогов: {len(conversations)}, сообщений: {sum(len(d.messages) for d in conversations)}")

        return all_conversations

    def get_character_statistics(self) -> Dict[str, Any]:
        """Получить общую статистику по ВСЕМ диалогам"""
        query = """
                SELECT c.id                       as character_id, \
                       c.name                     as character_name, \
                       COUNT(DISTINCT cc.user_id) as unique_users, \
                       COUNT(cc.id)               as total_messages, \
                       MIN(cc.timestamp)          as first_message, \
                       MAX(cc.timestamp)          as last_message
                FROM conversation_context cc
                         JOIN characters c ON cc.character_id = c.id
                WHERE cc.deleted_at IS NULL
                GROUP BY c.id, c.name
                ORDER BY total_messages DESC \
                """

        self.cursor.execute(query)
        stats = {}
        total_messages = 0
        total_users = 0

        for row in self.cursor.fetchall():
            stats[row['character_id']] = {
                'name': row['character_name'],
                'unique_users': row['unique_users'],
                'total_messages': row['total_messages'],
                'first_message': row['first_message'],
                'last_message': row['last_message']
            }
            total_messages += row['total_messages']
            total_users += row['unique_users']

        return {
            'character_stats': stats,
            'total_messages': total_messages,
            'total_users': total_users,
            'export_date': datetime.now().isoformat()
        }


class DialogueAnalyzer:
    """Анализатор и экспортер ВСЕХ диалогов"""

    def __init__(self, output_dir: str = "./conversation_analysis"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_analysis_prompt(self, character: CharacterInfo, dialogues: List[UserDialogue]) -> str:
        """Создать промпт для анализа AI с ВСЕМИ диалогами"""

        # Статистика
        total_users = len(dialogues)
        total_messages = sum(len(d.messages) for d in dialogues)
        avg_messages_per_user = total_messages / total_users if total_users > 0 else 0

        # ВСЕ диалоги включаем в промпт
        all_dialogues_text = []

        for dialogue_index, dialogue in enumerate(dialogues, 1):
            dialogue_text = f"\n{'=' * 80}\n"
            dialogue_text += f"📝 ДИАЛОГ #{dialogue_index} | Пользователь ID: {dialogue.user_id}\n"
            dialogue_text += f"{'=' * 80}\n"

            if dialogue.user_info:
                username = dialogue.user_info.get('username', 'Не указан')
                first_name = dialogue.user_info.get('first_name', 'Не указано')
                last_name = dialogue.user_info.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()

                dialogue_text += f"👤 ПОЛЬЗОВАТЕЛЬ:\n"
                dialogue_text += f"  • ID: {dialogue.user_id}\n"
                if username != 'Не указан':
                    dialogue_text += f"  • Username: @{username}\n"
                if full_name:
                    dialogue_text += f"  • Имя: {full_name}\n"

                if dialogue.user_info.get('created_at'):
                    created = dialogue.user_info['created_at']
                    if isinstance(created, str):
                        created = created[:19]
                    dialogue_text += f"  • Зарегистрирован: {created}\n"

            dialogue_text += f"📊 СТАТИСТИКА ДИАЛОГА:\n"
            dialogue_text += f"  • Всего сообщений: {dialogue.total_messages}\n"
            dialogue_text += f"  • Первое сообщение: {dialogue.first_message_date}\n"
            dialogue_text += f"  • Последнее сообщение: {dialogue.last_message_date}\n"

            if dialogue.last_message_date and dialogue.first_message_date:
                duration = dialogue.last_message_date - dialogue.first_message_date
                dialogue_text += f"  • Длительность диалога: {duration.days} дней\n"

            dialogue_text += f"\n{'─' * 80}\n"
            dialogue_text += "💬 ПОЛНЫЙ ДИАЛОГ:\n"
            dialogue_text += f"{'─' * 80}\n\n"

            # Включаем ВСЕ сообщения
            for i, msg in enumerate(dialogue.messages, 1):
                timestamp_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if msg.role == 'user':
                    dialogue_text += f"[{timestamp_str}] 👤 ПОЛЬЗОВАТЕЛЬ:\n{msg.content}\n\n"
                else:
                    dialogue_text += f"[{timestamp_str}] 🤖 {character.name.upper()}:\n{msg.content}\n\n"
                    dialogue_text += f"{'─' * 40}\n\n"

            dialogue_text += f"✅ КОНЕЦ ДИАЛОГА #{dialogue_index}"
            all_dialogues_text.append(dialogue_text)

        # Формируем полный промпт
        prompt = f"""
# 🤖 ПОЛНЫЙ АНАЛИЗ ДИАЛОГОВ ПЕРСОНАЖА: {character.name}

## 📋 ТЕКУЩИЙ ПРОМПТ ПЕРСОНАЖА:
{character.system_prompt}

## 📝 ОПИСАНИЕ ПЕРСОНАЖА:
{character.description}

## 📊 ПОЛНАЯ СТАТИСТИКА:
- Всего пользователей, общавшихся с персонажем: {total_users}
- Всего сообщений в диалогах: {total_messages}
- Среднее количество сообщений на пользователя: {avg_messages_per_user:.1f}
- Экспорт выполнен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 🎯 ЗАДАНИЕ ДЛЯ AI-АНАЛИТИКА:
Перед вами ВСЕ диалоги пользователей с персонажем "{character.name}". 
Ваша задача — провести глубокий анализ и предложить конкретные улучшения промпта.

### Что анализировать:
1. 🗣️ **Стиль общения пользователей:**
   - Как начинают диалоги?
   - Какие темы поднимают?
   - Какие эмоции выражают?
   - Как реагируют на ответы персонажа?

2. 🤖 **Эффективность текущего промпта:**
   - Насколько ответы соответствуют ожиданиям пользователей?
   - Есть ли шаблонные/повторяющиеся ответы?
   - Где персонаж теряет контекст?
   - Какие моменты пользователи ценят больше всего?

3. 💡 **Потенциал для улучшения:**
   - Какие аспекты личности персонажа "работают" лучше всего?
   - Что пользователи ожидают, но не получают?
   - Где можно добавить больше персонализации?
   - Как улучшить эмоциональный интеллект персонажа?

4. 🔄 **Конкретные предложения:**
   - Какие фразы/реакции добавить в промпт?
   - Что убрать или изменить?
   - Как лучше обрабатывать частые темы?
   - Как улучшить удержание контекста?

## 📁 ВСЕ ДИАЛОГИ ПОЛЬЗОВАТЕЛЕЙ:
{''.join(all_dialogues_text)}

## 📝 ФОРМАТ ОТВЕТА ДЛЯ УЛУЧШЕНИЯ ПРОМПТА:

### 1. КРАТКИЙ АНАЛИЗ (максимум 500 слов):
- Основные выводы по всем диалогам
- Сильные стороны текущего промпта
- Ключевые проблемы и упущения

### 2. ТОП-10 КОНКРЕТНЫХ УЛУЧШЕНИЙ:
1. [Конкретное изменение 1]
2. [Конкретное изменение 2]
...
10. [Конкретное изменение 10]

### 3. ОБНОВЛЕННЫЙ ПРОМПТ ПЕРСОНАЖА:
[Полный текст нового промпта с ВСЕМИ улучшениями]

### 4. КОММЕНТАРИИ К ИЗМЕНЕНИЯМ:
- Почему именно эти изменения?
- Как они улучшат взаимодействие?
- Что мы ожидаем от новых реакций?

### 5. МЕТРИКИ УСПЕХА:
- Как проверить эффективность изменений?
- На что обращать внимание в будущих диалогах?
- Ключевые индикаторы улучшения

{'=' * 80}
🚀 НАЧИНАЙТЕ АНАЛИЗ! УЧТИТЕ ВСЕ ДИАЛОГИ И ВСЕ СООБЩЕНИЯ ВЫШЕ!
{'=' * 80}
"""
        return prompt

    def export_detailed_dialogues(self, character: CharacterInfo, dialogues: List[UserDialogue], character_dir: Path):
        """Экспорт детальных диалогов в отдельные файлы"""
        dialogues_dir = character_dir / "detailed_dialogues"
        dialogues_dir.mkdir(exist_ok=True)

        for dialogue in dialogues:
            filename = f"user_{dialogue.user_id}_dialog.txt"
            filepath = dialogues_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Диалог с пользователем ID: {dialogue.user_id}\n")
                f.write(f"Персонаж: {character.name}\n")
                f.write(f"Экспорт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")

                if dialogue.user_info:
                    f.write("👤 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:\n")
                    f.write("-" * 40 + "\n")
                    f.write(f"ID: {dialogue.user_id}\n")

                    username = dialogue.user_info.get('username')
                    if username:
                        f.write(f"Username: @{username}\n")

                    first_name = dialogue.user_info.get('first_name')
                    last_name = dialogue.user_info.get('last_name')
                    if first_name or last_name:
                        f.write(f"Имя: {first_name or ''} {last_name or ''}\n".strip() + "\n")

                    if dialogue.user_info.get('created_at'):
                        created = dialogue.user_info['created_at']
                        if isinstance(created, str):
                            created = created[:19]
                        f.write(f"Зарегистрирован: {created}\n")

                    if dialogue.user_info.get('last_seen'):
                        last_seen = dialogue.user_info['last_seen']
                        if isinstance(last_seen, str):
                            last_seen = last_seen[:19]
                        f.write(f"Последняя активность: {last_seen}\n")

                    f.write(f"Администратор: {'Да' if dialogue.user_info.get('is_admin') else 'Нет'}\n")
                    f.write(f"Заблокирован: {'Да' if dialogue.user_info.get('is_blocked') else 'Нет'}\n")
                    f.write("\n")

                f.write("📊 СТАТИСТИКА ДИАЛОГА:\n")
                f.write("-" * 40 + "\n")
                f.write(f"Всего сообщений: {dialogue.total_messages}\n")
                f.write(f"Первое сообщение: {dialogue.first_message_date}\n")
                f.write(f"Последнее сообщение: {dialogue.last_message_date}\n")

                if dialogue.last_message_date and dialogue.first_message_date:
                    duration = dialogue.last_message_date - dialogue.first_message_date
                    f.write(f"Длительность диалога: {duration.days} дней\n")

                f.write("\n" + "=" * 80 + "\n\n")
                f.write("💬 ПОЛНЫЙ ДИАЛОГ:\n\n")

                # Записываем ВСЕ сообщения
                for i, msg in enumerate(dialogue.messages, 1):
                    timestamp_str = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    if msg.role == 'user':
                        f.write(f"[{timestamp_str}] 👤 ПОЛЬЗОВАТЕЛЬ:\n{msg.content}\n\n")
                    else:
                        f.write(f"[{timestamp_str}] 🤖 {character.name.upper()}:\n{msg.content}\n\n")
                        f.write("-" * 40 + "\n\n")

        print(f"  📄 Сохранено детальных диалогов: {len(dialogues)}")

    def export_statistics(self, character_data: Dict, character_dir: Path):
        """Экспорт подробной статистики по персонажу"""
        character = character_data['character']
        dialogues = character_data['dialogues']

        # Подробная статистика
        user_message_counts = [len(d.messages) for d in dialogues]

        stats = {
            'character_id': character.id,
            'character_name': character.name,
            'character_description': character.description[:500] + "..." if len(
                character.description) > 500 else character.description,
            'total_users': len(dialogues),
            'total_messages': sum(user_message_counts),
            'avg_messages_per_user': sum(user_message_counts) / len(dialogues) if dialogues else 0,
            'max_messages_per_user': max(user_message_counts) if user_message_counts else 0,
            'min_messages_per_user': min(user_message_counts) if user_message_counts else 0,
            'active_period': {
                'earliest_date': min(d.first_message_date for d in dialogues) if dialogues else None,
                'latest_date': max(d.last_message_date for d in dialogues) if dialogues else None,
                'days_active': (max(d.last_message_date for d in dialogues) - min(
                    d.first_message_date for d in dialogues)).days if dialogues and len(dialogues) > 1 else 0
            },
            'user_distribution': {
                '1-5 сообщений': len([d for d in dialogues if 1 <= len(d.messages) <= 5]),
                '6-20 сообщений': len([d for d in dialogues if 6 <= len(d.messages) <= 20]),
                '21-50 сообщений': len([d for d in dialogues if 21 <= len(d.messages) <= 50]),
                '51-100 сообщений': len([d for d in dialogues if 51 <= len(d.messages) <= 100]),
                '101-500 сообщений': len([d for d in dialogues if 101 <= len(d.messages) <= 500]),
                '500+ сообщений': len([d for d in dialogues if len(d.messages) > 500]),
            },
            'top_users_by_messages': [
                {
                    'user_id': d.user_id,
                    'message_count': len(d.messages),
                    'first_message': d.first_message_date,
                    'last_message': d.last_message_date
                }
                for d in sorted(dialogues, key=lambda x: len(x.messages), reverse=True)[:10]
            ],
            'export_date': datetime.now().isoformat(),
            'export_timestamp': datetime.now().timestamp()
        }

        # Сохраняем в JSON
        json_path = character_dir / "statistics.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, default=str)

        # Сохраняем в читаемом текстовом формате
        txt_path = character_dir / "statistics.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"📊 ПОЛНАЯ СТАТИСТИКА ПЕРСОНАЖА: {character.name}\n")
            f.write("=" * 60 + "\n\n")

            f.write("📈 ОСНОВНЫЕ МЕТРИКИ:\n")
            f.write(f"• Всего пользователей: {stats['total_users']}\n")
            f.write(f"• Всего сообщений: {stats['total_messages']}\n")
            f.write(f"• Среднее сообщений на пользователя: {stats['avg_messages_per_user']:.1f}\n")
            f.write(f"• Максимум сообщений от одного пользователя: {stats['max_messages_per_user']}\n")
            f.write(f"• Минимум сообщений от одного пользователя: {stats['min_messages_per_user']}\n\n")

            f.write("📅 ПЕРИОД АКТИВНОСТИ:\n")
            if stats['active_period']['earliest_date']:
                f.write(f"• Первое сообщение: {stats['active_period']['earliest_date']}\n")
                f.write(f"• Последнее сообщение: {stats['active_period']['latest_date']}\n")
                f.write(f"• Дней активности: {stats['active_period']['days_active']}\n\n")

            f.write("👥 РАСПРЕДЕЛЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ПО АКТИВНОСТИ:\n")
            for category, count in stats['user_distribution'].items():
                percentage = (count / stats['total_users'] * 100) if stats['total_users'] > 0 else 0
                f.write(f"• {category}: {count} пользователей ({percentage:.1f}%)\n")
            f.write("\n")

            f.write("🏆 ТОП-10 САМЫХ АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:\n")
            for i, user in enumerate(stats['top_users_by_messages'], 1):
                f.write(f"{i}. ID {user['user_id']}: {user['message_count']} сообщений "
                        f"(с {user['first_message'].strftime('%Y-%m-%d')} по {user['last_message'].strftime('%Y-%m-%d')})\n")

        print(f"  📊 Сохранена подробная статистика")

    def export_character_info(self, character: CharacterInfo, character_dir: Path):
        """Экспорт полной информации о персонаже"""
        info_file = character_dir / "character_info.txt"

        with open(info_file, 'w', encoding='utf-8') as f:
            f.write(f"🤖 ПОЛНАЯ ИНФОРМАЦИЯ О ПЕРСОНАЖЕ\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"Имя: {character.name}\n")
            f.write(f"ID: {character.id}\n")
            f.write(f"Статус: {'Активен' if character.is_active else 'Неактивен'}\n")
            f.write(f"Тип аватара: {character.avatar_mime_type}\n\n")

            f.write("📝 ОПИСАНИЕ ПЕРСОНАЖА:\n")
            f.write("-" * 40 + "\n")
            f.write(f"{character.description}\n\n")

            f.write("🎭 ТЕКУЩИЙ СИСТЕМНЫЙ ПРОМПТ:\n")
            f.write("-" * 40 + "\n")
            f.write(f"{character.system_prompt}\n")

        # Сохраняем промпт отдельно для удобства
        prompt_file = character_dir / "current_system_prompt.txt"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(character.system_prompt)

    def export_conversations(self, all_conversations: Dict[int, Dict], global_stats: Dict):
        """Основной метод экспорта ВСЕХ диалогов"""

        summary = {
            'total_characters': len(all_conversations),
            'total_dialogues': sum(data['total_dialogues'] for data in all_conversations.values()),
            'total_messages': sum(data['total_messages'] for data in all_conversations.values()),
            'export_date': datetime.now().isoformat(),
            'global_stats': global_stats
        }

        print("\n" + "=" * 80)
        print("📈 ПОЛНАЯ СТАТИСТИКА ЭКСПОРТА:")
        print(f"   Персонажей: {summary['total_characters']}")
        print(f"   Диалогов: {summary['total_dialogues']}")
        print(f"   Сообщений: {summary['total_messages']}")
        print("=" * 80 + "\n")

        # Сортируем персонажей по количеству сообщений (от большего к меньшему)
        sorted_characters = sorted(
            all_conversations.items(),
            key=lambda x: x[1]['total_messages'],
            reverse=True
        )

        # Экспорт для каждого персонажа
        for character_id, character_data in sorted_characters:
            character = character_data['character']
            dialogues = character_data['dialogues']

            print(f"\n🎭 ПЕРСОНАЖ: {character.name}")
            print(f"   ID: {character_id}")
            print(f"   Диалогов: {len(dialogues)}")
            print(f"   Сообщений: {sum(len(d.messages) for d in dialogues)}")
            print(f"   Статус: {'Активен' if character.is_active else 'Неактивен'}")

            if not dialogues:
                print("   ⚠️ Нет диалогов для экспорта")
                continue

            # Создаем папку для персонажа
            safe_name = "".join(c for c in character.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            character_dir = self.output_dir / safe_name
            character_dir.mkdir(exist_ok=True)

            print(f"  📁 Папка: {character_dir.name}")

            # Экспортируем информацию о персонаже
            self.export_character_info(character, character_dir)

            # Экспортируем ВСЕ диалоги в промпт для AI
            prompt = self.create_analysis_prompt(character, dialogues)
            prompt_file = character_dir / f"{safe_name}_FULL_ANALYSIS_PROMPT.txt"

            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)

            print(f"  🤖 Создан ПОЛНЫЙ промпт для анализа AI ({len(prompt):,} символов)")

            # Экспортируем детальные диалоги в отдельные файлы
            self.export_detailed_dialogues(character, dialogues, character_dir)

            # Экспортируем статистику
            self.export_statistics(character_data, character_dir)

            # Создаем краткий сводный файл
            summary_file = character_dir / "QUICK_SUMMARY.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"📋 БЫСТРЫЙ ОБЗОР: {character.name}\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Диалогов: {len(dialogues)}\n")
                f.write(f"Сообщений: {sum(len(d.messages) for d in dialogues)}\n")
                f.write(f"Пользователей: {len(dialogues)}\n")
                f.write(f"Экспортировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("📁 СОДЕРЖАНИЕ ПАПКИ:\n")
                f.write("-" * 40 + "\n")
                f.write("1. character_info.txt - Полная информация о персонаже\n")
                f.write("2. current_system_prompt.txt - Текущий промпт\n")
                f.write(f"3. {safe_name}_FULL_ANALYSIS_PROMPT.txt - Промпт для AI анализа\n")
                f.write("4. statistics.json/txt - Подробная статистика\n")
                f.write("5. detailed_dialogues/ - Папка с полными диалогами\n")
                f.write("6. QUICK_SUMMARY.txt - Этот файл\n")

        # Сохраняем общую статистику
        summary_file = self.output_dir / "FULL_EXPORT_SUMMARY.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

        # Создаем читаемый отчет
        report_file = self.output_dir / "EXPORT_REPORT.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("📊 ОТЧЕТ ОБ ЭКСПОРТЕ ВСЕХ ДИАЛОГОВ\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Дата экспорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("📈 ОБЩАЯ СТАТИСТИКА:\n")
            f.write(f"• Всего персонажей: {summary['total_characters']}\n")
            f.write(f"• Всего диалогов: {summary['total_dialogues']}\n")
            f.write(f"• Всего сообщений: {summary['total_messages']:,}\n\n")

            f.write("👥 СТАТИСТИКА ПО ПЕРСОНАЖАМ:\n")
            f.write("-" * 40 + "\n")

            for character_id, character_data in sorted_characters:
                character = character_data['character']
                f.write(f"\n🎭 {character.name}:\n")
                f.write(f"  • Диалогов: {character_data['total_dialogues']}\n")
                f.write(f"  • Сообщений: {character_data['total_messages']}\n")
                f.write(
                    f"  • Среднее на диалог: {character_data['total_messages'] / character_data['total_dialogues']:.1f}\n")

            f.write(f"\n\n📁 СТРУКТУРА ЭКСПОРТА:\n")
            f.write(f"Корневая папка: {self.output_dir.absolute()}\n")
            f.write(f"Для каждого персонажа создана отдельная папка с:\n")
            f.write("1. Полным промптом для AI анализа\n")
            f.write("2. Всеми диалогами в отдельных файлах\n")
            f.write("3. Подробной статистикой\n")
            f.write("4. Информацией о персонаже\n\n")

            f.write("🎯 КАК ИСПОЛЬЗОВАТЬ:\n")
            f.write("1. Откройте файл [Персонаж]_FULL_ANALYSIS_PROMPT.txt\n")
            f.write("2. Скопируйте ВЕСЬ текст в ChatGPT/Claude/Gemini\n")
            f.write("3. Попросите AI проанализировать ВСЕ диалоги\n")
            f.write("4. Внедрите предложенные улучшения в промпт бота\n")

        print(f"\n" + "=" * 80)
        print("✅ ЭКСПОРТ ЗАВЕРШЕН УСПЕШНО!")
        print(f"📁 Результаты сохранены в: {self.output_dir.absolute()}")
        print(f"📄 Отчет: {report_file}")
        print("=" * 80)
        print("\n🎯 ДАЛЬНЕЙШИЕ ДЕЙСТВИЯ:")
        print("1. Откройте папку с нужным персонажем")
        print("2. Найдите файл [Имя]_FULL_ANALYSIS_PROMPT.txt")
        print("3. Скопируйте ВЕСЬ текст в AI-ассистента")
        print("4. Получите анализ и улучшения промпта")
        print("5. Внедрите лучшие предложения в вашего бота\n")


def main():
    """Основная функция скрипта"""
    parser = argparse.ArgumentParser(
        description='Экспорт ВСЕХ диалогов из базы данных для анализа и улучшения промптов персонажей',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python %(prog)s
  python %(prog)s --output-dir ./analysis_results
  python %(prog)s --db-host localhost --db-port 5433 --db-name ai-friend

Скрипт экспортирует ВСЕ диалоги БЕЗ ограничений для полного анализа.
        """
    )

    parser.add_argument('--output-dir', type=str, default='./conversation_analysis',
                        help='Директория для сохранения результатов (по умолчанию: ./conversation_analysis)')
    parser.add_argument('--db-host', type=str, default='localhost',
                        help='Хост базы данных (по умолчанию: localhost)')
    parser.add_argument('--db-port', type=int, default=5433,
                        help='Порт базы данных (по умолчанию: 5433)')
    parser.add_argument('--db-name', type=str, default='ai-friend',
                        help='Имя базы данных (по умолчанию: ai-friend)')
    parser.add_argument('--db-user', type=str, default='not_postgres',
                        help='Пользователь базы данных (по умолчанию: not_postgres)')
    parser.add_argument('--db-password', type=str, default='_koa3f7uN-JLH3x@1vR$',
                        help='Пароль базы данных (по умолчанию: _koa3f7uN-JLH3x@1vR$)')

    args = parser.parse_args()

    print(f"🚀 ЗАПУСК ЭКСПОРТА ВСЕХ ДИАЛОГОВ...")
    print(f"📁 Выходная директория: {args.output_dir}")
    print(f"🗄️  База данных: {args.db_name}@{args.db_host}:{args.db_port}")
    print(f"👤 Пользователь БД: {args.db_user}")
    print(f"⏰ Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        # Конфигурация базы данных
        db_config = DatabaseConfig(
            host=args.db_host,
            port=args.db_port,
            database=args.db_name,
            user=args.db_user,
            password=args.db_password
        )

        # Инициализация экспортера
        exporter = ConversationExporter(db_config)

        if not exporter.connect():
            sys.exit(1)

        # Получение ВСЕХ диалогов
        print("\n📥 ЗАГРУЗКА ВСЕХ ДАННЫХ ИЗ БАЗЫ...")

        # Сначала получаем общую статистику
        print("📊 Получение общей статистики...")
        global_stats = exporter.get_character_statistics()

        # Получаем ВСЕ диалоги
        print("💬 Загрузка ВСЕХ диалогов...")
        all_conversations = exporter.get_all_conversations()

        # Инициализация анализатора
        analyzer = DialogueAnalyzer(args.output_dir)

        # Экспорт ВСЕХ данных
        analyzer.export_conversations(all_conversations, global_stats)

        # Закрытие соединения
        exporter.disconnect()

    except KeyboardInterrupt:
        print("\n⚠️ Экспорт прерван пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ЭКСПОРТЕ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()