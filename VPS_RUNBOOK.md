# VPS Runbook: Blue/Green Deployment

## Overview

Этот runbook описывает процесс ручного Blue/Green деплоя для Sieshka Food Delivery на VPS.

**Схема работы:**
- Два набора API контейнеров: `api_blue` (порт 8081) и `api_green` (порт 8082)
- Nginx проксирует трафик через переменную `$api_upstream`
- Переключение происходит через изменение `nginx/upstream.runtime.conf` и reload nginx
- База данных (PostgreSQL) и Redis общие для обоих цветов

## Быстрые команды

### 1. Проверить активный цвет

```bash
cat nginx/upstream.runtime.conf
# Output: set $api_upstream "api_green";
```

### 2. Деплой новой версии (автоматический скрипт)

```bash
cd ~/SieshKa-Site
./scripts/deploy-bluegreen.sh
```

### 3. Проверить статус

```bash
./scripts/deploy-bluegreen.sh status
```

### 4. Ручной откат

```bash
# Определить текущий цвет
CURRENT=$(grep -oP 'set \$api_upstream "\K[^"]+' nginx/upstream.runtime.conf)

# Переключить на другой цвет
if [ "$CURRENT" == "api_blue" ]; then
    echo 'set $api_upstream "api_green";' > nginx/upstream.runtime.conf
else
    echo 'set $api_upstream "api_blue";' > nginx/upstream.runtime.conf
fi

# Reload nginx
docker compose exec nginx nginx -s reload

# Проверить
curl -f https://siesh-ka.ru/health
```

## Пошаговый ручной деплой

### Шаг 1: Подготовка

```bash
cd ~/SieshKa-Site

# Проверить текущий цвет
cat nginx/upstream.runtime.conf
# ACTIVE=green (api_green), INACTIVE=blue (api_blue)

# Создать бэкап БД
mkdir -p backups/manual
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker compose exec -T db pg_dump -U food -d food > backups/manual/food_${TIMESTAMP}.sql

# Сохранить текущую ревизию Alembic
docker compose exec api_green alembic current > backups/manual/alembic_current.txt
```

### Шаг 2: Развертывание неактивного цвета (blue)

```bash
# Собрать и запустить api_blue
docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml up -d --build api_blue

# Ждать healthcheck (30-60 сек)
docker compose ps api_blue

# Smoke-test через порт 8081
curl -f http://127.0.0.1:8081/health
curl -f http://127.0.0.1:8081/api/slots?day=today&method=delivery
```

### Шаг 3: Миграции базы данных

```bash
# Применить миграции на новом цвете
docker compose exec api_blue alembic upgrade head

# Проверить версию
docker compose exec api_blue alembic current
```

### Шаг 4: Переключение трафика

```bash
# Обновить upstream
echo 'set $api_upstream "api_blue";' > nginx/upstream.runtime.conf

# Reload nginx (zero-downtime)
docker compose exec nginx nginx -s reload

# Проверить через production URL
curl -f https://siesh-ka.ru/health
curl -I https://siesh-ka.ru
# Должно показывать X-Upstream: api_blue
```

### Шаг 5: Пост-проверка

```bash
# Проверить логи нового цвета
docker compose logs api_blue --tail 50

# Проверить метрики
curl https://siesh-ka.ru/metrics | grep http_requests_total

# Если всё ок - остановить старый цвет
docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml stop api_green
```

## Откат (Rollback)

### Сценарий 1: Проблемы с кодом (быстрый откат)

```bash
# Просто переключаем upstream обратно
echo 'set $api_upstream "api_green";' > nginx/upstream.runtime.conf
docker compose exec nginx nginx -s reload

# Проверить
curl -f https://siesh-ka.ru/health
```

### Сценарий 2: Проблемы с миграциями

```bash
# 1. Переключить upstream обратно
echo 'set $api_upstream "api_green";' > nginx/upstream.runtime.conf
docker compose exec nginx nginx -s reload

# 2. Получить предыдущую ревизию из файла
PREV_REVISION=$(cat backups/manual/alembic_current.txt | grep -oP '^\w+')

# 3. Откатить миграции на неактивном цвете
docker compose exec api_blue alembic downgrade $PREV_REVISION

# 4. Остановить неактивный цвет
docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml stop api_blue
```

### Сценарий 3: Полный откат с восстановлением БД

```bash
# Только если миграции сломали данные!

# 1. Переключить upstream на рабочий цвет
echo 'set $api_upstream "api_green";' > nginx/upstream.runtime.conf
docker compose exec nginx nginx -s reload

# 2. Остановить ВСЕ API контейнеры
docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml stop api_blue api_green api

# 3. Восстановить БД из бэкапа
BACKUP_FILE=$(cat backups/manual/latest_backup.txt)
docker compose exec -T db psql -U food -d food < "$BACKUP_FILE"

# 4. Запустить проверенный цвет
docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml up -d api_green

# 5. Проверить
curl -f https://siesh-ka.ru/health
```

## Структура файлов

```
~/SieshKa-Site/
├── docker-compose.yml              # Базовая конфигурация
├── docker-compose.bluegreen.yml    # Blue/Green override
├── nginx/
│   ├── default.conf                # Nginx config с переменной upstream
│   ├── upstream.runtime.conf       # Runtime upstream (rw mount)
│   └── .htpasswd                   # Basic auth
├── scripts/
│   └── deploy-bluegreen.sh         # Скрипт автоматического деплоя
└── backups/manual/                 # Ручные бэкапы
    ├── food_YYYYMMDD_HHMMSS.sql
    ├── alembic_current.txt
    └── latest_backup.txt
```

## Переменные окружения

В `.env` должны быть:

```bash
# Для API контейнеров
DATABASE_URL=postgresql+psycopg://food:${POSTGRES_PASSWORD}@db:5432/food
REDIS_URL=redis://redis:6379/0
BASE_URL=https://siesh-ka.ru

# Для blue/green (опционально, для логирования)
DEPLOYMENT_COLOR=blue  # или green, автоматически выставляется в compose
```

## Health Checks

### API Health
```bash
curl http://127.0.0.1:8081/health  # blue
curl http://127.0.0.1:8082/health  # green
curl https://siesh-ka.ru/health     # production
```

### Nginx Config Test
```bash
docker compose exec nginx nginx -t
```

### Database Connection
```bash
docker compose exec db pg_isready -U food -d food
```

## Troubleshooting

### Проблема: Nginx не перезагружается
```bash
# Проверить синтаксис
docker compose exec nginx nginx -t

# Если ошибка - проверить upstream.runtime.conf
cat nginx/upstream.runtime.conf
# Должно быть: set $api_upstream "api_blue"; (или api_green)

# Принудительный reload
docker compose exec nginx nginx -s reload
```

### Проблема: Контейнер не стартует
```bash
# Логи
docker compose logs api_blue --tail 100

# Проверить env
docker compose exec api_blue env | grep -E '(DATABASE|REDIS)'

# Пересобрать
docker compose -f docker-compose.yml -f docker-compose.bluegreen.yml up -d --build --force-recreate api_blue
```

### Проблема: Миграции не применяются
```bash
# Проверить текущую версию
docker compose exec api_blue alembic current

# Проверить историю
docker compose exec api_blue alembic history

# Применить вручную
docker compose exec api_blue alembic upgrade head

# При ошибке - откат
docker compose exec api_blue alembic downgrade -1
```

### Проблема: Smoke-test не проходит
```bash
# Проверить, что порт проброшен
docker compose ps api_blue
# Должно показывать: 127.0.0.1:8081->8000/tcp

# Проверить изнутри контейнера
docker compose exec api_blue curl -f http://localhost:8000/health

# Проверить с хоста
curl -v http://127.0.0.1:8081/health
```

## Контакты и Escalation

- **Emergency rollback:** Переключить upstream файл и reload nginx
- **Database corruption:** Остановить все API, восстановить из бэкапа
- **SSL issues:** Проверить certbot, обновить сертификаты вручную

## Чек-лист перед деплоем

- [ ] Код протестирован локально
- [ ] Миграции проверены (`alembic history`)
- [ ] Бэкап БД создан
- [ ] Текущая ревизия Alembic сохранена
- [ ] Smoke-test скрипт проверен
- [ ] План отката готов

## Чек-лист после деплоя

- [ ] Production health check проходит
- [ ] Метрики собираются (`/metrics`)
- [ ] Логи без ошибок
- [ ] Старый цвет остановлен (опционально)
- [ ] Бэкап старого цвета сохранён на случай отката
