#!/usr/bin/env bash
set -euo pipefail

# install.sh - Bootstrap Accountinox on Ubuntu (MariaDB variant)
# Usage (run as root):
# sudo REPO_URL=<git-url> DOMAIN=<example.com> DB_CHOICE=mariadb DB_USER=acct DB_PASS=pass DB_NAME=accountinoxdb ./install.sh

: "${REPO_URL:?REPO_URL is required (e.g. https://github.com/user/repo.git)}"

APP_DIR="${APP_DIR:-/srv/accountinox}"
DOMAIN="${DOMAIN:-}"
DJANGO_USER="${DJANGO_USER:-www-data}"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR="$APP_DIR/.venv"
DB_CHOICE="${DB_CHOICE:-mariadb}"   # mariadb | postgres | mysql | none
DB_NAME="${DB_NAME:-accountinoxdb}"
DB_USER="${DB_USER:-accountinox}"
DB_PASS="${DB_PASS:-}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-}"
USE_REDIS="${USE_REDIS:-0}"
WORKERS="${WORKERS:-3}"

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root: sudo $0"
  exit 1
fi

echo "Installing Accountinox -> $APP_DIR (DB: $DB_CHOICE)"

apt_update_install() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git curl "$PYTHON_BIN" "${PYTHON_BIN}-venv" "${PYTHON_BIN}-dev" build-essential nginx openssl pkg-config libssl-dev libffi-dev
  # System libs for Pillow (image support)
  apt-get install -y libjpeg-dev zlib1g-dev libtiff5-dev libfreetype6-dev libwebp-dev libharfbuzz-dev libfribidi-dev || true
  if [ "$DB_CHOICE" = "postgres" ]; then
    apt-get install -y postgresql libpq-dev
  elif [ "$DB_CHOICE" = "mysql" ]; then
    apt-get install -y default-mysql-server default-libmysqlclient-dev
  elif [ "$DB_CHOICE" = "mariadb" ]; then
    apt-get install -y mariadb-server libmariadb-dev
  fi
  if [ "$USE_REDIS" = "1" ]; then
    apt-get install -y redis-server
  fi
  if [ -n "$DOMAIN" ]; then
    apt-get install -y certbot python3-certbot-nginx
  fi
}

create_dirs_and_user() {
  mkdir -p "$APP_DIR"
  chown "$SUDO_USER":"$SUDO_USER" "$APP_DIR" || true
  mkdir -p "$APP_DIR/logs" "$APP_DIR/media" "$APP_DIR/staticfiles"
}

clone_repo_and_venv() {
  # If the target is already a git clone, update it.
  if [ -d "$APP_DIR/.git" ]; then
    (cd "$APP_DIR" && git fetch --all && git reset --hard origin/HEAD) || true
  else
    # Clone into a temporary dir first to avoid git error when APP_DIR exists.
    TMPDIR=$(mktemp -d /tmp/accountinox.XXXX)
    git clone "$REPO_URL" "$TMPDIR"

    # If APP_DIR exists and is non-empty, move it to a backup before replacing.
    if [ -d "$APP_DIR" ] && [ "$(ls -A "$APP_DIR")" ]; then
      BACKUP="$APP_DIR.bak_$(date +%s)"
      echo "Backing up existing $APP_DIR -> $BACKUP"
      mv "$APP_DIR" "$BACKUP"
    else
      # Ensure parent exists for move
      mkdir -p "$(dirname "$APP_DIR")"
    fi

    mv "$TMPDIR" "$APP_DIR"
  fi

  if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  source "$VENV_DIR/bin/activate"
  pip install --upgrade pip setuptools wheel
  if [ -f "$APP_DIR/requirements.txt" ]; then
    pip install --no-cache-dir -r "$APP_DIR/requirements.txt"
  fi
  # Ensure PyJWT and Pillow are available for packages that import `jwt` and ImageField during app startup
  pip install --no-cache-dir PyJWT Pillow
  pip install --upgrade "gunicorn" "uvicorn[standard]" "django-environ"
  deactivate
}

generate_keys_and_write_env() {
  source "$VENV_DIR/bin/activate"
  DJANGO_SECRET_KEY="$("$VENV_DIR/bin/python" - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
)"
  FERNET_KEY="$("$VENV_DIR/bin/python" - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)"
  OTP_HMAC_KEY="$("$VENV_DIR/bin/python" - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  # If DB_PASS was not provided by the caller, generate a strong, URL-safe password
  if [ -z "${DB_PASS:-}" ]; then
    DB_PASS="$("$VENV_DIR/bin/python" - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
 )"
    echo "Generated secure DB password"
  fi
  deactivate

  ENVFILE="$APP_DIR/.env"
  cat > "$ENVFILE" <<EOF
DEBUG=0
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
ALLOWED_HOSTS=${DOMAIN:-localhost}
SITE_URL=${DOMAIN:-}
FERNET_KEY=${FERNET_KEY}
OTP_HMAC_KEY=${OTP_HMAC_KEY}
# REDIS_URL=redis://127.0.0.1:6379/0
EOF

  if [ "$DB_CHOICE" = "postgres" ]; then
    DB_PORT=${DB_PORT:-5432}
    echo "DATABASE_URL=postgres://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME" >> "$ENVFILE"
  elif [ "$DB_CHOICE" = "mysql" ] || [ "$DB_CHOICE" = "mariadb" ]; then
    DB_PORT=${DB_PORT:-3306}
    echo "DATABASE_URL=mysql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME" >> "$ENVFILE"
  fi

  chmod 600 "$ENVFILE"
  chown "$SUDO_USER":"$SUDO_USER" "$ENVFILE" || true
  echo ".env written to $ENVFILE"
}

provision_database() {
  if [ "$DB_CHOICE" = "postgres" ]; then
    systemctl enable --now postgresql || true
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DO \$do\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '$DB_USER') THEN CREATE USER $DB_USER WITH PASSWORD '$DB_PASS'; END IF; END \$do\$;" || true
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || true
  elif [ "$DB_CHOICE" = "mysql" ]; then
    systemctl enable --now mysql || true
    mysql -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`;"
    mysql -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS'; ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS'; GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost'; FLUSH PRIVILEGES;" || true
  elif [ "$DB_CHOICE" = "mariadb" ]; then
    systemctl enable --now mariadb || systemctl enable --now mysql || true
    mysql -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\`;"
    mysql -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS'; ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS'; GRANT ALL PRIVILEGES ON \`$DB_NAME\`.* TO '$DB_USER'@'localhost'; FLUSH PRIVILEGES;" || true
  else
    echo "DB_CHOICE=none — skipping DB provisioning"
  fi
}

django_migrate_collectstatic() {
  source "$VENV_DIR/bin/activate"
  cd "$APP_DIR"
  # Load environment variables from .env safely (don't `source` arbitrary content)
  ENVFILE="$APP_DIR/.env"
  if [ -f "$ENVFILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      # skip empty lines and comments
      case "$line" in
        ""|\#*) continue ;;
      esac
      key="${line%%=*}"
      value="${line#*=}"
      # Trim possible surrounding quotes from value
      value="${value%"}"; value="${value#"}"
      export "$key"="$value"
    done < "$ENVFILE"
  fi
  export DJANGO_SETTINGS_MODULE=config.settings
  "$VENV_DIR/bin/python" manage.py migrate --noinput
  "$VENV_DIR/bin/python" manage.py collectstatic --noinput
  deactivate
}

create_systemd_service() {
  SERVICE_FILE=/etc/systemd/system/accountinox.service
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Accountinox Django app
After=network.target

[Service]
User=$DJANGO_USER
Group=$DJANGO_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --bind 127.0.0.1:8000 --workers $WORKERS
Restart=always
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now accountinox
}

create_nginx_site() {
  NGINX_FILE=/etc/nginx/sites-available/accountinox
  cat > "$NGINX_FILE" <<EOF
server {
    listen 80;
    server_name ${DOMAIN:-_};

    location /static/ {
        alias $APP_DIR/staticfiles/;
        access_log off;
    }

    location /media/ {
        alias $APP_DIR/media/;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 120;
    }
}
EOF
  ln -sf "$NGINX_FILE" /etc/nginx/sites-enabled/accountinox
  nginx -t
  systemctl restart nginx
}

obtain_ssl() {
  if [ -n "$DOMAIN" ]; then
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN}" || true
  fi
}

fix_permissions() {
  chown -R "$DJANGO_USER":"$DJANGO_USER" "$APP_DIR"
  chmod -R u+rwX "$APP_DIR"
}

main() {
  apt_update_install
  create_dirs_and_user
  clone_repo_and_venv
  generate_keys_and_write_env
  provision_database
  django_migrate_collectstatic
  fix_permissions
  create_systemd_service
  create_nginx_site
  obtain_ssl
  echo "Done. Tail logs:"
  echo "  sudo journalctl -u accountinox -f"
  echo "  sudo tail -f /var/log/nginx/error.log"
  echo "To create superuser: source $VENV_DIR/bin/activate && python manage.py createsuperuser"
}

main "$@"
