.PHONY: build up down logs logs-bot restart clean monitor

# Сборка образов
build:
	docker-compose build --no-cache

# Запуск сервисов
up:
	docker-compose up -d

# Остановка сервисов
down:
	docker-compose down

# Просмотр логов
logs:
	docker-compose logs -f

# Просмотр логов бота
logs-bot:
	docker-compose logs -f bot

# Перезапуск
restart: down up

# Очистка (внимание: удаляет данные!)
clean:
	docker-compose down -v
	docker system prune -f

# Мониторинг
monitor:
	@echo "📊 Services:"
	@docker-compose ps
	@echo ""
	@echo "🪵 Recent logs:"
	@docker-compose logs --tail=20

# Деплой
deploy: build up

# Проверка метрик
metrics:
	curl -s http://localhost:8000/metrics | head -20

# Миграция данных (если нужно)
migrate:
	docker-compose run --rm bot python migrate_sqlite_to_postgresql.py