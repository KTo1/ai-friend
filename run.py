import os
from pathlib import Path
from dotenv import load_dotenv
from presentation.telegram.bot import FriendBot

# Добавим отладочную информацию
print("=== DEBUG ===")
print("Current working directory:", os.getcwd())
print("Files in current directory:", os.listdir('.'))

# Проверим, есть ли .env в текущей директории
env_path = Path('.env')
print(".env exists:", env_path.exists())

# Если .env не в текущей директории, попробуем найти его в родительской или указать абсолютный путь
if not env_path.exists():
    # Попробуем подняться на уровень выше (на всякий случай)
    env_path = Path('..') / '.env'
    print("Trying parent directory:", env_path.exists())

if env_path.exists():
    load_dotenv(env_path)
    print(f"Loaded .env from: {env_path}")
else:
    load_dotenv()  # попытка загрузки из текущего рабочего каталога или родительских
    print("Loaded .env from default location (if any)")

# Проверим, загрузилась ли переменная TELEGRAM_BOT_TOKEN
token = os.getenv("TELEGRAM_BOT_TOKEN")
print("TELEGRAM_BOT_TOKEN:", "SET" if token else "NOT SET")

ai_provider = os.getenv("AI_PROVIDER")
print("AI_PROVIDER:", f"SET {ai_provider}" if token else "NOT SET")


def check_required_vars():
    """Проверка обязательных переменных в зависимости от провайдера"""
    ai_provider = os.getenv("AI_PROVIDER").lower()
    missing_vars = []

    if len(ai_provider) == 0:
        missing_vars.append("AI_PROVIDER")

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
    elif ai_provider == "deepseek":
        if not os.getenv("DEEPSEEK_API_KEY"):
            missing_vars.append("DEEPSEEK_API_KEY")
    # Для huggingface и ollama ключи не обязательны

    return missing_vars


if __name__ == "__main__":
    missing_vars = check_required_vars()

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
