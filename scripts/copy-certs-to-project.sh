#!/bin/bash
#
# Скрипт для копирования SSL сертификатов из Docker volume в проект
# Запускать из папки проекта: ./scripts/copy-certs-to-project.sh

set -e

echo "=== Копирование SSL сертификатов ==="

# Создать папку для сертификатов
mkdir -p ./letsencrypt/live/siesh-ka.ru

# Скопировать сертификаты из volume
docker run --rm \
    -v sieshka-site_letsencrypt:/source:ro \
    -v $(pwd)/letsencrypt:/dest \
    alpine \
    sh -c "cp -r /source/live/* /dest/live/ 2>/dev/null || echo 'Live certs not found in volume'"

# Проверить что скопировалось
if [ -f "./letsencrypt/live/siesh-ka.ru/fullchain.pem" ]; then
    echo "✓ Сертификаты успешно скопированы"
    ls -la ./letsencrypt/live/siesh-ka.ru/
else
    echo "✗ Сертификаты не найдены в volume"
    echo "Проверяем структуру volume..."
    docker run --rm -v sieshka-site_letsencrypt:/certs alpine ls -laR /certs/
fi
