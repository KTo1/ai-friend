#!/bin/bash

# Скрипт деплоя Friend Bot

set -e

echo "🚀 Starting Friend Bot deployment..."

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration and run again."
    exit 1
fi

# Сборка и запуск
echo "🐳 Building and starting containers..."
docker-compose down
docker-compose build --no-cache
docker-compose up -d

echo "⏳ Waiting for services to start..."
sleep 30

# Проверка статуса сервисов
echo "🔍 Checking services status..."
docker-compose ps

# Проверка метрик
echo "📊 Checking metrics endpoint..."
curl -s http://localhost:8000/metrics | head -10

echo "✅ Deployment completed!"
echo ""
echo "📊 Access your services:"
echo "   - Bot Metrics: http://localhost:8000/metrics"
echo "   - Prometheus:  http://localhost:9090"
echo "   - Grafana:     http://localhost:3000 (admin/admin)"
echo "   - PostgreSQL:  localhost:5432"
echo ""
echo "🐳 To view logs: docker-compose logs -f bot"