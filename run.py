import os
from dotenv import load_dotenv

# Загрузка переменных окружения ДО всех импортов
load_dotenv()

from presentation.telegram.bot import FriendBot


def check_required_vars():
    """Проверка обязательных переменных в зависимости от провайдера"""
    ai_provider = os.getenv("AI_PROVIDER", "ollama").lower()
    missing_vars = []

    # Обязательные для всех
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        missing_vars.append("TELEGRAM_BOT_TOKEN")

    # Проверки по провайдерам
    if ai_provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            missing_vars.append("OPENAI_API_KEY")
    elif ai_provider == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            missing_vars.append("GEMINI_API_KEY")
    # Для huggingface и ollama ключи не обязательны

    return missing_vars

if __name__ == "__main__":
    missing_vars = check_required_vars()

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file")
        exit(1)

    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file")
        exit(1)

    # Логируем загруженную конфигурацию
    print("🔧 Loaded configuration:")
    print(f"   Metrics port: {os.getenv('METRICS_PORT', '8000')}")
    print(f"   Tracing: {os.getenv('ENABLE_TRACING', 'true')}")
    print(f"   Log level: {os.getenv('LOG_LEVEL', 'INFO')}")

    bot = FriendBot()
    bot.run()
