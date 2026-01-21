import json
from typing import List, Optional
from datetime import datetime
from domain.entity.tariff_plan import TariffPlan, UserTariff, RateLimitConfig, MessageLimitConfig
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
        try:
            self._create_default_tariffs()

        except Exception as e:
            self.logger.error(f"Error initializing tariff tables: {e}")

    def _create_default_tariffs(self):
        """Создать тарифы по умолчанию если их нет"""
        default_tariffs = [
            {
                'name': 'Премиум',
                'description': "Безлимитные сообщения в день \n Нет ограничений на длину сообщений\n Долговременная память диалога\n Приоритетная поддержка",
                'price': 899,
                'rate_limits': RateLimitConfig(messages_per_minute=120, messages_per_hour=99999, messages_per_day=99999),
                'message_limits': MessageLimitConfig(max_message_length=4000, max_context_messages=30),
                'is_default': True,
            }
        ]

        for tariff_data in default_tariffs:
            existing = self.db.fetch_one('SELECT id FROM tariff_plans WHERE name = %s', (tariff_data['name'],))
            if not existing:
                tariff = TariffPlan(
                    id=0,
                    name=tariff_data['name'],
                    description=tariff_data['description'],
                    price=tariff_data['price'],
                    rate_limits=tariff_data['rate_limits'],
                    message_limits=tariff_data['message_limits'],
                    is_default=tariff_data.get('is_default', False),
                    features=tariff_data.get('features', {})
                )
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
            },
            'features': tariff.features
        }

        if tariff.id == 0:  # Новый тариф
            result = self.db.execute_query('''
                INSERT INTO tariff_plans 
                (name, description, price, is_active, is_default, rate_limits, message_limits, features, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                tariff.name, tariff.description, tariff.price, tariff.is_active, tariff.is_default,
                json.dumps(data['rate_limits']), json.dumps(data['message_limits']),
                json.dumps(data['features']), datetime.utcnow()
            ))

            if result and hasattr(result, '__getitem__') and 'id' in result:
                return result['id']
            else:
                last_id = self.db.fetch_one("SELECT LASTVAL() as id")
                return last_id['id'] if last_id else 0
        else:  # Обновление существующего
            self.db.execute_query('''
                UPDATE tariff_plans 
                SET name = %s, description = %s, price = %s, is_active = %s, is_default = %s,
                    rate_limits = %s, message_limits = %s, features = %s, updated_at = %s
                WHERE id = %s
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
            FROM tariff_plans WHERE id = %s
        ''', (tariff_id,))

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
                INSERT INTO user_tariffs 
                (user_id, tariff_plan_id, activated_at, expires_at, is_active)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    tariff_plan_id = EXCLUDED.tariff_plan_id,
                    activated_at = EXCLUDED.activated_at,
                    expires_at = EXCLUDED.expires_at,
                    is_active = EXCLUDED.is_active
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
            WHERE ut.user_id = %s AND ut.is_active = TRUE
        ''', (user_id,))

        if result:
            tariff_plan = self._parse_tariff_plan({
                'id': result['id'],
                'name': result['name'],
                'description': result['description'],
                'price': result['price'],
                'is_active': result['is_active'],
                'is_default': result['is_default'],
                'rate_limits': result['rate_limits'],
                'message_limits': result['message_limits'],
                'features': result['features'],
                'created_at': result['created_at'],
                'updated_at': result['updated_at']
            })
            return UserTariff(
                user_id=result['user_id'],
                tariff_plan_id=result['tariff_plan_id'],
                tariff_plan=tariff_plan,
                activated_at=self._parse_datetime(result['activated_at']),
                expires_at=self._parse_datetime(result['expires_at']),
                is_active=bool(result['is_active'])
            )
        return None

    def remove_user_tariff(self, user_id: int) -> bool:
        """Удалить тариф пользователя"""
        try:
            self.db.execute_query('DELETE FROM user_tariffs WHERE user_id = %s', (user_id,))
            return True
        except Exception as e:
            self.logger.error(f"Error removing tariff from user {user_id}: {e}")
            return False

    def _parse_tariff_plan(self, row) -> TariffPlan:
        """Парсинг тарифного плана из строки БД"""
        try:
            rate_limits_data = row['rate_limits']
            message_limits_data = row['message_limits']
            features_data = row['features'] if row['features'] else {}

            if isinstance(rate_limits_data, str):
                rate_limits_data = json.loads(rate_limits_data)
            if isinstance(message_limits_data, str):
                message_limits_data = json.loads(message_limits_data)
            if isinstance(features_data, str):
                features_data = json.loads(features_data) if features_data else {}

            rate_limits = RateLimitConfig(
                messages_per_minute=rate_limits_data.get('messages_per_minute', 2),
                messages_per_hour=rate_limits_data.get('messages_per_hour', 15),
                messages_per_day=rate_limits_data.get('messages_per_day', 30)
            )

            message_limits = MessageLimitConfig(
                max_message_length=message_limits_data.get('max_message_length', 2000),
                max_context_messages=message_limits_data.get('max_context_messages', 10)
            )

            return TariffPlan(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                price=row['price'],
                is_active=bool(row['is_active']),
                is_default=bool(row['is_default']),
                rate_limits=rate_limits,
                message_limits=message_limits,
                features=features_data,
                created_at=self._parse_datetime(row['created_at']),
                updated_at=self._parse_datetime(row['updated_at'])
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
                return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
            except Exception:
                return datetime.utcnow()

        return datetime.utcnow()