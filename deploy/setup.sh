#!/bin/bash
# Math Game - VPS Deploy Script
# Usage: ssh root@server 'bash -s' < deploy/setup.sh
# Yoki serverda: bash setup.sh

set -e

DOMAIN="${1:?Usage: bash setup.sh YOUR_DOMAIN}"
APP_DIR="/opt/mathgame"

echo "=== Math Game Deploy ==="
echo "Domain: $DOMAIN"

# 1. System packages
echo ">>> Installing system packages..."
apt update
apt install -y python3 python3-venv python3-pip certbot python3-certbot-nginx

# 2. Create app directory
echo ">>> Setting up app directory..."
mkdir -p $APP_DIR
cp -r . $APP_DIR/ 2>/dev/null || echo "Run this from the project directory"

# 3. Python venv & dependencies
echo ">>> Setting up Python venv..."
cd $APP_DIR
python3 -m venv venv
$APP_DIR/venv/bin/pip install -r requirements.txt

# 4. .env file
if [ ! -f $APP_DIR/.env ]; then
    echo ">>> Creating .env file..."
    cat > $APP_DIR/.env << EOF
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
WEBAPP_URL=https://$DOMAIN
EOF
    echo "!!! EDIT .env file: nano $APP_DIR/.env"
else
    echo ">>> .env exists, updating WEBAPP_URL..."
    sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=https://$DOMAIN|" $APP_DIR/.env
fi

# 5. Permissions
chown -R www-data:www-data $APP_DIR

# 6. Nginx config
echo ">>> Configuring nginx..."
sed "s/YOUR_DOMAIN/$DOMAIN/g" $APP_DIR/deploy/nginx-mathgame.conf > /etc/nginx/sites-available/mathgame
ln -sf /etc/nginx/sites-available/mathgame /etc/nginx/sites-enabled/mathgame

# 7. SSL certificate
echo ">>> Getting SSL certificate..."
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email || {
    echo "!!! Certbot failed. Run manually: certbot --nginx -d $DOMAIN"
}

nginx -t && systemctl reload nginx

# 8. Systemd services
echo ">>> Setting up systemd services..."
cp $APP_DIR/deploy/mathgame-web.service /etc/systemd/system/
cp $APP_DIR/deploy/mathgame-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable mathgame-web mathgame-bot
systemctl restart mathgame-web mathgame-bot

echo ""
echo "=== DONE ==="
echo "1. Edit .env:  nano $APP_DIR/.env"
echo "2. Restart:    systemctl restart mathgame-web mathgame-bot"
echo "3. Logs:       journalctl -u mathgame-web -f"
echo "              journalctl -u mathgame-bot -f"
echo "4. Status:     systemctl status mathgame-web mathgame-bot"
