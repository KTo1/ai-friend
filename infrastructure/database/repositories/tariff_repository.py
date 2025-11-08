import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from domain.entity.tariff_plan import TariffPlan, UserTariff
from domain.entity.rate_limit import RateLimitConfig
from domain.entity.message_limit import MessageLimitConfig
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger


class TariffRepository:
    """Репозиторий для управления тарифными планами"""

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger("tariff_repository")
        self._init_tables()

    def _init_tables(self):
        """Инициализация таблиц тарифов"""
        # Таблица тарифных планов
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS tariff_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                price REAL DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                is_default BOOLEAN DEFAULT FALSE,
                rate_limits TEXT NOT NULL,
                message_limits TEXT NOT NULL,
                features TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица пользовательских тарифов
        self.db.execute_query('''
            CREATE TABLE IF NOT EXISTS user_tariffs (
                user_id INTEGER PRIMARY KEY,
                tariff_plan_id INTEGER NOT NULL,
                activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (tariff_plan_id) REFERENCES tariff_plans (id)
            )
        ''')

        # Создаем тарифы по умолчанию если их нет
        self._create_default_tariffs()

    def _create_default_tariffs(self):
        """Создать тарифы по умолчанию"""
        default_tariffs = [
            TariffPlan(
                id=0,  # Auto-increment
                name='Бесплатный',
                description='Базовый тариф для новых пользователей',
                price=0,
                rate_limits=RateLimitConfig(messages_per_minute=2, messages_per_hour=15, messages_per_day=30),
                message_limits=MessageLimitConfig(max_message_length=100, max_context_messages=3,
                                                  max_context_length=1200),
                is_default=True,
                features={'ai_providers': ['ollama'], 'support': 'basic'}
            ),
            TariffPlan(
                id=0,
                name='Стандартный',
                description='Популярный тариф для активных пользователей',
                price=700,
                rate_limits=RateLimitConfig(messages_per_minute=10, messages_per_hour=100, messages_per_day=500),
                message_limits=MessageLimitConfig(max_message_length=2000, max_context_messages=10,
                                                  max_context_length=4000),
                features={'ai_providers': ['ollama', 'deepseek'], 'support': 'priority'}
            ),
            TariffPlan(
                id=0,
                name='Премиум',
                description='Максимальные возможности для профессионалов',
                price=1900,
                rate_limits=RateLimitConfig(messages_per_minute=20, messages_per_hour=200, messages_per_day=1000),
                message_limits=MessageLimitConfig(max_message_length=5000, max_context_messages=20,
                                                  max_context_length=8000),
                features={'ai_providers': ['ollama', 'deepseek', 'openai'], 'support': '24/7'}
            )
        ]

        for tariff in default_tariffs:
            existing = self.db.fetch_one('SELECT id FROM tariff_plans WHERE name = ?', (tariff.name,))
            if not existing:
                self.save_tariff_plan(tariff)

    def save_tariff_plan(self, tariff: TariffPlan) -> int:
        """Сохранить тарифный план"""
        data = {
            'rate_limits': {
                'messages_per_minute': tariff.rate_limits.messages_per_minute,
                'messages_per_hour': tariff.rate_limits.messages_per_hour,
                'messages_per_day': tariff.rate_limits.messages_per_day
            },
            'message_limits': {
                'max_message_length': tariff.message_limits.max_message_length,
                'max_context_messages': tariff.message_limits.max_context_messages,
                'max_context_length': tariff.message_limits.max_context_length
            },
            'features': tariff.features
        }

        if tariff.id == 0:  # Новый тариф
            result = self.db.execute_query('''
                INSERT INTO tariff_plans 
                (name, description, price, is_active, is_default, rate_limits, message_limits, features, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                tariff.name, tariff.description, tariff.price, tariff.is_active, tariff.is_default,
                json.dumps(data['rate_limits']), json.dumps(data['message_limits']),
                json.dumps(data['features']), datetime.utcnow()
            ))
            return result.lastrowid
        else:  # Обновление существующего
            self.db.execute_query('''
                UPDATE tariff_plans 
                SET name = ?, description = ?, price = ?, is_active = ?, is_default = ?,
                    rate_limits = ?, message_limits = ?, features = ?, updated_at = ?
                WHERE id = ?
            ''', (
                tariff.name, tariff.description, tariff.price, tariff.is_active, tariff.is_default,
                json.dumps(data['rate_limits']), json.dumps(data['message_limits']),
                json.dumps(data['features']), datetime.utcnow(), tariff.id
            ))
            return tariff.id

    def get_tariff_plan(self, tariff_id: int) -> Optional[TariffPlan]:
        """Получить тарифный план по ID"""
        result = self.db.fetch_one('''
            SELECT id, name, description, price, is_active, is_default, 
                   rate_limits, message_limits, features, created_at, updated_at
            FROM tariff_plans WHERE id = ?
        ''', (tariff_id,))

        if result:
            return self._parse_tariff_plan(result)
        return None

    def get_tariff_plan_by_name(self, name: str) -> Optional[TariffPlan]:
        """Получить тарифный план по имени"""
        result = self.db.fetch_one('''
            SELECT id, name, description, price, is_active, is_default,
                   rate_limits, message_limits, features, created_at, updated_at
            FROM tariff_plans WHERE name = ?
        ''', (name,))

        if result:
            return self._parse_tariff_plan(result)
        return None

    def get_all_tariff_plans(self, active_only: bool = True) -> List[TariffPlan]:
        """Получить все тарифные планы"""
        query = '''
            SELECT id, name, description, price, is_active, is_default,
                   rate_limits, message_limits, features, created_at, updated_at
            FROM tariff_plans
        '''
        params = ()

        if active_only:
            query += ' WHERE is_active = TRUE'

        query += ' ORDER BY price ASC'

        results = self.db.fetch_all(query, params)
        return [self._parse_tariff_plan(row) for row in results if row]

    def get_default_tariff_plan(self) -> Optional[TariffPlan]:
        """Получить тарифный план по умолчанию"""
        result = self.db.fetch_one('''
            SELECT id, name, description, price, is_active, is_default,
                   rate_limits, message_limits, features, created_at, updated_at
            FROM tariff_plans WHERE is_default = TRUE AND is_active = TRUE
        ''')

        if result:
            return self._parse_tariff_plan(result)
        return None

    def assign_tariff_to_user(self, user_id: int, tariff_plan_id: int, expires_at: datetime = None) -> bool:
        """Назначить тарифный план пользователю"""
        try:
            self.db.execute_query('''
                INSERT OR REPLACE INTO user_tariffs 
                (user_id, tariff_plan_id, activated_at, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, tariff_plan_id, datetime.utcnow(), expires_at, True))
            return True
        except Exception as e:
            self.logger.error(f"Error assigning tariff to user {user_id}: {e}")
            return False

    def get_user_tariff(self, user_id: int) -> Optional[UserTariff]:
        """Получить тариф пользователя"""
        result = self.db.fetch_one('''
            SELECT ut.user_id, ut.tariff_plan_id, ut.activated_at, ut.expires_at, ut.is_active,
                   tp.id, tp.name, tp.description, tp.price, tp.is_active, tp.is_default,
                   tp.rate_limits, tp.message_limits, tp.features, tp.created_at, tp.updated_at
            FROM user_tariffs ut
            JOIN tariff_plans tp ON ut.tariff_plan_id = tp.id
            WHERE ut.user_id = ? AND ut.is_active = TRUE
        ''', (user_id,))

        if result:
            tariff_plan = self._parse_tariff_plan(result[5:])
            return UserTariff(
                user_id=result[0],
                tariff_plan_id=result[1],
                tariff_plan=tariff_plan,
                activated_at=self._parse_datetime(result[2]),
                expires_at=self._parse_datetime(result[3]),
                is_active=bool(result[4])
            )
        return None

    def remove_user_tariff(self, user_id: int) -> bool:
        """Удалить тариф пользователя"""
        try:
            self.db.execute_query('DELETE FROM user_tariffs WHERE user_id = ?', (user_id,))
            return True
        except Exception as e:
            self.logger.error(f"Error removing tariff from user {user_id}: {e}")
            return False

    def _parse_tariff_plan(self, row) -> TariffPlan:
        """Парсинг тарифного плана из строки БД"""
        try:
            rate_limits_data = json.loads(row[6])
            message_limits_data = json.loads(row[7])
            features_data = json.loads(row[8]) if row[8] else {}

            rate_limits = RateLimitConfig(
                messages_per_minute=rate_limits_data.get('messages_per_minute', 5),
                messages_per_hour=rate_limits_data.get('messages_per_hour', 50),
                messages_per_day=rate_limits_data.get('messages_per_day', 200)
            )

            message_limits = MessageLimitConfig(
                max_message_length=message_limits_data.get('max_message_length', 1000),
                max_context_messages=message_limits_data.get('max_context_messages', 5),
                max_context_length=message_limits_data.get('max_context_length', 2000)
            )

            return TariffPlan(
                id=row[0],
                name=row[1],
                description=row[2],
                price=row[3],
                is_active=bool(row[4]),
                is_default=bool(row[5]),
                rate_limits=rate_limits,
                message_limits=message_limits,
                features=features_data,
                created_at=self._parse_datetime(row[9]),
                updated_at=self._parse_datetime(row[10])
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"Error parsing tariff plan: {e}")
            raise

    def _parse_datetime(self, dt_value) -> datetime:
        """Парсинг datetime"""
        if dt_value is None:
            return datetime.utcnow()

        if isinstance(dt_value, datetime):
            return dt_value

        if isinstance(dt_value, str):
            try:
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                    try:
                        return datetime.strptime(dt_value, fmt)
                    except ValueError:
                        continue
                return datetime.utcnow()
            except Exception:
                return datetime.utcnow()

        return datetime.utcnow()