from typing import List, Optional
from datetime import datetime, timedelta
from domain.entity.proactive_message import ProactiveMessage
from infrastructure.database.database import Database


class ProactiveRepository:
    def __init__(self, database: Database):
        self.db = database
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы проактивных сообщений"""
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS proactive_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_type TEXT,
                content TEXT,
                scheduled_time TIMESTAMP,
                is_sent BOOLEAN DEFAULT FALSE,
                sent_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

    def save_message(self, message: ProactiveMessage):
        """Сохранить проактивное сообщение"""
        self.db.execute_query('''
            INSERT INTO proactive_messages 
            (user_id, message_type, content, scheduled_time, is_sent, sent_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.user_id, message.message_type, message.content,
              message.scheduled_time, message.is_sent, message.sent_time))

    def get_pending_messages(self, user_id: int) -> List[ProactiveMessage]:
        """Получить ожидающие сообщения для пользователя"""
        results = self.db.fetch_all('''
            SELECT message_type, content, scheduled_time, is_sent, sent_time
            FROM proactive_messages 
            WHERE user_id = ? AND is_sent = FALSE AND scheduled_time <= ?
            ORDER BY scheduled_time ASC
        ''', (user_id, datetime.now()))

        messages = []
        for result in results:
            messages.append(ProactiveMessage(
                user_id=user_id,
                message_type=result[0],
                content=result[1],
                scheduled_time=datetime.fromisoformat(result[2]),
                is_sent=bool(result[3]),
                sent_time=datetime.fromisoformat(result[4]) if result[4] else None
            ))

        return messages

    def mark_message_sent(self, user_id: int, message_type: str):
        """Пометить сообщение как отправленное"""
        self.db.execute_query('''
            UPDATE proactive_messages 
            SET is_sent = TRUE, sent_time = ?
            WHERE user_id = ? AND message_type = ? AND is_sent = FALSE
        ''', (datetime.now(), user_id, message_type))

    def user_has_active_messages(self, user_id: int) -> bool:
        """Проверить, есть ли активные сообщения у пользователя"""
        result = self.db.fetch_one('''
            SELECT 1 FROM proactive_messages 
            WHERE user_id = ? AND is_sent = FALSE
            LIMIT 1
        ''', (user_id,))
        return result is not None