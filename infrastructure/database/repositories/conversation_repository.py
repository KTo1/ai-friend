from typing import List, Dict
from domain.value_object.message import Message
from infrastructure.database.database import Database


class ConversationRepository:
    def __init__(self, database: Database):
        self.db = database

    def save_message(self, user_id: int, role: str, content: str):
        """Сохранить сообщение"""
        self.db.execute_query('''
            INSERT INTO conversation_context (user_id, role, content)
            VALUES (?, ?, ?)
        ''', (user_id, role, content))

        self.db.execute_query('''
            DELETE FROM conversation_context 
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM conversation_context 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 15
            )
        ''', (user_id, user_id))

    def get_conversation_context(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получить контекст разговора"""
        results = self.db.fetch_all('''
            SELECT role, content 
            FROM conversation_context 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))

        return [{"role": role, "content": content} for role, content in reversed(results)]

    def clear_conversation(self, user_id: int):
        """Очистить историю разговора"""
        self.db.execute_query('DELETE FROM conversation_context WHERE user_id = ?', (user_id,))