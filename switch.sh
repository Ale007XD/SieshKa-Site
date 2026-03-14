#!/bin/bash
CONF="./nginx/upstream.runtime.conf"
NGINX_NAME="sieshka-site-nginx-1"

if grep -q "api-blue:8001" "$CONF"; then
    echo "Current: BLUE. Switching to GREEN..."
    echo "upstream api_backend { server sieshka-site-api-green-1:8002; }" > "$CONF"
else
    echo "Current: GREEN. Switching to BLUE..."
    echo "upstream api_backend { server sieshka-site-api-blue-1:8001; }" > "$CONF"
fi

docker exec $NGINX_NAME nginx -s reload
echo "Done! Traffic switched."