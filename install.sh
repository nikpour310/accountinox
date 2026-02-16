#!/usr/bin/env bash
###############################################################################
#  Accountinox — Production Deployment Script
#  Target OS : Ubuntu 22.04 LTS (Jammy Jellyfish)
#  Usage     : sudo bash install.sh            (interactive)
#              sudo ENV_VAR=val bash install.sh (non-interactive)
#
#  Required env: REPO_URL
#  Optional env: DOMAIN, DB_CHOICE, DB_USER, DB_PASS, DB_NAME, DB_HOST,
#                DB_PORT, USE_REDIS, APP_DIR, WORKERS, PYTHON_VER
###############################################################################
set -Eeuo pipefail
IFS=$'\n\t'

# ─── Trap: clean up on error ────────────────────────────────────────────────
cleanup() {
  local ec=$?
  if [[ $ec -ne 0 ]]; then
    echo -e "\n${RED}✗ Installation failed (exit $ec). Check above for details.${NC}"
    echo -e "  Partial logs may be in: ${APP_DIR:-/srv/accountinox}/logs/"
  fi
}
trap cleanup EXIT

# ─── Colors & helpers ────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "${CYAN}▸${NC} $*"; }
success() { echo -e "${GREEN}✔${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
fail()    { echo -e "${RED}✗${NC} $*" >&2; exit 1; }
banner()  {
  echo ""
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BOLD}  $*${NC}"
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}
step() { echo -e "\n${DIM}$(date '+%H:%M:%S')${NC} ${BOLD}$*${NC}"; }

SECONDS=0   # built-in timer

# ─── Pre-flight checks ──────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || fail "Run as root:  sudo bash $0"
[[ -f /etc/lsb-release ]] && source /etc/lsb-release
if [[ "${DISTRIB_ID:-}" != "Ubuntu" ]]; then
  warn "This script targets Ubuntu 22.04. Detected: ${DISTRIB_DESCRIPTION:-unknown}"
fi

: "${REPO_URL:?REPO_URL is required  (e.g. https://github.com/user/repo.git)}"

# ─── Configuration ───────────────────────────────────────────────────────────
APP_NAME="accountinox"
APP_DIR="${APP_DIR:-/srv/${APP_NAME}}"
DOMAIN="${DOMAIN:-}"
PYTHON_VER="${PYTHON_VER:-3.11}"
PYTHON_BIN="python${PYTHON_VER}"
VENV_DIR="${APP_DIR}/.venv"
SERVICE_USER="${SERVICE_USER:-accountinox}"
DB_CHOICE="${DB_CHOICE:-mariadb}"       # mariadb | postgres | mysql | sqlite
DB_NAME="${DB_NAME:-accountinoxdb}"
DB_USER="${DB_USER:-accountinox}"
DB_PASS="${DB_PASS:-}"                  # auto-generated if empty
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-}"
USE_REDIS="${USE_REDIS:-1}"
WORKERS="${WORKERS:-0}"                 # 0 = auto-detect
ENABLE_FIREWALL="${ENABLE_FIREWALL:-1}"
SWAP_SIZE_MB="${SWAP_SIZE_MB:-0}"       # 0 = auto (1G if RAM ≤ 2G)

# ─── Detect fresh install vs update ──────────────────────────────────────────
ENVFILE="$APP_DIR/.env"
IS_UPDATE=0
if [[ -d "$APP_DIR/.git" && -f "$ENVFILE" ]]; then
  IS_UPDATE=1
  info "Detected existing installation — running in ${BOLD}UPDATE${NC} mode"
  info "Database and .env will be preserved"
fi

# ─── Auto-tune workers ──────────────────────────────────────────────────────
if [[ "$WORKERS" -eq 0 ]]; then
  CPU_COUNT=$(nproc 2>/dev/null || echo 1)
  WORKERS=$(( CPU_COUNT * 2 + 1 ))
  [[ $WORKERS -gt 9 ]] && WORKERS=9    # cap for memory safety
fi

###############################################################################
#                            PHASE 1 — SYSTEM                                #
###############################################################################
phase_system() {
  banner "Phase 1 / 7 — System Preparation"

  step "Updating package index"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq

  step "Installing base packages"
  apt-get install -y -qq --no-install-recommends \
    git curl wget ca-certificates gnupg lsb-release \
    "$PYTHON_BIN" "${PYTHON_BIN}-venv" "${PYTHON_BIN}-dev" \
    build-essential pkg-config libssl-dev libffi-dev \
    libjpeg-dev zlib1g-dev libtiff5-dev libfreetype6-dev \
    libwebp-dev libharfbuzz-dev libfribidi-dev \
    nginx openssl logrotate fail2ban ufw htop ncdu jq rsync \
    >/dev/null 2>&1
  success "Base packages installed"

  # ── Database client/server libs ──
  case "$DB_CHOICE" in
    mariadb)
      apt-get install -y -qq mariadb-server libmariadb-dev >/dev/null 2>&1
      success "MariaDB installed" ;;
    mysql)
      apt-get install -y -qq default-mysql-server default-libmysqlclient-dev >/dev/null 2>&1
      success "MySQL installed" ;;
    postgres)
      apt-get install -y -qq postgresql libpq-dev >/dev/null 2>&1
      success "PostgreSQL installed" ;;
    sqlite) info "Using SQLite — no extra packages needed" ;;
    *) fail "Unsupported DB_CHOICE: $DB_CHOICE" ;;
  esac

  # ── Redis ──
  if [[ "$USE_REDIS" == "1" ]]; then
    apt-get install -y -qq redis-server >/dev/null 2>&1
    # Memory optimisation: set maxmemory policy
    if [[ -f /etc/redis/redis.conf ]]; then
      sed -i 's/^# maxmemory-policy.*/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
    fi
    systemctl enable --now redis-server >/dev/null 2>&1
    success "Redis installed & tuned"
  fi

  # ── Certbot ──
  if [[ -n "$DOMAIN" ]]; then
    apt-get install -y -qq certbot python3-certbot-nginx >/dev/null 2>&1
    success "Certbot installed"
  fi

  # ── Swap (low-RAM servers) ──
  if [[ "$SWAP_SIZE_MB" -eq 0 ]]; then
    TOTAL_RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
    [[ $TOTAL_RAM_MB -le 2048 ]] && SWAP_SIZE_MB=1024
  fi
  if [[ "$SWAP_SIZE_MB" -gt 0 ]] && [[ ! -f /swapfile ]]; then
    info "Creating ${SWAP_SIZE_MB}MB swap"
    fallocate -l "${SWAP_SIZE_MB}M" /swapfile
    chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl -w vm.swappiness=10 >/dev/null
    grep -q 'vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
    success "Swap enabled (${SWAP_SIZE_MB}MB, swappiness=10)"
  fi
}

###############################################################################
#                         PHASE 2 — SERVICE USER                             #
###############################################################################
phase_user() {
  banner "Phase 2 / 7 — Service User & Directories"

  if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir "$APP_DIR" "$SERVICE_USER"
    success "Created system user: $SERVICE_USER"
  else
    info "User $SERVICE_USER already exists"
  fi

  mkdir -p "$APP_DIR"/{logs,media,staticfiles,backups}
  chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
  success "Directories ready"
}

###############################################################################
#                       PHASE 3 — CODE & VIRTUALENV                          #
###############################################################################
phase_code() {
  banner "Phase 3 / 7 — Source Code & Python Environment"

  step "Fetching source code"
  if [[ -d "$APP_DIR/.git" ]]; then
    info "Existing repo detected — pulling latest"
    cd "$APP_DIR"
    git fetch --all --quiet 2>/dev/null
    git reset --hard origin/HEAD --quiet 2>/dev/null || git reset --hard origin/main --quiet 2>/dev/null
  else
    TMPDIR=$(mktemp -d)
    git clone --depth 1 "$REPO_URL" "$TMPDIR" 2>/dev/null
    # Preserve existing persistent dirs
    for dir in media backups logs .venv; do
      if [[ -d "$APP_DIR/$dir" ]]; then
        cp -a "$APP_DIR/$dir" "$TMPDIR/$dir" 2>/dev/null || true
      fi
    done
    rsync -a --delete \
      --exclude='.venv' --exclude='media' --exclude='backups' --exclude='logs' --exclude='.env' \
      "$TMPDIR/" "$APP_DIR/"
    rm -rf "$TMPDIR"
  fi
  chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
  success "Source code ready"

  step "Building virtual environment"
  if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi

  source "$VENV_DIR/bin/activate"
  pip install -q --upgrade pip setuptools wheel 2>/dev/null

  if [[ -f "$APP_DIR/requirements.txt" ]]; then
    pip install -q --no-cache-dir -r "$APP_DIR/requirements.txt" 2>/dev/null
  fi

  # Runtime essentials
  pip install -q --no-cache-dir \
    gunicorn 'uvicorn[standard]' PyJWT Pillow django-environ 2>/dev/null

  if [[ "$USE_REDIS" == "1" ]]; then
    pip install -q --no-cache-dir django-redis 2>/dev/null
  fi

  deactivate
  chown -R "$SERVICE_USER":"$SERVICE_USER" "$VENV_DIR"
  success "Virtual environment ready ($(${VENV_DIR}/bin/python --version 2>&1))"
}

###############################################################################
#                       PHASE 4 — DATABASE                                   #
###############################################################################
phase_database() {
  banner "Phase 4 / 7 — Database"

  DB_URL=""

  # ── On UPDATE: read existing DB_PASS from .env so we don't break the connection ──
  if [[ $IS_UPDATE -eq 1 && -z "$DB_PASS" && "$DB_CHOICE" != "sqlite" ]]; then
    local existing_url
    existing_url=$(grep -E '^DATABASE_URL=' "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2-)
    if [[ -n "$existing_url" ]]; then
      # Extract password from URL: scheme://user:PASS@host:port/db
      DB_PASS=$(echo "$existing_url" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
      DB_USER=$(echo "$existing_url" | sed -n 's|.*://\([^:]*\):.*|\1|p')
      DB_NAME=$(echo "$existing_url" | sed -n 's|.*/\([^?]*\).*|\1|p')
      if [[ -n "$DB_PASS" ]]; then
        info "Using existing database credentials from .env"
      fi
    fi
  fi

  # Generate DB password ONLY for fresh installs
  if [[ -z "$DB_PASS" ]] && [[ "$DB_CHOICE" != "sqlite" ]]; then
    DB_PASS=$("$VENV_DIR/bin/python" -c "import secrets; print(secrets.token_urlsafe(32))")
    info "Generated secure database password"
  fi

  case "$DB_CHOICE" in
    mariadb|mysql)
      local svc
      [[ "$DB_CHOICE" == "mariadb" ]] && svc="mariadb" || svc="mysql"
      systemctl enable --now "$svc" >/dev/null 2>&1 || systemctl enable --now mysql >/dev/null 2>&1

      mysql -e "CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" 2>/dev/null
      mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';" 2>/dev/null || true
      if [[ $IS_UPDATE -eq 0 ]]; then
        mysql -e "ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';" 2>/dev/null || true
      fi
      mysql -e "GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';" 2>/dev/null
      mysql -e "FLUSH PRIVILEGES;" 2>/dev/null

      DB_PORT="${DB_PORT:-3306}"
      DB_URL="mysql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
      success "${DB_CHOICE} database $([[ $IS_UPDATE -eq 1 ]] && echo 'verified' || echo 'provisioned')"
      ;;

    postgres)
      systemctl enable --now postgresql >/dev/null 2>&1
      if [[ $IS_UPDATE -eq 0 ]]; then
        sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
          "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_user WHERE usename='${DB_USER}') THEN CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}'; END IF; END \$\$;" 2>/dev/null
        sudo -u postgres createdb -O "$DB_USER" "$DB_NAME" 2>/dev/null || true
      fi

      DB_PORT="${DB_PORT:-5432}"
      DB_URL="postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
      success "PostgreSQL database $([[ $IS_UPDATE -eq 1 ]] && echo 'verified' || echo 'provisioned')"
      ;;

    sqlite)
      success "Using SQLite (file-based)"
      ;;
  esac
}

###############################################################################
#                    PHASE 5 — ENV + DJANGO SETUP                            #
###############################################################################
phase_django() {
  banner "Phase 5 / 7 — Environment & Django Setup"

  source "$VENV_DIR/bin/activate"

  # ── UPDATE MODE: preserve existing .env, only update DATABASE_URL & domain ──
  if [[ $IS_UPDATE -eq 1 && -f "$ENVFILE" ]]; then
    step "Updating existing .env (preserving all settings)"
    cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
    info "Backed up existing .env"

    # Update DATABASE_URL if it changed
    if [[ -n "${DB_URL:-}" ]]; then
      if grep -qE '^DATABASE_URL=' "$ENVFILE"; then
        sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DB_URL}|" "$ENVFILE"
      else
        echo "" >> "$ENVFILE"
        echo "DATABASE_URL=${DB_URL}" >> "$ENVFILE"
      fi
    fi

    # Update domain if explicitly provided
    if [[ -n "$DOMAIN" ]]; then
      sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=${DOMAIN},www.${DOMAIN}|" "$ENVFILE" 2>/dev/null || true
      sed -i "s|^SITE_URL=.*|SITE_URL=https://${DOMAIN}|" "$ENVFILE" 2>/dev/null || true
      sed -i "s|^SITE_BASE_URL=.*|SITE_BASE_URL=https://${DOMAIN}|" "$ENVFILE" 2>/dev/null || true
      sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://${DOMAIN},https://www.${DOMAIN}|" "$ENVFILE" 2>/dev/null || true
    fi

    chmod 600 "$ENVFILE"
    chown "$SERVICE_USER":"$SERVICE_USER" "$ENVFILE"
    success ".env preserved & updated"

  # ── FRESH INSTALL: generate new .env ──
  else
    step "Generating cryptographic keys"

    DJANGO_SECRET_KEY=$("$VENV_DIR/bin/python" -c \
      "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    FERNET_KEY=$("$VENV_DIR/bin/python" -c \
      "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    OTP_HMAC_KEY=$("$VENV_DIR/bin/python" -c \
      "import secrets; print(secrets.token_hex(32))")

    cat > "$ENVFILE" <<ENVEOF
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Accountinox — Production Environment
#  Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DEBUG=0
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
ALLOWED_HOSTS=${DOMAIN:-localhost},www.${DOMAIN:-localhost}
SITE_URL=https://${DOMAIN:-localhost}
SITE_BASE_URL=https://${DOMAIN:-localhost}

# ─── Security Keys ───
FERNET_KEY=${FERNET_KEY}
OTP_HMAC_KEY=${OTP_HMAC_KEY}
ENVEOF

    # Database URL
    if [[ -n "${DB_URL:-}" ]]; then
      echo "" >> "$ENVFILE"
      echo "# ─── Database ───" >> "$ENVFILE"
      echo "DATABASE_URL=${DB_URL}" >> "$ENVFILE"
    fi

    # Redis
    if [[ "$USE_REDIS" == "1" ]]; then
      cat >> "$ENVFILE" <<ENVEOF

# ─── Cache ───
REDIS_URL=redis://127.0.0.1:6379/0
ENVEOF
    fi

    cat >> "$ENVFILE" <<ENVEOF

# ─── SSL / Security ───
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https
CSRF_TRUSTED_ORIGINS=https://${DOMAIN:-localhost},https://www.${DOMAIN:-localhost}

# ─── Email (configure for production) ───
# EMAIL_HOST=smtp.example.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_HOST_USER=
# EMAIL_HOST_PASSWORD=
# DEFAULT_FROM_EMAIL=noreply@${DOMAIN:-localhost}

# ─── Optional ───
# SENTRY_DSN=
# SENTRY_ENVIRONMENT=production
# GOOGLE_CLIENT_ID=
# GOOGLE_SECRET=
# IPPANEL_API_KEY=
# IPPANEL_SENDER=
# IPPANEL_PATTERN_CODE=
ENVEOF

    chmod 600 "$ENVFILE"
    chown "$SERVICE_USER":"$SERVICE_USER" "$ENVFILE"
    success ".env written"
  fi

  step "Running migrations"
  cd "$APP_DIR"
  export DJANGO_SETTINGS_MODULE=config.settings
  # Source .env safely
  set -a
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    export "$key"="$value"
  done < "$ENVFILE"
  set +a

  sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" manage.py migrate --noinput 2>&1 | tail -5
  success "Migrations complete"

  step "Collecting static files"
  sudo -u "$SERVICE_USER" "$VENV_DIR/bin/python" manage.py collectstatic --noinput --clear 2>&1 | tail -1
  success "Static files collected"

  deactivate
}

###############################################################################
#                    PHASE 6 — SYSTEMD + NGINX + SSL                         #
###############################################################################
phase_services() {
  banner "Phase 6 / 7 — Services (systemd + Nginx + SSL)"

  # ── Gunicorn systemd service ──
  step "$([[ $IS_UPDATE -eq 1 ]] && echo 'Updating' || echo 'Creating') systemd service"
  cat > /etc/systemd/system/${APP_NAME}.service <<SVCEOF
[Unit]
Description=Accountinox ASGI Server
After=network.target${USE_REDIS:+ redis-server.service}
Wants=network-online.target

[Service]
Type=exec
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings

ExecStart=${VENV_DIR}/bin/gunicorn config.asgi:application \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers ${WORKERS} \
    --bind 127.0.0.1:8000 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile ${APP_DIR}/logs/access.log \
    --error-logfile ${APP_DIR}/logs/gunicorn.log \
    --log-level warning

ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

# ── Hardening ──
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/logs ${APP_DIR}/media ${APP_DIR}/db.sqlite3
LimitNOFILE=65536
LimitNPROC=512
OOMScoreAdjust=-100

[Install]
WantedBy=multi-user.target
SVCEOF

  systemctl daemon-reload
  systemctl enable ${APP_NAME}.service >/dev/null 2>&1
  systemctl restart ${APP_NAME}.service || warn "Service start failed — check: journalctl -u ${APP_NAME} -n 30"
  success "Systemd service active"

  # ── Nginx ──
  step "Configuring Nginx"

  # Global Nginx tuning
  if ! grep -q 'worker_connections 2048' /etc/nginx/nginx.conf 2>/dev/null; then
    sed -i 's/worker_connections [0-9]*/worker_connections 2048/' /etc/nginx/nginx.conf 2>/dev/null || true
  fi

  cat > /etc/nginx/sites-available/${APP_NAME} <<'NGXHEAD'
# ━━━━ Accountinox Nginx Config ━━━━

upstream accountinox_backend {
    server 127.0.0.1:8000 fail_timeout=0;
    keepalive 32;
}

limit_req_zone $binary_remote_addr zone=login:10m rate=5r/s;
limit_req_zone $binary_remote_addr zone=api:10m   rate=30r/s;

NGXHEAD

  if [[ -n "$DOMAIN" ]]; then
    cat >> /etc/nginx/sites-available/${APP_NAME} <<NGXEOF
server {
    listen 80;
    listen [::]:80;
    server_name www.${DOMAIN};
    return 301 https://${DOMAIN}\$request_uri;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
NGXEOF
  else
    cat >> /etc/nginx/sites-available/${APP_NAME} <<'NGXEOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
NGXEOF
  fi

  cat >> /etc/nginx/sites-available/${APP_NAME} <<NGXEOF

    charset utf-8;
    client_max_body_size 20M;

    # ── Security headers ──
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    # ── Gzip compression ──
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_comp_level 5;
    gzip_types
        text/plain text/css application/json application/javascript
        text/xml application/xml application/xml+rss text/javascript
        image/svg+xml font/woff2 application/font-woff;

    # ── Static files (immutable cache) ──
    location /static/ {
        alias ${APP_DIR}/staticfiles/;
        expires 365d;
        add_header Cache-Control "public, immutable";
        access_log off;
        tcp_nodelay on;
        open_file_cache max=3000 inactive=120s;
        open_file_cache_valid 45s;
        open_file_cache_min_uses 2;
    }

    # ── Media files ──
    location /media/ {
        alias ${APP_DIR}/media/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;

        # Block executable uploads
        location ~* \.(php|py|sh|pl|cgi)$ { deny all; }
    }

    # ── Favicon / robots ──
    location = /favicon.ico { access_log off; log_not_found off; }

    # ── Health check (monitoring) ──
    location = /healthz/ {
        proxy_pass http://accountinox_backend;
        proxy_set_header Host \$host;
        access_log off;
    }

    # ── Login rate limiting ──
    location ~ ^/(accounts/login|admin/login) {
        limit_req zone=login burst=10 nodelay;
        limit_req_status 429;
        proxy_pass http://accountinox_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # ── Main application proxy ──
    location / {
        proxy_pass http://accountinox_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        proxy_buffering on;
        proxy_buffer_size 8k;
        proxy_buffers 16 8k;
    }

    # ── Block dotfiles (.git, .env, etc.) ──
    location ~ /\. { deny all; access_log off; log_not_found off; }
}
NGXEOF

  rm -f /etc/nginx/sites-enabled/default
  ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/${APP_NAME}

  nginx -t 2>&1 | head -2
  systemctl enable --now nginx >/dev/null 2>&1
  systemctl reload nginx
  success "Nginx configured & reloaded"

  # ── SSL ──
  if [[ -n "$DOMAIN" ]]; then
    if [[ -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
      info "SSL certificate already exists for ${DOMAIN}"
      certbot renew --dry-run 2>/dev/null && success "SSL certificate valid" || warn "SSL renewal check failed"
    else
      step "Obtaining SSL certificate"
      certbot --nginx -d "$DOMAIN" -d "www.${DOMAIN}" \
        --non-interactive --agree-tos -m "admin@${DOMAIN}" \
        --redirect 2>&1 | tail -3 || warn "Certbot failed — configure SSL manually"
    fi
    systemctl enable --now certbot.timer 2>/dev/null || true
    success "SSL configured with auto-renewal"
  fi
}

###############################################################################
#                     PHASE 7 — HARDENING & HOUSEKEEPING                     #
###############################################################################
phase_harden() {
  banner "Phase 7 / 7 — Security Hardening"

  # ── Firewall ──
  if [[ "$ENABLE_FIREWALL" == "1" ]]; then
    step "Configuring UFW firewall"
    ufw default deny incoming >/dev/null 2>&1
    ufw default allow outgoing >/dev/null 2>&1
    ufw allow ssh >/dev/null 2>&1
    ufw allow 'Nginx Full' >/dev/null 2>&1
    echo "y" | ufw enable >/dev/null 2>&1
    success "Firewall active (SSH + HTTP/S only)"
  fi

  # ── Fail2Ban ──
  step "Configuring Fail2Ban"
  cat > /etc/fail2ban/jail.d/${APP_NAME}.conf <<F2BEOF
[sshd]
enabled  = true
port     = ssh
maxretry = 5
bantime  = 3600
findtime = 600

[nginx-http-auth]
enabled  = true
port     = http,https
maxretry = 5
bantime  = 3600

[nginx-limit-req]
enabled  = true
port     = http,https
logpath  = /var/log/nginx/error.log
maxretry = 10
bantime  = 600
F2BEOF
  systemctl enable --now fail2ban >/dev/null 2>&1
  systemctl restart fail2ban >/dev/null 2>&1
  success "Fail2Ban configured"

  # ── Log rotation ──
  step "Setting up log rotation"
  cat > /etc/logrotate.d/${APP_NAME} <<LREOF
${APP_DIR}/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 ${SERVICE_USER} ${SERVICE_USER}
    sharedscripts
    postrotate
        systemctl reload ${APP_NAME} 2>/dev/null || true
    endscript
}
LREOF
  success "Log rotation configured (14 days)"

  # ── Kernel tuning ──
  step "Applying sysctl optimisations"
  cat > /etc/sysctl.d/99-${APP_NAME}.conf <<SYSEOF
# ── Network ──
net.core.somaxconn = 4096
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.core.netdev_max_backlog = 4096
net.ipv4.ip_local_port_range = 1024 65535

# ── File descriptors ──
fs.file-max = 65536

# ── Memory (low-footprint) ──
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5
SYSEOF
  sysctl --system >/dev/null 2>&1
  success "Kernel parameters tuned"

  # ── Disable unused services ──
  for svc in snapd.service snapd.socket cups cups-browsed avahi-daemon bluetooth; do
    systemctl disable --now "$svc" 2>/dev/null || true
  done
  info "Disabled unused services for lower memory usage"

  # ── Cron: daily DB backup ──
  step "Setting up automated daily backup"
  CRON_CMD=""
  case "$DB_CHOICE" in
    mariadb|mysql)
      CRON_CMD="0 3 * * * mysqldump --single-transaction -u ${DB_USER} -p'${DB_PASS}' ${DB_NAME} | gzip > ${APP_DIR}/backups/db_\$(date +\%Y\%m\%d_\%H\%M).sql.gz && find ${APP_DIR}/backups -name 'db_*.sql.gz' -mtime +7 -delete"
      ;;
    postgres)
      CRON_CMD="0 3 * * * PGPASSWORD='${DB_PASS}' pg_dump -U ${DB_USER} -h ${DB_HOST} ${DB_NAME} | gzip > ${APP_DIR}/backups/db_\$(date +\%Y\%m\%d_\%H\%M).sql.gz && find ${APP_DIR}/backups -name 'db_*.sql.gz' -mtime +7 -delete"
      ;;
    sqlite)
      CRON_CMD="0 3 * * * cp ${APP_DIR}/db.sqlite3 ${APP_DIR}/backups/db_\$(date +\%Y\%m\%d_\%H\%M).sqlite3 && find ${APP_DIR}/backups -name 'db_*.sqlite3' -mtime +7 -delete"
      ;;
  esac
  if [[ -n "$CRON_CMD" ]]; then
    (crontab -l 2>/dev/null | grep -v "${APP_NAME}_backup"; echo "# ${APP_NAME}_backup"; echo "$CRON_CMD") | crontab -
    success "Daily backup at 03:00 (7-day retention)"
  fi

  # ── Final permissions ──
  step "Locking down permissions"
  chown -R "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR"
  chmod -R u=rwX,g=rX,o= "$APP_DIR"
  chmod 600 "$APP_DIR/.env"
  success "Permissions secured"
}

###############################################################################
#                           SUMMARY                                          #
###############################################################################
print_summary() {
  local elapsed_min=$(( SECONDS / 60 ))
  local elapsed_sec=$(( SECONDS % 60 ))

  # Gather live status
  local svc_status
  svc_status=$(systemctl is-active ${APP_NAME} 2>/dev/null || echo "unknown")
  local nginx_status
  nginx_status=$(systemctl is-active nginx 2>/dev/null || echo "unknown")
  local redis_status="disabled"
  [[ "$USE_REDIS" == "1" ]] && redis_status=$(systemctl is-active redis-server 2>/dev/null || echo "unknown")
  local db_status="n/a"
  case "$DB_CHOICE" in
    mariadb)  db_status=$(systemctl is-active mariadb 2>/dev/null || echo "unknown") ;;
    mysql)    db_status=$(systemctl is-active mysql 2>/dev/null || echo "unknown") ;;
    postgres) db_status=$(systemctl is-active postgresql 2>/dev/null || echo "unknown") ;;
    sqlite)   db_status="file" ;;
  esac

  local py_ver
  py_ver=$("${VENV_DIR}/bin/python" --version 2>&1 | awk '{print $2}')
  local disk_used
  disk_used=$(du -sh "$APP_DIR" 2>/dev/null | awk '{print $1}')
  local ram_free
  ram_free=$(free -h | awk '/^Mem:/{print $7}')

  echo ""
  echo ""
  echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║                                                                  ║${NC}"
  if [[ $IS_UPDATE -eq 1 ]]; then
  echo -e "${GREEN}║${NC}     ${BOLD}✔  ACCOUNTINOX — UPDATE COMPLETE${NC}                            ${GREEN}║${NC}"
  else
  echo -e "${GREEN}║${NC}     ${BOLD}✔  ACCOUNTINOX — DEPLOYMENT COMPLETE${NC}                        ${GREEN}║${NC}"
  fi
  echo -e "${GREEN}║                                                                  ║${NC}"
  echo -e "${GREEN}╠══════════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Services${NC}                                                        ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ App (gunicorn)  : $(colorize_status "$svc_status")                                   ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ Nginx           : $(colorize_status "$nginx_status")                                   ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ Database        : $(colorize_status "$db_status") (${DB_CHOICE})                          ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  └─ Redis           : $(colorize_status "$redis_status")                                   ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Configuration${NC}                                                   ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ Directory       : ${CYAN}${APP_DIR}${NC}                                ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ Python          : ${CYAN}${py_ver}${NC}                                          ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ Workers         : ${CYAN}${WORKERS}${NC} (ASGI/Uvicorn)                              ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ├─ Disk usage      : ${CYAN}${disk_used}${NC}                                        ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  └─ Free RAM        : ${CYAN}${ram_free}${NC}                                       ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  if [[ -n "$DOMAIN" ]]; then
  echo -e "${GREEN}║${NC}  ${BOLD}URL${NC} : ${CYAN}https://${DOMAIN}${NC}                                      ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  fi
  echo -e "${GREEN}║${NC}  ${BOLD}Duration${NC} : ${elapsed_min}m ${elapsed_sec}s                                          ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}╠══════════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${YELLOW}NEXT STEPS:${NC}                                                     ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}1.${NC} Create superuser:                                             ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}     ${DIM}sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/python \\${NC}    ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}     ${DIM}  ${APP_DIR}/manage.py createsuperuser${NC}            ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}2.${NC} Configure email settings in: ${CYAN}${APP_DIR}/.env${NC}     ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}3.${NC} Server management:                                            ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}     ${DIM}sudo bash ${APP_DIR}/manage_server.sh${NC}              ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"

  # DB credentials (show only on fresh install)
  if [[ "$DB_CHOICE" != "sqlite" && $IS_UPDATE -eq 0 ]]; then
    echo ""
    echo -e "${RED}┌─── DATABASE CREDENTIALS (save these!) ───────────────────────┐${NC}"
    echo -e "${RED}│${NC}  Database : ${BOLD}${DB_NAME}${NC}"
    echo -e "${RED}│${NC}  Username : ${BOLD}${DB_USER}${NC}"
    echo -e "${RED}│${NC}  Password : ${BOLD}${DB_PASS}${NC}"
    echo -e "${RED}└──────────────────────────────────────────────────────────────┘${NC}"
  fi
  echo ""
}

colorize_status() {
  case "$1" in
    active|running|file) echo -e "${GREEN}$1${NC}" ;;
    inactive|dead|unknown) echo -e "${RED}$1${NC}" ;;
    disabled) echo -e "${DIM}$1${NC}" ;;
    *) echo -e "${YELLOW}$1${NC}" ;;
  esac
}

###############################################################################
#                              MAIN                                          #
###############################################################################
main() {
  banner "Accountinox Deployment — Ubuntu $(lsb_release -rs 2>/dev/null || echo '22.04')"
  echo ""
  if [[ $IS_UPDATE -eq 1 ]]; then
    echo -e "  ${YELLOW}MODE     : UPDATE (data & .env preserved)${NC}"
  else
    echo -e "  ${GREEN}MODE     : FRESH INSTALL${NC}"
  fi
  info "App      : ${APP_DIR}"
  info "Database : ${DB_CHOICE}"
  info "Redis    : $([[ "$USE_REDIS" == "1" ]] && echo "yes" || echo "no")"
  info "Workers  : ${WORKERS}"
  info "Firewall : $([[ "$ENABLE_FIREWALL" == "1" ]] && echo "yes" || echo "no")"
  [[ -n "$DOMAIN" ]] && info "Domain   : ${DOMAIN}"
  echo ""

  phase_system
  phase_user
  phase_code
  phase_database
  phase_django
  phase_services
  phase_harden
  print_summary
}

main "$@"
