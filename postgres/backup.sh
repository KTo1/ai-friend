#!/bin/bash
# ФИКС: Принудительно используем новый API
export DOCKER_API_VERSION=1.44

set -e
BACKUP_DIR="./backups"
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
