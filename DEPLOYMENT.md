# Деплой Friend Bot с ELK стеком

## Требования
- Docker & Docker Compose
- 4GB+ RAM (рекомендуется 8GB для ELK)
- Linux/Ubuntu 20.04+

## Быстрый старт:

# 1. Клонируйте и перейдите в папку
git clone <your-repo>
cd ai-friend

# 2. Настройте .env файл
cp .env.example .env
nano .env  # Заполните TELEGRAM_BOT_TOKEN и другие переменные

# 3. Запустите деплой
chmod +x deploy.sh
./deploy.sh