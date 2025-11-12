# Деплой Friend Bot

## Быстрый старт:

```bash
# 1. Клонируйте и перейдите в папку
git clone <your-repo>
cd ai-friend

# 2. Настройте .env файл
cp .env.example .env
nano .env  # Заполните TELEGRAM_BOT_TOKEN

# 3. Запустите деплой (всё сделает автоматически)
chmod +x deploy.sh
./deploy.sh