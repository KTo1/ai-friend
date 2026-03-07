from datetime import datetime
from typing import Optional, Dict, Any
from infrastructure.database.database import Database
from infrastructure.monitoring.logging import StructuredLogger


class PaymentRepository:
    """Репозиторий для работы с платежами в звёздах Telegram."""

    def __init__(self, database: Database):
        self.db = database
        self.logger = StructuredLogger('payment_repository')
        self._init_table()

    def _init_table(self):
        """Создаёт таблицу payments, если её нет."""
        try:
            self.db.execute_query("""
                                  CREATE TABLE IF NOT EXISTS payments
                                  (
                                      id                         SERIAL PRIMARY KEY,
                                      user_id                    BIGINT  NOT NULL,
                                      tariff_plan_id             INTEGER NOT NULL,
                                      amount                     INTEGER NOT NULL,
                                      currency                   TEXT    NOT NULL DEFAULT 'XTR',
                                      payload                    TEXT    NOT NULL UNIQUE,
                                      status                     TEXT    NOT NULL DEFAULT 'initiated',
                                      telegram_payment_charge_id TEXT,
                                      provider_payment_charge_id TEXT,
                                      created_at                 TIMESTAMP        DEFAULT CURRENT_TIMESTAMP,
                                      updated_at                 TIMESTAMP        DEFAULT CURRENT_TIMESTAMP,

                                      CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                                      CONSTRAINT fk_tariff FOREIGN KEY (tariff_plan_id) REFERENCES tariff_plans (id) ON DELETE CASCADE
                                  );
                                  """)
            self.db.execute_query("""
                                  CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments (user_id);
                                  CREATE INDEX IF NOT EXISTS idx_payments_payload ON payments (payload);
                                  """)
            self.logger.info("Payments table initialized")
        except Exception as e:
            self.logger.error(f"Error initializing payments table: {e}")

    def create_payment(self, user_id: int, tariff_plan_id: int, amount: int,
                       payload: str, currency: str = 'XTR') -> Optional[int]:
        """
        Создаёт запись о начале платежа.
        Возвращает ID созданной записи или None при ошибке.
        """
        try:
            result = self.db.fetch_one("""
                                       INSERT INTO payments (user_id, tariff_plan_id, amount, currency, payload, status,
                                                             created_at, updated_at)
                                       VALUES (%s, %s, %s, %s, %s, 'initiated', %s, %s)
                                       RETURNING id
                                       """, (user_id, tariff_plan_id, amount, currency, payload,
                                             datetime.utcnow(), datetime.utcnow()))
            return result['id'] if result else None
        except Exception as e:
            self.logger.error(f"Error creating payment for user {user_id}: {e}")
            return None

    def update_payment_success(self, payload: str,
                               telegram_payment_charge_id: str,
                               provider_payment_charge_id: str) -> bool:
        """
        Обновляет запись платежа при успешной оплате.
        """
        try:
            self.db.execute_query("""
                                  UPDATE payments
                                  SET status                     = 'success',
                                      telegram_payment_charge_id = %s,
                                      provider_payment_charge_id = %s,
                                      updated_at                 = %s
                                  WHERE payload = %s
                                    AND status = 'initiated'
                                  """, (telegram_payment_charge_id, provider_payment_charge_id,
                                        datetime.utcnow(), payload))
            return True
        except Exception as e:
            self.logger.error(f"Error updating payment success for payload {payload}: {e}")
            return False

    def get_payment_by_payload(self, payload: str) -> Optional[Dict[str, Any]]:
        """Возвращает запись платежа по payload (для отладки)."""
        try:
            return self.db.fetch_one("SELECT * FROM payments WHERE payload = %s", (payload,))
        except Exception as e:
            self.logger.error(f"Error fetching payment by payload {payload}: {e}")
            return None