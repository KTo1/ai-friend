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
