from typing import List, Dict
from infrastructure.database.database import Database


class ConversationRepository:
    def __init__(self, database: Database):
        self.db = database

    def save_message(self, user_id: int, role: str, content: str,
                     max_context_messages: int = 15):
        """Сохранить сообщение с учетом лимита контекста"""
        self.db.execute_query('''
            INSERT INTO conversation_context (user_id, role, content)
            VALUES (%s, %s, %s)
        ''', (user_id, role, content))

        # Удаляем старые сообщения, оставляя только max_context_messages последних
        self.db.execute_query('''
            DELETE FROM conversation_context 
            WHERE user_id = %s AND id NOT IN (
                SELECT id FROM conversation_context 
                WHERE user_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            )
        ''', (user_id, user_id, max_context_messages))

    def get_conversation_context(self, user_id: int,
                                 max_context_messages: int = 10) -> List[Dict]:
        """Получить контекст разговора с учетом лимита"""
        results = self.db.fetch_all('''
            SELECT role, content 
            FROM conversation_context 
            WHERE user_id = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        ''', (user_id, max_context_messages))

        return [{"role": row["role"], "content": row["content"]} for row in reversed(results)]

    def clear_conversation(self, user_id: int):
        """Очистить историю разговора"""
        self.db.execute_query('DELETE FROM conversation_context WHERE user_id = %s', (user_id,))

    def get_conversation_stats(self, user_id: int) -> Dict:
        """Получить статистику разговора"""
        total_messages = self.db.fetch_one(
            'SELECT COUNT(*) FROM conversation_context WHERE user_id = %s',
            (user_id,)
        )
        total_messages = total_messages["count"] if total_messages else 0

        last_message = self.db.fetch_one('''
            SELECT timestamp FROM conversation_context 
            WHERE user_id = %s 
            ORDER BY timestamp DESC LIMIT 1
        ''', (user_id,))

        return {
            'total_messages': total_messages,
            'last_message_time': last_message["timestamp"] if last_message else None
        }