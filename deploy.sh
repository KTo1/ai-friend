#!/bin/bash

set -e  # Выход при ошибке

# ФИКС: Принудительно используем новый API
export DOCKER_API_VERSION=1.44

echo "🚀 Starting Friend Bot Deployment with ELK Stack and Monitoring..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

info() {
    echo -e "${CYAN}[INFO] $1${NC}"
}

# Check requirements
check_requirements() {
    log "Checking system requirements..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    # Check .env file
    if [ ! -f .env ]; then
        error ".env file not found. Please create it from .env.example"
        exit 1
    fi

    # Check TELEGRAM_BOT_TOKEN
    if ! grep -q "TELEGRAM_BOT_TOKEN=." .env; then
        error "TELEGRAM_BOT_TOKEN is not set in .env file"
        exit 1
    fi

    log "All requirements satisfied ✓"
}

# Create necessary directories
create_directories() {
    log "Creating necessary directories..."

    mkdir -p logs
    mkdir -p postgres/backups
    mkdir -p postgres/init
    mkdir -p postgres/data
    mkdir -p elk/elasticsearch/data
    mkdir -p elk/logstash
    mkdir -p elk/logstash/data
    mkdir -p prometheus/data
    mkdir -p grafana/provisioning/datasources
    mkdir -p grafana/provisioning/dashboards
    mkdir -p grafana/dashboards
    mkdir -p backup/scripts

    log "Directories created ✓"
}

# Create Logstash configuration
create_logstash_config() {
    log "Creating Logstash configuration..."

    cat > elk/logstash/logstash.conf << 'EOF'
input {
  file {
    path => "/var/log/bot/friend-bot.log"
    start_position => "beginning"
    sincedb_path => "/dev/null"
    codec => json
  }
}

filter {
  # Парсим JSON логи
  json {
    source => "message"
  }

  # Добавляем timestamp
  date {
    match => [ "timestamp", "ISO8601" ]
    target => "@timestamp"
  }

  # Добавляем поле service если отсутствует
  if ![service] {
    mutate {
      add_field => { "service" => "friend-bot" }
    }
  }

  # Удаляем поле message если оно дублирует content
  if [message] and [content] and [message] == [content] {
    mutate {
      remove_field => [ "message" ]
    }
  }

  # Очистка полей
  mutate {
    remove_field => [ "host" ]
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "friend-bot-logs-%{+YYYY.MM.dd}"
  }

  # Для дебага - вывод в консоль
  stdout {
    codec => rubydebug
  }
}
EOF

    # Создаем дополнительный конфиг для системных логов
    cat > elk/logstash/system-logs.conf << 'EOF'
input {
  file {
    path => "/var/log/bot/*.log"
    exclude => ["/var/log/bot/friend-bot.log"]
    start_position => "beginning"
    sincedb_path => "/dev/null"
    codec => plain
    tags => ["system"]
  }
}

filter {
  if "system" in [tags] {
    grok {
      match => { "message" => "\[%{TIMESTAMP_ISO8601:timestamp}\] %{LOGLEVEL:loglevel} %{GREEDYDATA:message_text}" }
    }

    date {
      match => [ "timestamp", "ISO8601" ]
      target => "@timestamp"
    }

    mutate {
      add_field => {
        "service" => "friend-bot"
        "log_type" => "system"
      }
    }
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "friend-bot-system-%{+YYYY.MM.dd}"
  }
}
EOF

    # Устанавливаем правильные права
    chmod 644 elk/logstash/*.conf

    log "Logstash configuration created ✓"
}

# Setup ELK stack
setup_elk() {
    log "Setting up ELK stack..."

    # Устанавливаем правильные права для директорий с логами
    chmod -R 777 logs
    chmod -R 755 elk

    log "ELK stack setup completed ✓"
}

# Create necessary database initialization
create_db_init() {
    log "Creating database initialization scripts..."

    # Создаем базовый SQL init файл если не существует
    if [ ! -f postgres/init/init.sql ]; then
        cat > postgres/init/init.sql << 'EOF'
-- Friend Bot Database Initialization
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create additional indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversation_context_user_id_timestamp
ON conversation_context(user_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_user_activity_last_message
ON user_activity(last_message_time DESC);

CREATE INDEX IF NOT EXISTS idx_users_created_at
ON users(created_at DESC);
EOF
        log "Database initialization script created ✓"
    fi
}

# Create backup script
create_backup_script() {
    log "Creating backup script..."

    cat > backup/scripts/backup.sh << 'EOF'
#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Configuration
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="ai-friend-backup-${TIMESTAMP}.sql"
RETENTION_DAYS=7

log "Starting database backup..."

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    error "Backup directory $BACKUP_DIR does not exist"
    exit 1
fi

# Create backup
log "Creating backup: $BACKUP_FILE"
if docker-compose exec -T postgres pg_dump -U postgres -d ai-friend --verbose > "$BACKUP_DIR/$BACKUP_FILE"; then
    log "Backup created successfully: $BACKUP_FILE"

    # Compress backup
    log "Compressing backup..."
    gzip "$BACKUP_DIR/$BACKUP_FILE"
    log "Backup compressed: $BACKUP_FILE.gz"

    # Clean old backups
    log "Cleaning backups older than $RETENTION_DAYS days..."
    find "$BACKUP_DIR" -name "ai-friend-backup-*.sql.gz" -mtime +$RETENTION_DAYS -delete

    # List current backups
    log "Current backups:"
    ls -la "$BACKUP_DIR"/ai-friend-backup-*.sql.gz 2>/dev/null || echo "No backups found"
else
    error "Backup failed!"
    exit 1
fi

log "Backup completed successfully!"
EOF

    # Создаем скрипт восстановления
    cat > backup/scripts/restore.sh << 'EOF'
#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Configuration
BACKUP_DIR="/backups"

log "Starting database restore..."

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    error "Backup directory $BACKUP_DIR does not exist"
    exit 1
fi

# List available backups
log "Available backups:"
BACKUP_FILES=($(ls -t "$BACKUP_DIR"/ai-friend-backup-*.sql.gz 2>/dev/null || true))

if [ ${#BACKUP_FILES[@]} -eq 0 ]; then
    error "No backup files found in $BACKUP_DIR"
    exit 1
fi

for i in "${!BACKUP_FILES[@]}"; do
    echo "  $((i+1))). ${BACKUP_FILES[$i]}"
done

# Ask user to select backup
echo ""
read -p "Select backup to restore (1-${#BACKUP_FILES[@]}): " backup_choice

if ! [[ "$backup_choice" =~ ^[0-9]+$ ]] || [ "$backup_choice" -lt 1 ] || [ "$backup_choice" -gt ${#BACKUP_FILES[@]} ]; then
    error "Invalid selection"
    exit 1
fi

SELECTED_BACKUP="${BACKUP_FILES[$((backup_choice-1))]}"
BACKUP_BASENAME=$(basename "$SELECTED_BACKUP" .gz)

log "Selected backup: $SELECTED_BACKUP"

# Confirm restoration
read -p "Are you sure you want to restore from this backup? This will overwrite current data! (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    log "Restore cancelled"
    exit 0
fi

# Stop bot service to prevent data corruption
log "Stopping bot service..."
docker-compose stop bot

# Decompress backup
log "Decompressing backup..."
gunzip -c "$SELECTED_BACKUP" > "/tmp/$BACKUP_BASENAME"

# Restore database
log "Restoring database..."
if docker-compose exec -T postgres psql -U postgres -d ai-friend -f /backups/restore.tmp > /dev/null 2>&1; then
    log "Database restored successfully!"
else
    # If database doesn't exist, create it first
    log "Creating database..."
    docker-compose exec -T postgres createdb -U postgres ai-friend 2>/dev/null || true

    log "Restoring to new database..."
    docker-compose exec -T postgres psql -U postgres -d ai-friend -f /backups/restore.tmp
fi

# Cleanup
rm -f "/tmp/$BACKUP_BASENAME"

# Start bot service
log "Starting bot service..."
docker-compose start bot

log "Restore completed successfully!"
EOF

    # Создаем скрипт автоматического бэкапа
    cat > backup/scripts/auto_backup.sh << 'EOF'
#!/bin/bash

set -e

# Configuration
BACKUP_DIR="/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="ai-friend-auto-backup-${TIMESTAMP}.sql.gz"
RETENTION_DAYS=3

log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1"
}

# Create backup
log "Starting automatic backup..."
docker-compose exec -T postgres pg_dump -U postgres -d ai-friend | gzip > "$BACKUP_DIR/$BACKUP_FILE"

if [ $? -eq 0 ]; then
    log "Automatic backup successful: $BACKUP_FILE"

    # Clean old automatic backups
    find "$BACKUP_DIR" -name "ai-friend-auto-backup-*.sql.gz" -mtime +$RETENTION_DAYS -delete
else
    log "Automatic backup failed!"
    exit 1
fi
EOF

    # Устанавливаем права на выполнение
    chmod +x backup/scripts/*.sh

    log "Backup scripts created ✓"
}

# Setup monitoring
setup_monitoring() {
    log "Setting up monitoring stack..."

    # Создаем конфигурацию Prometheus
    cat > prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  # - "first_rules.yml"
  # - "second_rules.yml"

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'bot'
    static_configs:
      - targets: ['bot:8000']
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          # - alertmanager:9093
EOF

    # Создаем datasource для Grafana
    cat > grafana/provisioning/datasources/prometheus.yml << 'EOF'
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
EOF

    log "Monitoring stack setup completed ✓"
}

# Wait for services to be healthy
wait_for_services() {
    log "Waiting for services to be healthy..."

    # Wait for PostgreSQL
    log "Waiting for PostgreSQL..."
    until docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do
        sleep 5
        echo -n "."
    done
    echo ""
    log "PostgreSQL is ready ✓"

    # Wait for Elasticsearch (может занять время при первом запуске)
    log "Waiting for Elasticsearch (this may take a while on first start)..."
    local es_attempts=0
    local max_es_attempts=30

    while [ $es_attempts -lt $max_es_attempts ]; do
        if curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then
            local es_status=$(curl -s http://localhost:9200/_cluster/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
            if [ "$es_status" = "green" ] || [ "$es_status" = "yellow" ]; then
                log "Elasticsearch is ready (status: $es_status) ✓"
                break
            fi
        fi

        es_attempts=$((es_attempts + 1))
        sleep 10
        echo -n "."
    done

    if [ $es_attempts -eq $max_es_attempts ]; then
        warn "Elasticsearch is taking longer than expected to start"
        warn "You can check its status manually with: curl http://localhost:9200/_cluster/health"
    fi

    # Wait for Kibana
    log "Waiting for Kibana..."
    local kibana_attempts=0
    local max_kibana_attempts=20

    while [ $kibana_attempts -lt $max_kibana_attempts ]; do
        if curl -s http://localhost:5601/api/status > /dev/null 2>&1; then
            log "Kibana is ready ✓"
            break
        fi

        kibana_attempts=$((kibana_attempts + 1))
        sleep 10
        echo -n "."
    done

    # Wait for Prometheus
    log "Waiting for Prometheus..."
    local prometheus_attempts=0
    local max_prometheus_attempts=15

    while [ $prometheus_attempts -lt $max_prometheus_attempts ]; do
        if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
            log "Prometheus is ready ✓"
            break
        fi

        prometheus_attempts=$((prometheus_attempts + 1))
        sleep 5
        echo -n "."
    done

    # Wait for Grafana
    log "Waiting for Grafana..."
    local grafana_attempts=0
    local max_grafana_attempts=15

    while [ $grafana_attempts -lt $max_grafana_attempts ]; do
        if curl -s http://localhost:3001/api/health > /dev/null 2>&1; then
            log "Grafana is ready ✓"
            break
        fi

        grafana_attempts=$((grafana_attempts + 1))
        sleep 5
        echo -n "."
    done

    log "Core services are healthy ✓"
}

# Initialize database
init_database() {
    log "Initializing database..."

    # Wait a bit more for PostgreSQL to be fully ready
    sleep 10

    # Check if database exists and is accessible
    if docker-compose exec -T postgres psql -U postgres -l | grep -q "ai-friend"; then
        log "Database 'ai-friend' exists ✓"
    else
        warn "Database 'ai-friend' does not exist, it will be created automatically"
    fi

    # Run a simple health check query
    if docker-compose exec -T postgres psql -U postgres -d ai-friend -c "SELECT 1;" > /dev/null 2>&1; then
        log "Database connection test passed ✓"
    else
        warn "Database connection test failed, tables will be created on first run"
    fi

    log "Database initialization completed ✓"
}

# Deploy application
deploy_app() {
    log "Starting deployment..."

    # Stop existing containers
    log "Stopping existing containers..."
    docker-compose down

    # Pull latest images
    log "Pulling latest images..."
    docker-compose pull

    # Build and start services
    log "Building and starting services..."
    docker-compose up --build -d

    # Wait for services
    wait_for_services

    # Initialize database
    init_database

    log "Deployment completed successfully! 🎉"
}

# Display deployment info
show_info() {
    echo ""
    log "=== DEPLOYMENT COMPLETED ==="
    echo ""
    log "📊 Monitoring URLs:"
    echo "   Grafana:      http://localhost:3001 (admin/admin)"
    echo "   Kibana:       http://localhost:5601"
    echo "   Prometheus:   http://localhost:9091"
    echo "   Bot Metrics:  http://localhost:8000/metrics"
    echo "   Elasticsearch: http://localhost:9200"
    echo ""
    log "🗄️  Database:"
    echo "   PostgreSQL:   localhost:5433"
    echo ""
    log "💾 Backup Scripts:"
    echo "   Manual backup:  ./backup/scripts/backup.sh"
    echo "   Restore:        ./backup/scripts/restore.sh"
    echo "   Auto backup:    ./backup/scripts/auto_backup.sh"
    echo ""
    log "🔧 Services Status:"
    docker-compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    log "📝 Next steps:"
    echo "   1. Check Kibana: Go to http://localhost:5601"
    echo "   2. Create index pattern: 'friend-bot-logs-*'"
    echo "   3. Check Grafana: http://localhost:3001 (admin/admin)"
    echo "   4. Test bot: Send /start to your Telegram bot"
    echo "   5. View logs: docker-compose logs -f bot"
    echo "   6. Setup backup cron: add './backup/scripts/auto_backup.sh' to crontab"
    echo ""
    log "🐛 Troubleshooting:"
    echo "   View logs: docker-compose logs [service-name]"
    echo "   Restart service: docker-compose restart [service-name]"
    echo "   Check health: curl http://localhost:9200/_cluster/health"
    echo "   Backup database: ./backup/scripts/backup.sh"
    echo ""
}

# Health check
health_check() {
    log "Running health checks..."

    echo ""
    log "Service Health Status:"
    echo "---------------------"

    # Check bot container
    if docker-compose ps bot | grep -q "Up"; then
        log "Bot service: ✓ Healthy"
    else
        error "Bot service: ✗ Unhealthy"
    fi

    # Check PostgreSQL
    if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
        log "PostgreSQL: ✓ Healthy"
    else
        error "PostgreSQL: ✗ Unhealthy"
    fi

    # Check Elasticsearch
    if curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then
        local es_status=$(curl -s http://localhost:9200/_cluster/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        log "Elasticsearch: ✓ Healthy (Status: $es_status)"
    else
        warn "Elasticsearch: ⚠️  Not responding"
    fi

    # Check Kibana
    if curl -s http://localhost:5601/api/status > /dev/null 2>&1; then
        log "Kibana: ✓ Healthy"
    else
        warn "Kibana: ⚠️  Starting..."
    fi

    # Check Prometheus
    if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
        log "Prometheus: ✓ Healthy"
    else
        warn "Prometheus: ⚠️  Not responding"
    fi

    # Check Grafana
    if curl -s http://localhost:3001/api/health > /dev/null 2>&1; then
        log "Grafana: ✓ Healthy"
    else
        warn "Grafana: ⚠️  Not responding"
    fi

    echo ""
}

# Main deployment function
main() {
    log "Starting Friend Bot + ELK Stack + Monitoring Deployment..."

    check_requirements
    create_directories
    create_logstash_config
    setup_elk
    create_db_init
    create_backup_script
    setup_monitoring
    deploy_app
    health_check
    show_info

    log "Deployment sequence completed! 🚀"
    log "Check the information above for next steps and troubleshooting."
}

# Run main function
main "$@"