#!/bin/bash
set -e

echo "=== Let's Encrypt Certificate Setup ==="
echo ""

# Check if DOMAIN is set
if [ -z "$DOMAIN" ]; then
    echo "Please set DOMAIN environment variable:"
    echo "export DOMAIN=siesh-ka.ru"
    echo "export EMAIL=your-email@example.com"
    exit 1
fi

if [ -z "$EMAIL" ]; then
    echo "Please set EMAIL environment variable:"
    echo "export EMAIL=your-email@example.com"
    exit 1
fi

echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo ""

# Step 1: Use temporary nginx config without HTTPS
echo "Step 1: Starting nginx without HTTPS..."
cp nginx/default.conf nginx/default.conf.backup
cp nginx/default.conf.temp nginx/default.conf

# Step 2: Start nginx
docker compose up -d nginx

echo "Waiting for nginx to start..."
sleep 5

# Step 3: Get certificates
echo ""
echo "Step 2: Obtaining SSL certificates from Let's Encrypt..."
docker compose run --rm certbot certonly \
    --webroot \
    -w /var/www/certbot \
    --email "$EMAIL" \
    -d "$DOMAIN" \
    --agree-tos \
    --no-eff-email

# Step 4: Restore original config with HTTPS
echo ""
echo "Step 3: Restoring HTTPS configuration..."
cp nginx/default.conf.backup nginx/default.conf

# Step 5: Restart nginx
echo ""
echo "Step 4: Restarting nginx with HTTPS..."
docker compose restart nginx

echo ""
echo "=== Setup complete! ==="
echo "Your site should now be accessible via https://$DOMAIN"
echo ""
echo "To test certificate renewal:"
echo "  docker compose run --rm certbot renew --dry-run"
