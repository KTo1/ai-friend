.PHONY: rebuild build build-с up down logs logs-bot restart clean monitor

export DOCKER_API_VERSION=1.44

rebuild:
    docker compose up -d --build --force-recreate --no-deps bot

# Сборка образов
build-с:
	docker compose build --no-cache

build:
	docker compose build

# Запуск сервисов
up:
	docker compose up -d

# Остановка сервисов
down:
	docker compose down

# Просмотр логов
logs:
	docker compose logs -f

# Просмотр логов бота
logs-bot:
	docker compose logs -f bot

# Перезапуск
restart: down up

# Очистка (внимание: удаляет данные!)
clean:
	docker compose down -v
	docker system prune -f

# Мониторинг
monitor:
	@echo "📊 Services:"
	@docker compose ps
	@echo ""
	@echo "🪵 Recent logs:"
	@docker compose logs --tail=20

# Деплой
deploy: build up

# Проверка метрик
metrics:
	curl -s http://localhost:8001/metrics | head -20

# Бэкап базы данных
backup:
	@echo "💾 Creating database backup..."
	@chmod +x postgres/backup.sh
	@./postgres/backup.sh

# Восстановление базы данных
restore:
	@echo "🔄 Restoring database..."
	@chmod +x postgres/restore.sh
	@./postgres/restore.sh

# Показать список бэкапов
backup-list:
	@echo "📁 Available backups:"
	@ls -lt postgres/backups/backup_*.sql 2>/dev/null || echo "No backups found"

# Очистить старые бэкапы (оставить последние 5)
backup-clean:
	@echo "🧹 Cleaning old backups..."
	@ls -t postgres/backups/backup_*.sql 2>/dev/null | tail -n +6 | xargs -r rm -v