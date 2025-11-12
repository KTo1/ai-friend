#!/bin/bash

set -e

echo "🚀 Starting Friend Bot deployment..."

# ФИКС: Принудительно используем новый API
export DOCKER_API_VERSION=1.44

# Проверка версий
echo "🔍 Checking Docker versions..."
DOCKER_VERSION=$(docker --version 2>/dev/null | awk '{print $3}' | sed 's/,//')
DOCKER_COMPOSE_VERSION=$(docker compose version 2>/dev/null | grep -oP 'Docker Compose version \K[^\s]+' || echo "Not found")

echo "   Docker: $DOCKER_VERSION"
echo "   Docker Compose: $DOCKER_COMPOSE_VERSION"

# Проверка .env файла
if [ ! -f .env ]; then
    echo "❌ .env file not found. Creating from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "📝 Please edit .env file with your TELEGRAM_BOT_TOKEN and run again."
        exit 1
    else
        echo "❌ .env.example not found. Please create .env file manually."
        cat > .env << EOF
TELEGRAM_BOT_TOKEN=your_bot_token_here
DB_PASSWORD=postgres
AI_PROVIDER=ollama
EOF
        echo "📝 Basic .env created. Please edit it and set your TELEGRAM_BOT_TOKEN."
        exit 1
    fi
fi

# СОЗДАЕМ СТРУКТУРУ ПАПОК (автоматически)
echo "📁 Creating directory structure..."
mkdir -p \
    postgres/data \
    postgres/backups \
    postgres/init \
    prometheus \
    grafana/provisioning/datasources \
    grafana/dashboards

# УБИРАЕМ ВСЮ НАСТРОЙКУ ПРАВ - DOCKER САМ РАЗБЕРЕТСЯ!
echo "✅ Directory structure created - Docker will handle permissions automatically"

# СОЗДАЕМ БАЗОВЫЕ КОНФИГИ ЕСЛИ ИХ НЕТ
echo "📄 Creating default configs if missing..."

# Prometheus config
if [ ! -f prometheus/prometheus.yml ]; then
    echo "   Creating prometheus/prometheus.yml"
    cat > prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'friend-bot'
    static_configs:
      - targets: ['bot:8000']
    scrape_interval: 10s
EOF
fi

# Grafana datasource
if [ ! -f grafana/provisioning/datasources/prometheus.yml ]; then
    echo "   Creating grafana/provisioning/datasources/prometheus.yml"
    cat > grafana/provisioning/datasources/prometheus.yml << 'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF
fi

# Backup script
if [ ! -f postgres/backup.sh ]; then
    echo "   Creating postgres/backup.sh"
    cat > postgres/backup.sh << 'EOF'
#!/bin/bash
# ФИКС: Принудительно используем новый API
export DOCKER_API_VERSION=1.44

set -e
BACKUP_DIR="./postgres/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_${DATE}.sql"
echo "💾 Creating PostgreSQL backup: $BACKUP_FILE"
docker compose exec -T postgres pg_dump -U postgres -d ai-friend --clean --if-exists > "$BACKUP_FILE"
if [ -s "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "✅ Backup completed: $BACKUP_FILE ($BACKUP_SIZE)"
    ls -t "$BACKUP_DIR"/backup_*.sql | tail -n +11 | xargs -r rm
else
    echo "❌ Backup failed - file is empty!"
    exit 1
fi
EOF
    chmod +x postgres/backup.sh
fi

# Restore script
if [ ! -f postgres/restore.sh ]; then
    echo "   Creating postgres/restore.sh"
    cat > postgres/restore.sh << 'EOF'
#!/bin/bash
# ФИКС: Принудительно используем новый API
export DOCKER_API_VERSION=1.44

set -e
echo "🔄 Starting PostgreSQL restore..."
BACKUP_DIR="./postgres/backups"
if [ -n "$1" ]; then
    BACKUP_FILE="$1"
else
    echo "📁 Available backups:"
    ls -lt "$BACKUP_DIR"/backup_*.sql 2>/dev/null | head -10
    read -p "📝 Enter backup filename: " BACKUP_FILE
    BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
fi
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi
echo "⚠️  WARNING: This will overwrite current database!"
read -p "❓ Are you sure? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Restore cancelled"
    exit 0
fi
echo "🔄 Restoring from: $BACKUP_FILE"
docker compose exec -T postgres psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS ai-friend;"
docker compose exec -T postgres psql -U postgres -d postgres -c "CREATE DATABASE ai-friend;"
docker compose exec -T postgres psql -U postgres -d friend_bot < "$BACKUP_FILE"
echo "✅ Restore completed!"
EOF
    chmod +x postgres/restore.sh
fi

# Останавливаем предыдущие контейнеры
echo "🛑 Stopping any existing containers..."
docker compose down || true

# Сборка и запуск
echo "🐳 Building and starting containers..."
docker compose build
docker compose up -d

echo "⏳ Waiting for services to start..."
sleep 25

# Проверка статуса
echo "🔍 Checking services status..."
docker compose ps

# Проверяем что сервисы запустились
echo "🔧 Verifying services..."
if docker compose exec postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo "✅ PostgreSQL is ready"
else
    echo "❌ PostgreSQL failed to start"
    docker compose logs postgres
    exit 1
fi

if curl -s http://localhost:8001/metrics > /dev/null 2>&1; then
    echo "✅ Bot metrics are available"
else
    echo "⚠️  Bot metrics not available yet, checking logs..."
    docker compose logs bot | tail -10
fi

echo "🎉 Deployment completed successfully!"
echo ""
echo "📊 Access your services:"
echo "   - Bot Metrics: http://localhost:8001/metrics"
echo "   - Prometheus:  http://localhost:9091"
echo "   - Grafana:     http://localhost:3001 (admin/admin)"
echo "   - PostgreSQL:  localhost:5433"
echo ""
echo "💾 Database management:"
echo "   - ./postgres/backup.sh    # Backup database"
echo "   - ./postgres/restore.sh   # Restore from backup"
echo ""
echo "🐳 Useful commands:"
echo "   - docker compose logs -f bot    # View bot logs"
echo "   - docker compose restart bot    # Restart bot"
echo "   - docker compose down           # Stop all services"