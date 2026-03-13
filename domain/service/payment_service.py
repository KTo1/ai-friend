import hashlib
import json
import requests

from infrastructure.monitoring.logging import StructuredLogger

TINKOFF_TERMINAL_KEY = "1773075305892"
TINKOFF_TERMINAL_PASSWORD = "_Zv9Fe82C499SJm&"
TINKOFF_INIT_URL = "https://securepay.tinkoff.ru/v2/Init"

class PaymentService:
    """Сервис для управления палтежами"""

    def __init__(self):
        self.logger = StructuredLogger("payment_service")

    def tinkoff_get_link(self, amount, chat_id, order_number):
        data = {
            "Amount": amount,
            "Description": 'Пополнение баланса "Твоя ИИ подруга"',
            "OrderId": f"{chat_id}-n{order_number}",
            "TerminalKey": TINKOFF_TERMINAL_KEY,
            "Password": TINKOFF_TERMINAL_PASSWORD
        }

        # Сортируем ключи
        sorted_items = sorted(data.items())

        # Берем только значения
        values = [str(value) for _, value in sorted_items]

        # Конкатенируем
        concatenated_string = "".join(values)

        # SHA256
        hashed_string = hashlib.sha256(concatenated_string.encode()).hexdigest()

        # Добавляем Token
        data["Token"] = hashed_string

        # Убираем пароль
        del data["Password"]

        try:
            response = requests.post(
                TINKOFF_INIT_URL,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
        except requests.RequestException as e:
            print("Ошибка запроса:", e)
            return False

        if response.status_code != 200:
            print("HTTP ошибка:", response.status_code)
            return False

        try:
            output = response.json()
        except json.JSONDecodeError:
            print("Ошибка декодирования JSON")
            return False

        if output.get("Success") and output.get("PaymentURL"):
            return output["PaymentURL"]
        else:
            print("Ссылка не пришла")
            return False