import json
from typing import List, Dict, Any, Optional, Tuple
from domain.entity.conversation_summary import ConversationSummary
from domain.interfaces.ai_client import AIClientInterface
from infrastructure.monitoring.logging import StructuredLogger


class SummaryService:

    def __init__(self, ai_client: AIClientInterface):
        self.ai_client = ai_client
        self.logger = StructuredLogger('summary_service')

    async def generate_dialog_summary(self, messages: List[Dict],
                                      character_name: str) -> Optional[Dict[str, Any]]:
        """Генерирует краткую суммаризацию диалога (уровень 1)"""

        try:
            # Берем последние 20 сообщений для суммаризации
            recent_messages = messages[-20:]

            # Формируем текст диалога
            dialog_text = "Последний диалог:\n\n"
            for msg in recent_messages:
                role = "👤 Пользователь" if msg['role'] == 'user' else f"🤖 {character_name}"
                dialog_text += f"{role}: {msg['content']}\n\n"

            prompt = [
                {
                    'role': 'system',
                    'content': f'''Ты создаешь краткую суммаризацию диалога для персонажа {character_name}.

Ты — эксперт по поддержанию контекста в диалогах.

Прочитай последние сообщения и напиши КРАТКОЕ резюме текущей сцены (максимум 4 предложения). Фокус строго на:

1. Текущая физическая поза / положение тел
2. Где находится член / руки / другие ключевые части
3. Что именно происходит прямо сейчас (действие в настоящем времени)
4. Краткое эмоциональное состояние персонажа

Не добавляй ничего лишнего. Не пересказывай весь сюжет. Только главное.

'''
                },
                {
                    'role': 'user',
                    'content': f"Суммаризируй этот диалог:\n\n{dialog_text}"
                }
            ]

            response = await self.ai_client.generate_response(
                prompt,
                max_tokens=150,
                temperature=0.3
            )

            return {
                'content': response.strip(),
                'level': 1,
                'message_count': len(recent_messages)
            }

        except Exception as e:
            self.logger.error(f'Error generating dialog summary: {e}')
            return None

    async def generate_session_summary(self, messages: List[Dict],
                                       previous_summaries: List[str],
                                       character_name: str) -> Optional[Dict[str, Any]]:
        """Генерирует детальную суммаризацию сессии/отношений (уровень 2)"""

        try:
            # Собираем общий текст всех сообщений (ограничиваем для экономии токенов)
            all_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-50:]])

            # Контекст из предыдущих суммаризаций
            context = "Предыдущие суммаризации:\n" + "\n".join(previous_summaries) if previous_summaries else ""

            prompt = [
                {
                    'role': 'system',
                    'content': f'''Ты создаешь детальную суммаризацию отношений пользователя с персонажем {character_name}.

Включи:
1. Характерные паттерны общения
2. Темы, которые интересны/важны пользователю
3. Эмоциональную динамику
4. Особенности, которые стоит учитывать в будущем общении

Будь конкретным и полезным для персонажа.'''
                },
                {
                    'role': 'user',
                    'content': f"{context}\n\nДиалог для анализа:\n{all_text}"
                }
            ]

            response = await self.ai_client.generate_response(
                prompt,
                max_tokens=300,
                temperature=0.4
            )

            return {
                'content': response.strip(),
                'level': 2,
                'message_count': len(messages)
            }

        except Exception as e:
            self.logger.error(f'Error generating session summary: {e}')
            return None

    def should_generate_level1(self, message_count: int,
                               last_summary_count: int = 0) -> bool:
        """Нужно ли генерировать суммаризацию уровня 1?"""
        # Генерируем каждые 10 сообщений или если сообщений стало в 2 раза больше с последней суммаризации
        return (message_count >= 10 and
                (last_summary_count == 0 or message_count >= last_summary_count * 2))

    def should_generate_level2(self, message_count: int,
                               hours_since_last: float = 24.0) -> bool:
        """Нужно ли генерировать суммаризацию уровня 2?"""
        # Генерируем если накопилось 50+ сообщений или прошло 24 часа
        return message_count >= 50 or hours_since_last >= 24

    def prepare_for_context(self, summaries: List[ConversationSummary]) -> str:
        """Подготавливает суммаризации для контекста AI"""

        if not summaries:
            return ""

        # Берем только свежие суммаризации
        recent_summaries = [s for s in summaries if s.is_recent]

        if not recent_summaries:
            return ""

        context = "📝 **Суммаризации предыдущих разговоров:**\n\n"

        for summary in sorted(recent_summaries, key=lambda x: x.level, reverse=True)[:3]:
            if summary.level == 1:
                context += f"💭 Кратко: {summary.content}\n\n"
            else:
                context += f"📚 Детально: {summary.content}\n\n"

        return context