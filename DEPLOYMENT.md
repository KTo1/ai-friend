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

# Добавьте репозиторий pgvector
sudo apt-get update
sudo apt-get install wget gnupg lsb-release
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list

# Установите расширение
sudo apt-get update
sudo apt-get install postgresql-13-vector  # для PostgreSQL 13
# ИЛИ
sudo apt-get install postgresql-14-vector  # для PostgreSQL 14
# ИЛИ
sudo apt-get install postgresql-15-vector  # для PostgreSQL 15