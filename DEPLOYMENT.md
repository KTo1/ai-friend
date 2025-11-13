# Деплой Friend Bot с ELK стеком

## Требования
- Docker & Docker Compose
- 4GB+ RAM (рекомендуется 8GB для ELK)
- Linux/Ubuntu 20.04+

## Быстрый старт:

```bash
# 1. Клонируйте и перейдите в папку
git clone <your-repo>
cd ai-friend

# 2. Настройте .env файл
cp .env.example .env
nano .env  # Заполните TELEGRAM_BOT_TOKEN и другие переменные

# 3. Создайте необходимые директории
mkdir -p logs postgres/backups postgres/init elk/logstash

# 4. Создайте конфиг Logstash
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
  }

  # Удаляем поле message если оно дублирует content
  if [message] and [content] and [message] == [content] {
    mutate {
      remove_field => [ "message" ]
    }
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

# 5. Запустите деплой
chmod +x deploy.sh
./deploy.sh