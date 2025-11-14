#!/bin/bash

set -e

echo "🚀 Starting kibana setup ..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

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

# ФУНКЦИЯ: Ожидание готовности Kibana
wait_for_kibana() {
    log "Waiting for Kibana to be fully ready..."

    local MAX_ATTEMPTS=3
    local ATTEMPT=0

    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        if curl -s -f "http://localhost:5601/api/status" > /dev/null 2>&1; then
            local STATUS_RESPONSE=$(curl -s "http://localhost:5601/api/status")

            if echo "$STATUS_RESPONSE" | grep -q '"overall":{"level":"available"'; then
                log "Kibana is fully ready and available ✓"
                return 0
            else
                local CURRENT_STATUS=$(echo "$STATUS_RESPONSE" | grep -o '"overall":{"level":"[^"]*"' | head -1)
                info "Kibana API is responding but not fully ready. Status: $CURRENT_STATUS"
            fi
        else
            warn "Kibana API not accessible yet (attempt $((ATTEMPT + 1))/$MAX_ATTEMPTS)"
        fi

        ATTEMPT=$((ATTEMPT + 1))
        sleep 5
    done

    error "Kibana did not become ready after $MAX_ATTEMPTS attempts"
    return 1
}

# ФУНКЦИЯ: Создание Data View
setup_kibana_dataview() {
    log "Creating Kibana Data View..."

    local URL="http://localhost:5601/api/data_views/data_view"

    # ПРОСТОЙ JSON для создания Data View
    local PAYLOAD='{
        "data_view": {
            "title": "friend-bot-logs-*",
            "timeFieldName": "@timestamp"
        }
    }'

    local MAX_ATTEMPTS=3
    local ATTEMPT=0

    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
        info "Attempting to create Data View (attempt $((ATTEMPT + 1))/$MAX_ATTEMPTS)..."

        local RESPONSE=$(curl -s -X POST "$URL" \
            -H 'Content-Type: application/json' \
            -H 'kbn-xsrf: reporting' \
            -d "$PAYLOAD")

        if echo "$RESPONSE" | grep -q '"title":"friend-bot-logs-'; then
            log "Kibana Data View created successfully ✓"
            return 0
        elif echo "$RESPONSE" | grep -qi 'already exists\|duplicate'; then
            warn "Data View already exists ✓"
            return 0
        else
            warn "Attempt $((ATTEMPT + 1)) failed. Response: $RESPONSE"
        fi

        ATTEMPT=$((ATTEMPT + 1))
        sleep 3
    done

    error "Failed to create Data View"
    return 1
}

# ФУНКЦИЯ: Получение ID Data View
get_dataview_id() {
    log "Getting Data View ID..."

    local RESPONSE=$(curl -s "http://localhost:5601/api/data_views/data_view")
    local DATA_VIEW_ID=$(echo "$RESPONSE" | grep -o '"id":"[^"]*"' | grep "friend-bot-logs" | head -1 | cut -d'"' -f4)

    if [ -n "$DATA_VIEW_ID" ]; then
        info "Found Data View ID: $DATA_VIEW_ID"
        echo "$DATA_VIEW_ID"
        return 0
    else
        error "Could not find Data View ID"
        return 1
    fi
}

# ФУНКЦИЯ: Настройка подсветки через fieldFormats
setup_field_format() {
    log "Setting up field format for level highlighting..."

    local DATA_VIEW_ID=$(get_dataview_id)
    if [ -z "$DATA_VIEW_ID" ]; then
        error "Cannot setup field format without Data View ID"
        return 1
    fi

    local URL="http://localhost:5601/api/data_views/data_view/$DATA_VIEW_ID"

    # ПРОСТОЙ JSON для fieldFormats
    local PAYLOAD='{
        "data_view": {
            "fieldFormats": {
                "level": {
                    "id": "color",
                    "params": {
                        "fieldType": "string",
                        "colors": [
                            {
                                "value": "ERROR",
                                "background": "#ffcccc",
                                "text": "#cc0000"
                            },
                            {
                                "value": "WARNING",
                                "background": "#fff0cc",
                                "text": "#e6a700"
                            },
                            {
                                "value": "INFO",
                                "background": "#ccffcc",
                                "text": "#007c63"
                            }
                        ]
                    }
                }
            }
        }
    }'

    local RESPONSE=$(curl -s -X PUT "$URL" \
        -H 'Content-Type: application/json' \
        -H 'kbn-xsrf: reporting' \
        -d "$PAYLOAD")

    if echo "$RESPONSE" | grep -q '"fieldFormats"'; then
        log "Field format configured successfully ✓"
        return 0
    else
        warn "Field format configuration failed"
        return 1
    fi
}

# ФУНКЦИЯ: Создание простого сохраненного поиска
create_simple_search() {
    log "Creating simple saved search..."

    local URL="http://localhost:5601/api/saved_objects/search/friend-bot-search"

    # ПРОСТОЙ JSON для сохраненного поиска
    local PAYLOAD='{
        "attributes": {
            "title": "Friend Bot Logs",
            "columns": ["@timestamp", "level", "message"],
            "sort": ["@timestamp", "desc"]
        }
    }'

    local RESPONSE=$(curl -s -X POST "$URL" \
        -H 'Content-Type: application/json' \
        -H 'kbn-xsrf: reporting' \
        -d "$PAYLOAD")

    if echo "$RESPONSE" | grep -q '"type":"search"'; then
        log "Saved search created successfully ✓"
    else
        warn "Saved search already exists or creation failed"
    fi
}

# Main deployment function
main() {
    log "Starting Kibana setup..."

    # 1. Ждем готовности Kibana
    if ! wait_for_kibana; then
        error "Kibana is not ready"
        return 1
    fi

    # 2. Создаем Data View
    if ! setup_kibana_dataview; then
        error "Failed to create Data View"
        return 1
    fi

    # 3. Настраиваем field format для подсветки
    if ! setup_field_format; then
        warn "Field format setup failed - manual configuration required"
    fi

    # 4. Создаем простой сохраненный поиск
    create_simple_search

    log ""
    log "🎉 Kibana setup completed!"
    log ""
    log "=== NEXT STEPS ==="
    log "1. Open Discover: http://localhost:5601/app/discover"
    log "2. Select 'friend-bot-logs-*' data view"
    log "3. Look for colored level indicators"
    log ""
    log "If colors don't appear automatically:"
    log "1. Go to Stack Management > Data Views"
    log "2. Open 'friend-bot-logs-*'"
    log "3. Edit 'level' field and set format to 'Color'"
    log "4. Configure colors for ERROR, WARNING, INFO"
}

main "$@"