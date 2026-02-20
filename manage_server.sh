#!/usr/bin/env bash
###############################################################################
#  Accountinox — Server Management Script
#  Usage: sudo bash manage_server.sh [command] [options]
#         sudo bash manage_server.sh              (interactive menu)
#         sudo bash manage_server.sh status        (direct command)
###############################################################################
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
APP_NAME="accountinox"
APP_DIR="${APP_DIR:-/srv/${APP_NAME}}"
VENV_DIR="${APP_DIR}/.venv"
ENVFILE="${APP_DIR}/.env"
MANAGE="${VENV_DIR}/bin/python ${APP_DIR}/manage.py"
SERVICE_USER="${SERVICE_USER:-accountinox}"
BACKUP_DIR="${APP_DIR}/backups"
LOG_DIR="${APP_DIR}/logs"
MAIL_BASE_DIR="${MAIL_BASE_DIR:-/var/mail/vhosts}"
MAIL_VMAIL_USER="${MAIL_VMAIL_USER:-vmail}"
MAIL_VMAIL_GROUP="${MAIL_VMAIL_GROUP:-vmail}"
MAIL_VMAIL_UID="${MAIL_VMAIL_UID:-5000}"
MAIL_VMAIL_GID="${MAIL_VMAIL_GID:-5000}"
MAIL_DOVECOT_USERS_FILE="${MAIL_DOVECOT_USERS_FILE:-/etc/dovecot/users}"
MAIL_DKIM_SELECTOR="${MAIL_DKIM_SELECTOR:-default}"
MAIL_RELAY_CRED_FILE="${MAIL_RELAY_CRED_FILE:-/etc/postfix/sasl_passwd}"

# ─── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "${CYAN}▸${NC} $*"; }
success() { echo -e "${GREEN}✔${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
fail()    { echo -e "${RED}✗${NC} $*" >&2; }
header()  { echo -e "\n${BOLD}─── $* ───${NC}"; }

# ─── Validate environment ───────────────────────────────────────────────────
check_env() {
  [[ -d "$APP_DIR" ]]  || { fail "App directory not found: $APP_DIR"; exit 1; }
  [[ -d "$VENV_DIR" ]] || { fail "Virtualenv not found: $VENV_DIR"; exit 1; }
}

# Load .env for Django commands
load_env() {
  if [[ -f "$ENVFILE" ]]; then
    set -a
    while IFS='=' read -r key value; do
      [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
      value="${value%\"}"; value="${value#\"}"
      value="${value%\'}"; value="${value#\'}"
      export "$key"="$value"
    done < "$ENVFILE"
    set +a
  fi
  export DJANGO_SETTINGS_MODULE=config.settings
}

# Detect DB type from .env
detect_db() {
  local db_url=""
  [[ -f "$ENVFILE" ]] && db_url=$(grep -E '^DATABASE_URL=' "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2-)
  if [[ "$db_url" == mysql://* ]]; then
    echo "mysql"
  elif [[ "$db_url" == postgres://* ]]; then
    echo "postgres"
  else
    echo "sqlite"
  fi
}

# Parse DB credentials from DATABASE_URL
parse_db_url() {
  local db_url
  db_url=$(grep -E '^DATABASE_URL=' "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2-)
  # Format: scheme://user:pass@host:port/dbname
  DB_TYPE=$(echo "$db_url" | cut -d: -f1)
  local userinfo host_part
  userinfo=$(echo "$db_url" | sed 's|.*://||;s|@.*||')
  host_part=$(echo "$db_url" | sed 's|.*@||')
  _DB_USER=$(echo "$userinfo" | cut -d: -f1)
  _DB_PASS=$(echo "$userinfo" | cut -d: -f2)
  _DB_HOST=$(echo "$host_part" | cut -d: -f1)
  _DB_PORT=$(echo "$host_part" | cut -d: -f2 | cut -d/ -f1)
  _DB_NAME=$(echo "$host_part" | cut -d/ -f2)
}

# ─── Critical production checks (keep minimal) ────────────────────────────────
require_database_url() {
  load_env
  local dbu="${DATABASE_URL:-}"
  if [[ -z "$dbu" ]]; then
    fail "DATABASE_URL is not set (check $ENVFILE). Aborting."
    exit 1
  fi
}

ensure_migrations_init() {
  find "$APP_DIR/apps" -maxdepth 3 -type d -name migrations 2>/dev/null | while read -r d; do
    [[ -f "$d/__init__.py" ]] || sudo -u "$SERVICE_USER" touch "$d/__init__.py"
  done
}

fix_blog_fk_migration() {
  local f="$APP_DIR/apps/blog/migrations/0001_initial.py"
  if [[ -f "$f" ]] && grep -q "to='apps\.blog\.post'" "$f" 2>/dev/null; then
    sed -i "s/to='apps\.blog\.post'/to='blog.Post'/" "$f"
    success "Patched blog migration FK (apps.blog.post → blog.Post)"
  fi
}

mysql_tz_count() {
  mysql -u root -N -B -e "SELECT COUNT(*) FROM mysql.time_zone;" 2>/dev/null || echo "0"
}

ensure_mysql_timezones() {
  local db_type
  db_type=$(detect_db)
  [[ "$db_type" != "mysql" ]] && return 0

  local c
  c=$(mysql_tz_count | tr -d '\r' | awk '{print $1}')
  [[ -z "$c" ]] && c="0"

  if [[ "$c" -le 0 ]]; then
    warn "MySQL/MariaDB timezone tables are empty — loading..."
    mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root mysql
    c=$(mysql_tz_count | tr -d '\r' | awk '{print $1}')
    if [[ -z "$c" || "$c" -le 0 ]]; then
      fail "Failed to load MySQL timezone tables (mysql.time_zone still empty)."
      exit 1
    fi
    success "Loaded MySQL timezone tables (rows: $c)"
  else
    success "MySQL timezone tables OK (rows: $c)"
  fi
}

ensure_static_permissions_and_checks() {
  local static_css="${APP_DIR}/staticfiles/admin/css/base.css"

  [[ -d "${APP_DIR}/staticfiles" ]] && chmod -R o+rx "${APP_DIR}/staticfiles"

  if [[ ! -f "$static_css" ]]; then
    fail "Static admin CSS missing: $static_css (collectstatic likely failed)."
    exit 1
  fi

  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "https://accountinox.ir/static/admin/css/base.css" 2>/dev/null || echo "000")
  if [[ "$code" != "200" ]]; then
    fail "Nginx static check failed (expected 200, got $code) for /static/admin/css/base.css"
    exit 1
  fi
  success "Nginx static OK (200)"
}

build_health_urls() {
  local path="${HEALTHCHECK_PATH:-/healthz/}"
  [[ "$path" != /* ]] && path="/$path"

  local primary="${HEALTHCHECK_URL:-http://127.0.0.1:8000${path}}"
  local fallback="${HEALTHCHECK_FALLBACK_URL:-}"

  # Load env so SITE_URL is available if defined in .env
  load_env
  local site_url="${SITE_URL:-}"

  HEALTH_URLS=()
  HEALTH_URLS+=("$primary")
  [[ -n "$fallback" ]] && HEALTH_URLS+=("$fallback")
  [[ -n "$site_url" ]] && HEALTH_URLS+=("${site_url%/}${path}")
}

probe_health_once() {
  local timeout="${HEALTHCHECK_TIMEOUT:-8}"
  local body_file
  body_file=$(mktemp)
  HEALTHCHECK_LAST_TRY=""
  HEALTHCHECK_LAST_OK=""

  local url code body
  for url in "${HEALTH_URLS[@]}"; do
    code=$(curl -sS -L --max-time "$timeout" -o "$body_file" -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then
      body=$(head -c 200 "$body_file" | tr '\n' ' ')
      HEALTHCHECK_LAST_OK="${url} (HTTP 200) ${body}"
      rm -f "$body_file"
      return 0
    fi
    if [[ -z "$HEALTHCHECK_LAST_TRY" ]]; then
      HEALTHCHECK_LAST_TRY="${url} -> HTTP ${code}"
    else
      HEALTHCHECK_LAST_TRY="${HEALTHCHECK_LAST_TRY} | ${url} -> HTTP ${code}"
    fi
  done

  rm -f "$body_file"
  return 1
}

wait_for_health() {
  build_health_urls

  local retries="${HEALTHCHECK_RETRIES:-12}"
  local delay="${HEALTHCHECK_DELAY:-2}"
  local i
  for ((i=1; i<=retries; i++)); do
    if probe_health_once; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

print_health_failure_context() {
  warn "Health probe failed after retries."
  [[ -n "${HEALTHCHECK_LAST_TRY:-}" ]] && warn "Last probe results: ${HEALTHCHECK_LAST_TRY}"

  local st
  st=$(systemctl is-active "${APP_NAME}" 2>/dev/null || echo "unknown")
  warn "Service ${APP_NAME} status: ${st}"

  warn "Recent ${APP_NAME} logs:"
  journalctl -u "${APP_NAME}" -n 20 --no-pager 2>/dev/null || true
}

###############################################################################
#                              COMMANDS                                       #
###############################################################################

# ──────────── Status ────────────
cmd_status() {
  header "System Status"

  # Services
  local services=("${APP_NAME}" "nginx")
  local db_type
  db_type=$(detect_db)
  case "$db_type" in
    mysql)    services+=("mariadb" "mysql") ;;
    postgres) services+=("postgresql") ;;
  esac
  [[ -f "$ENVFILE" ]] && grep -q 'REDIS_URL' "$ENVFILE" && services+=("redis-server")
  services+=("fail2ban" "ufw")

  printf "  ${BOLD}%-25s %-12s${NC}\n" "SERVICE" "STATUS"
  printf "  %-25s %-12s\n" "─────────────────────────" "────────────"
  for svc in "${services[@]}"; do
    local st
    st=$(systemctl is-active "$svc" 2>/dev/null || echo "n/a")
    local color="$RED"
    [[ "$st" == "active" ]] && color="$GREEN"
    [[ "$st" == "n/a" ]] && color="$DIM"
    printf "  %-25s ${color}%-12s${NC}\n" "$svc" "$st"
  done

  # Resources
  header "Resources"
  echo -e "  ${BOLD}CPU:${NC}"
  echo "    Load: $(cat /proc/loadavg | awk '{print $1, $2, $3}')"
  echo "    Cores: $(nproc)"
  echo ""
  echo -e "  ${BOLD}Memory:${NC}"
  free -h | awk '/^Mem:/ {printf "    Total: %s | Used: %s | Free: %s | Available: %s\n", $2, $3, $4, $7}'
  if [[ -f /proc/swaps ]] && swapon --show 2>/dev/null | grep -q .; then
    free -h | awk '/^Swap:/ {printf "    Swap:  Total: %s | Used: %s | Free: %s\n", $2, $3, $4}'
  fi
  echo ""
  echo -e "  ${BOLD}Disk:${NC}"
  df -h / | awk 'NR==2 {printf "    Root: %s total | %s used (%s) | %s free\n", $2, $3, $5, $4}'
  echo "    App dir: $(du -sh "$APP_DIR" 2>/dev/null | awk '{print $1}')"
  echo "    Logs: $(du -sh "$LOG_DIR" 2>/dev/null | awk '{print $1}')"
  echo "    Backups: $(du -sh "$BACKUP_DIR" 2>/dev/null | awk '{print $1}')"
  echo ""

  # Uptime
  echo -e "  ${BOLD}Uptime:${NC} $(uptime -p 2>/dev/null || uptime)"

  # App health check
  header "Health Check"
  if wait_for_health; then
    success "App responding: ${HEALTHCHECK_LAST_OK}"
  else
    fail "App health check failed"
    print_health_failure_context
  fi
}

# ──────────── Service control ────────────
cmd_start()   { systemctl start ${APP_NAME} && success "Started"; }
cmd_stop()    { systemctl stop ${APP_NAME} && success "Stopped"; }
cmd_restart() {
  header "Restarting Accountinox"
  systemctl restart ${APP_NAME}
  sleep 2
  local st
  st=$(systemctl is-active ${APP_NAME} 2>/dev/null)
  if [[ "$st" == "active" ]]; then
    success "Restarted successfully"
  else
    fail "Restart failed"
    journalctl -u ${APP_NAME} -n 15 --no-pager
  fi
}
cmd_reload() {
  systemctl reload ${APP_NAME} 2>/dev/null || systemctl restart ${APP_NAME}
  success "Reloaded"
}

# ──────────── Deploy / Update ────────────
cmd_deploy() {
  header "Deploying Update"
  local started=$SECONDS

  # 1. Backup DB first
  info "Creating pre-deploy backup..."
  cmd_backup_db

  # 2. Pull latest code
  info "Pulling latest code..."
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" git fetch --all --quiet 2>/dev/null
  sudo -u "$SERVICE_USER" git reset --hard origin/HEAD --quiet 2>/dev/null || \
    sudo -u "$SERVICE_USER" git reset --hard origin/main --quiet 2>/dev/null
  success "Code updated ($(sudo -u "$SERVICE_USER" git log -1 --format='%h %s' 2>/dev/null))"

  # 3. Install dependencies
  info "Installing dependencies..."
  source "$VENV_DIR/bin/activate"
  pip install -q --no-cache-dir -r requirements.txt 2>/dev/null
  deactivate

  # 4. Migrate & collect static
  load_env
  require_database_url
  ensure_mysql_timezones
  ensure_migrations_init
  fix_blog_fk_migration
  info "Running migrations..."
  sudo -u "$SERVICE_USER" $MANAGE migrate --noinput 2>&1 | tail -5

  info "Collecting static files..."
  sudo -u "$SERVICE_USER" $MANAGE collectstatic --noinput --clear 2>&1 | tail -1

  ensure_static_permissions_and_checks

  # 5. Restart
  info "Restarting services..."
  systemctl restart ${APP_NAME}
  systemctl reload nginx
  sleep 2

  # 6. Health check
  if wait_for_health; then
    success "Deploy complete in $((SECONDS - started))s — app healthy"
  else
    fail "Deploy finished but health check failed!"
    print_health_failure_context
    warn "Consider rollback: sudo bash $0 rollback"
  fi
}

cmd_pull_update() {
  header "Pull + Update Project"
  local started=$SECONDS

  cd "$APP_DIR"

  # Pull latest commit without force-reset (safer for local server patches)
  info "Pulling latest code (fast-forward only)..."
  if ! sudo -u "$SERVICE_USER" git -C "$APP_DIR" pull --ff-only; then
    fail "git pull failed (non-fast-forward or conflict)."
    warn "Tip: use 'sudo bash $0 deploy' for force deploy from origin."
    return 1
  fi
  success "Code updated ($(sudo -u "$SERVICE_USER" git -C "$APP_DIR" log -1 --format='%h %s' 2>/dev/null))"

  # Install dependencies
  info "Installing dependencies..."
  source "$VENV_DIR/bin/activate"
  pip install -q --no-cache-dir -r requirements.txt 2>/dev/null
  deactivate

  # Migrate & collect static
  load_env
  require_database_url
  ensure_mysql_timezones
  ensure_migrations_init
  fix_blog_fk_migration

  info "Running migrations..."
  sudo -u "$SERVICE_USER" $MANAGE migrate --noinput 2>&1 | tail -5

  info "Collecting static files..."
  sudo -u "$SERVICE_USER" $MANAGE collectstatic --noinput --clear 2>&1 | tail -1

  ensure_static_permissions_and_checks

  # Restart
  info "Restarting services..."
  systemctl restart ${APP_NAME}
  systemctl reload nginx
  sleep 2

  # Health check
  if wait_for_health; then
    success "Pull update complete in $((SECONDS - started))s - app healthy"
  else
    fail "Update finished but health check failed!"
    print_health_failure_context
    warn "Consider rollback: sudo bash $0 rollback"
  fi
}

# ──────────── Rollback ────────────
cmd_rollback() {
  header "Rollback"
  local latest_backup
  latest_backup=$(ls -t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -1)
  [[ -z "$latest_backup" ]] && { fail "No backups found in $BACKUP_DIR"; return 1; }

  echo -e "  Latest backup: ${CYAN}$(basename "$latest_backup")${NC}"
  echo -e "  ${YELLOW}This will restore the database from backup.${NC}"
  read -rp "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }

  local db_type
  db_type=$(detect_db)
  parse_db_url

  case "$db_type" in
    mysql)
      zcat "$latest_backup" | mysql -u "$_DB_USER" -p"$_DB_PASS" "$_DB_NAME"
      ;;
    postgres)
      zcat "$latest_backup" | PGPASSWORD="$_DB_PASS" psql -U "$_DB_USER" -h "$_DB_HOST" "$_DB_NAME"
      ;;
    sqlite)
      local sqlite_backup
      sqlite_backup=$(ls -t "$BACKUP_DIR"/db_*.sqlite3 2>/dev/null | head -1)
      [[ -z "$sqlite_backup" ]] && { fail "No SQLite backup found"; return 1; }
      cp "$sqlite_backup" "$APP_DIR/db.sqlite3"
      chown "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR/db.sqlite3"
      ;;
  esac

  systemctl restart ${APP_NAME}
  success "Rolled back to $(basename "$latest_backup")"
}

# ──────────── Database backup ────────────
cmd_backup_db() {
  header "Database Backup"
  mkdir -p "$BACKUP_DIR"
  local timestamp
  timestamp=$(date +%Y%m%d_%H%M%S)
  local db_type
  db_type=$(detect_db)

  case "$db_type" in
    mysql)
      parse_db_url
      local outfile="${BACKUP_DIR}/db_${timestamp}.sql.gz"
      mysqldump --single-transaction -u "$_DB_USER" -p"$_DB_PASS" "$_DB_NAME" 2>/dev/null | gzip > "$outfile"
      ;;
    postgres)
      parse_db_url
      local outfile="${BACKUP_DIR}/db_${timestamp}.sql.gz"
      PGPASSWORD="$_DB_PASS" pg_dump -U "$_DB_USER" -h "$_DB_HOST" "$_DB_NAME" 2>/dev/null | gzip > "$outfile"
      ;;
    sqlite)
      local outfile="${BACKUP_DIR}/db_${timestamp}.sqlite3"
      cp "$APP_DIR/db.sqlite3" "$outfile"
      ;;
  esac

  chown "$SERVICE_USER":"$SERVICE_USER" "$outfile"
  local size
  size=$(du -h "$outfile" | awk '{print $1}')
  success "Backup saved: $(basename "$outfile") ($size)"

  # Cleanup old backups (keep 30 days)
  find "$BACKUP_DIR" -name 'db_*' -mtime +30 -delete 2>/dev/null || true
}

# ──────────── Logs ────────────
cmd_logs() {
  local target="${1:-app}"
  header "Logs — $target"
  case "$target" in
    app|gunicorn)
      journalctl -u ${APP_NAME} -n 50 --no-pager ;;
    access)
      tail -50 "$LOG_DIR/access.log" 2>/dev/null || journalctl -u ${APP_NAME} -n 50 --no-pager ;;
    error)
      tail -50 "$LOG_DIR/gunicorn.log" 2>/dev/null ;;
    nginx)
      tail -50 /var/log/nginx/error.log 2>/dev/null ;;
    django)
      tail -50 "$LOG_DIR/django_error.log" 2>/dev/null ;;
    all)
      journalctl -u ${APP_NAME} -u nginx -n 80 --no-pager ;;
    follow|live)
      journalctl -u ${APP_NAME} -f ;;
    *)
      info "Usage: logs [app|access|error|nginx|django|all|follow]" ;;
  esac
}

# ──────────── Django management ────────────
cmd_django() {
  load_env
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE "$@"
}

cmd_shell() {
  load_env
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE shell
}

cmd_createsuperuser() {
  load_env
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE createsuperuser
}

# ──────────── Admin / Superuser Management ────────────
cmd_admins() {
  local subcmd="${1:-menu}"
  load_env
  cd "$APP_DIR"

  case "$subcmd" in
    list)
      header "Admin / Staff Users"
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
admins = User.objects.filter(is_staff=True).order_by('-is_superuser', 'username')
print(f'  {\"Username\":<20} {\"Email\":<30} {\"Superuser\":<12} {\"Active\":<8} {\"Last Login\":<20}')
print(f'  {\"─\"*20} {\"─\"*30} {\"─\"*12} {\"─\"*8} {\"─\"*20}')
for u in admins:
    ll = u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else 'never'
    print(f'  {u.username:<20} {u.email:<30} {str(u.is_superuser):<12} {str(u.is_active):<8} {ll:<20}')
print(f'\n  Total: {admins.count()} admin/staff users')
" 2>/dev/null
      ;;

    info)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Admin username: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      header "Admin Info: $target_user"
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user', is_staff=True)
except User.DoesNotExist:
    print('  Admin not found: $target_user (must be a staff user)')
    exit(1)
print(f'  Username    : {u.username}')
print(f'  Email       : {u.email}')
print(f'  First name  : {u.first_name}')
print(f'  Last name   : {u.last_name}')
print(f'  Active      : {u.is_active}')
print(f'  Staff       : {u.is_staff}')
print(f'  Superuser   : {u.is_superuser}')
print(f'  Date joined : {u.date_joined}')
print(f'  Last login  : {u.last_login}')
try:
    from apps.accounts.models import Profile
    p = Profile.objects.get(user=u)
    print(f'  Phone       : {p.phone or \"—\"}')
except Exception:
    pass
from django.contrib.auth.models import Permission
perms = u.user_permissions.all()
if perms:
    print(f'  Permissions : {perms.count()}')
    for p in perms[:10]:
        print(f'                {p.content_type.app_label}.{p.codename}')
    if perms.count() > 10:
        print(f'                ... +{perms.count()-10} more')
groups = u.groups.all()
if groups:
    print(f'  Groups      : {\"، \".join(g.name for g in groups)}')
" 2>/dev/null
      ;;

    passwd)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Admin username: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      read -rsp "  New password: " newpass; echo
      read -rsp "  Confirm password: " newpass2; echo
      [[ "$newpass" != "$newpass2" ]] && { fail "Passwords don't match"; return 1; }
      [[ ${#newpass} -lt 8 ]] && { fail "Password must be at least 8 characters"; return 1; }
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user', is_staff=True)
    u.set_password('$newpass')
    u.save()
    print('Password changed successfully for admin: $target_user')
except User.DoesNotExist:
    print('Admin not found: $target_user')
" 2>/dev/null
      ;;

    email)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Admin username: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      read -rp "  New email: " newemail
      [[ -z "$newemail" ]] && { fail "Email required"; return 1; }
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user', is_staff=True)
    old = u.email
    u.email = '$newemail'
    u.save()
    print(f'Email updated: {old} → $newemail')
except User.DoesNotExist:
    print('Admin not found: $target_user')
" 2>/dev/null
      ;;

    toggle-active)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Admin username: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user', is_staff=True)
    if u.is_superuser and u.is_active:
        sc = User.objects.filter(is_superuser=True, is_active=True).count()
        if sc <= 1:
            print('Cannot deactivate the last active superuser!')
            exit(1)
    u.is_active = not u.is_active
    u.save()
    state = 'activated' if u.is_active else 'deactivated'
    print(f'Admin {u.username} {state}')
except User.DoesNotExist:
    print('Admin not found: $target_user')
" 2>/dev/null
      ;;

    promote)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Username to promote to superuser: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      echo -e "  ${YELLOW}Warning: Superuser has FULL access to admin panel and all data.${NC}"
      read -rp "  Promote '$target_user' to superuser? [y/N] " confirm
      [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user')
    u.is_staff = True
    u.is_superuser = True
    u.save()
    print(f'{u.username} promoted to superuser')
except User.DoesNotExist:
    print('User not found: $target_user')
" 2>/dev/null
      ;;

    demote)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Superuser to demote: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user', is_staff=True)
    if u.is_superuser:
        sc = User.objects.filter(is_superuser=True, is_active=True).count()
        if sc <= 1:
            print('Cannot demote the last superuser!')
            exit(1)
    u.is_superuser = False
    u.save()
    print(f'{u.username} demoted (still staff, no longer superuser)')
except User.DoesNotExist:
    print('Admin not found: $target_user')
" 2>/dev/null
      ;;

    revoke)
      local target_user="${2:-}"
      [[ -z "$target_user" ]] && { read -rp "  Admin to revoke all access: " target_user; }
      [[ -z "$target_user" ]] && { fail "Username required"; return 1; }
      echo -e "  ${RED}This removes both staff and superuser access.${NC}"
      read -rp "  Confirm revoke for '$target_user'? [y/N] " confirm
      [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    u = User.objects.get(username='$target_user', is_staff=True)
    if u.is_superuser:
        sc = User.objects.filter(is_superuser=True, is_active=True).count()
        if sc <= 1:
            print('Cannot revoke the last superuser!')
            exit(1)
    u.is_staff = False
    u.is_superuser = False
    u.save()
    print(f'All admin access revoked for {u.username}')
except User.DoesNotExist:
    print('Admin not found: $target_user')
" 2>/dev/null
      ;;

    sessions)
      header "Active Admin Sessions"
      sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib.auth import get_user_model
User = get_user_model()
active = Session.objects.filter(expire_date__gte=timezone.now())
print(f'  Active sessions: {active.count()}')
admin_sessions = 0
for s in active:
    data = s.get_decoded()
    uid = data.get('_auth_user_id')
    if uid:
        try:
            u = User.objects.get(pk=uid, is_staff=True)
            admin_sessions += 1
            print(f'    {u.username:<20} expires: {s.expire_date:%Y-%m-%d %H:%M}')
        except User.DoesNotExist:
            pass
if admin_sessions == 0:
    print('  No active admin sessions')
" 2>/dev/null
      ;;

    menu|*)
      echo ""
      echo -e "  ${BOLD}Admin / Superuser Management${NC}"
      echo -e "  ${CYAN}1${NC}) List admins/staff        ${CYAN}2${NC}) Admin info"
      echo -e "  ${CYAN}3${NC}) Change admin password    ${CYAN}4${NC}) Change admin email"
      echo -e "  ${CYAN}5${NC}) Activate / deactivate    ${CYAN}6${NC}) Promote to superuser"
      echo -e "  ${CYAN}7${NC}) Demote from superuser    ${CYAN}8${NC}) Revoke all admin access"
      echo -e "  ${CYAN}9${NC}) Create new superuser     ${CYAN}10${NC}) Active admin sessions"
      echo -e "  ${CYAN}0${NC}) Back"
      echo ""
      read -rp "$(echo -e "${CYAN}▸${NC} Choice: ")" uchoice
      case "$uchoice" in
        1)  cmd_admins list ;;
        2)  cmd_admins info ;;
        3)  cmd_admins passwd ;;
        4)  cmd_admins email ;;
        5)  cmd_admins toggle-active ;;
        6)  cmd_admins promote ;;
        7)  cmd_admins demote ;;
        8)  cmd_admins revoke ;;
        9)  cmd_createsuperuser ;;
        10) cmd_admins sessions ;;
        0|*) return 0 ;;
      esac
      ;;
  esac
}

# ──────────── .env Management ────────────
# Helper: upsert a key=value in .env (update if exists, append if not)
_env_upsert() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENVFILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENVFILE"
  else
    echo "${key}=${value}" >> "$ENVFILE"
  fi
  chmod 600 "$ENVFILE"
  chown "$SERVICE_USER":"$SERVICE_USER" "$ENVFILE" 2>/dev/null || true
}

_env_get() {
  local key="$1"
  grep -E "^${key}=" "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2-
}

_email_mask() {
  local key="$1" value="$2"
  if [[ -z "$value" ]]; then
    echo "${DIM}(empty)${NC}"
    return 0
  fi
  if [[ "$key" =~ (PASSWORD|SECRET|TOKEN|KEY) ]]; then
    echo "${value:0:4}${DIM}••••••••${NC}"
  else
    echo "$value"
  fi
}

_email_bool_default() {
  local current="$1" fallback="$2"
  case "${current:-$fallback}" in
    1|true|TRUE|True|yes|YES|on|ON) echo "True" ;;
    *) echo "False" ;;
  esac
}

_email_prompt_bool() {
  local prompt="$1" default_val="$2" input
  if [[ "$default_val" == "True" ]]; then
    read -rp "  ${prompt} [Y/n]: " input
    [[ "$input" =~ ^[Nn]$ ]] && echo "False" || echo "True"
  else
    read -rp "  ${prompt} [y/N]: " input
    [[ "$input" =~ ^[Yy]$ ]] && echo "True" || echo "False"
  fi
}

_email_show_status() {
  header "Email Configuration Status"
  local keys=(
    EMAIL_BACKEND
    EMAIL_HOST
    EMAIL_PORT
    EMAIL_USE_TLS
    EMAIL_USE_SSL
    EMAIL_TIMEOUT
    EMAIL_HOST_USER
    EMAIL_HOST_PASSWORD
    DEFAULT_FROM_EMAIL
  )
  local k v
  for k in "${keys[@]}"; do
    v=$(_env_get "$k")
    echo -e "  ${CYAN}${k}${NC}=$(_email_mask "$k" "$v")"
  done

  local backend host port user pass from
  backend=$(_env_get "EMAIL_BACKEND")
  host=$(_env_get "EMAIL_HOST")
  port=$(_env_get "EMAIL_PORT")
  user=$(_env_get "EMAIL_HOST_USER")
  pass=$(_env_get "EMAIL_HOST_PASSWORD")
  from=$(_env_get "DEFAULT_FROM_EMAIL")

  echo ""
  if [[ -z "$backend" ]]; then
    info "EMAIL_BACKEND is not set in .env (Django falls back to SMTP when DEBUG=0)."
  fi

  local effective_backend="${backend:-django.core.mail.backends.smtp.EmailBackend}"
  if [[ "$effective_backend" == "django.core.mail.backends.console.EmailBackend" ]]; then
    warn "Console backend is active — emails are NOT actually sent."
  fi
  if [[ "$effective_backend" == "django.core.mail.backends.smtp.EmailBackend" ]]; then
    [[ -z "$host" ]] && warn "EMAIL_HOST is empty."
    [[ -z "$port" ]] && warn "EMAIL_PORT is empty."
    [[ -z "$user" ]] && warn "EMAIL_HOST_USER is empty."
    [[ -z "$pass" ]] && warn "EMAIL_HOST_PASSWORD is empty."
    [[ -z "$from" ]] && warn "DEFAULT_FROM_EMAIL is empty."
  fi
}

_email_save_smtp_settings() {
  local host="$1"
  local port="$2"
  local use_tls="$3"
  local use_ssl="$4"
  local user="$5"
  local pass="$6"
  local from_addr="$7"
  local timeout="$8"

  cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
  _env_upsert "EMAIL_BACKEND" "django.core.mail.backends.smtp.EmailBackend"
  _env_upsert "EMAIL_HOST" "$host"
  _env_upsert "EMAIL_PORT" "$port"
  _env_upsert "EMAIL_USE_TLS" "$use_tls"
  _env_upsert "EMAIL_USE_SSL" "$use_ssl"
  _env_upsert "EMAIL_HOST_USER" "$user"
  _env_upsert "EMAIL_HOST_PASSWORD" "$pass"
  _env_upsert "DEFAULT_FROM_EMAIL" "$from_addr"
  _env_upsert "EMAIL_TIMEOUT" "$timeout"
}

_email_configure_wizard() {
  header "SMTP Setup Wizard"
  echo -e "  ${CYAN}1${NC}) Brevo (recommended)"
  echo -e "  ${CYAN}2${NC}) Mailgun"
  echo -e "  ${CYAN}3${NC}) SMTP2GO"
  echo -e "  ${CYAN}4${NC}) Gmail / Google Workspace"
  echo -e "  ${CYAN}5${NC}) Custom SMTP"
  echo -e "  ${CYAN}0${NC}) Back"
  read -rp "$(echo -e "${CYAN}▸${NC} Provider: ")" provider

  local smtp_host smtp_port tls_default ssl_default timeout_default from_hint
  timeout_default="20"
  case "$provider" in
    1) smtp_host="smtp-relay.brevo.com"; smtp_port="587"; tls_default="True";  ssl_default="False"; from_hint="noreply@your-domain.com" ;;
    2) smtp_host="smtp.mailgun.org";     smtp_port="587"; tls_default="True";  ssl_default="False"; from_hint="noreply@your-domain.com" ;;
    3) smtp_host="mail.smtp2go.com";     smtp_port="587"; tls_default="True";  ssl_default="False"; from_hint="noreply@your-domain.com" ;;
    4) smtp_host="smtp.gmail.com";       smtp_port="587"; tls_default="True";  ssl_default="False"; from_hint="your-email@gmail.com" ;;
    5) smtp_host="$(_env_get EMAIL_HOST)"; smtp_port="$(_env_get EMAIL_PORT)"; tls_default="$(_email_bool_default "$(_env_get EMAIL_USE_TLS)" "True")"; ssl_default="$(_email_bool_default "$(_env_get EMAIL_USE_SSL)" "False")"; from_hint="$(_env_get DEFAULT_FROM_EMAIL)" ;;
    0|*) return 0 ;;
  esac

  [[ -z "$smtp_host" ]] && smtp_host="smtp.example.com"
  [[ -z "$smtp_port" ]] && smtp_port="587"
  [[ -z "$tls_default" ]] && tls_default="True"
  [[ -z "$ssl_default" ]] && ssl_default="False"
  [[ -z "$from_hint" ]] && from_hint="noreply@your-domain.com"

  local input
  read -rp "  SMTP Host [${smtp_host}]: " input
  [[ -n "$input" ]] && smtp_host="$input"
  read -rp "  SMTP Port [${smtp_port}]: " input
  [[ -n "$input" ]] && smtp_port="$input"

  local smtp_tls smtp_ssl
  smtp_tls=$(_email_prompt_bool "Use TLS" "$tls_default")
  smtp_ssl=$(_email_prompt_bool "Use SSL" "$ssl_default")
  if [[ "$smtp_tls" == "True" && "$smtp_ssl" == "True" ]]; then
    warn "Both TLS and SSL were enabled. Forcing SSL=False (recommended with port 587)."
    smtp_ssl="False"
  fi

  local smtp_user smtp_pass from_addr timeout
  read -rp "  SMTP Username: " smtp_user
  read -rsp "  SMTP Password: " smtp_pass; echo
  read -rp "  DEFAULT_FROM_EMAIL [${from_hint}]: " from_addr
  from_addr="${from_addr:-$from_hint}"
  read -rp "  EMAIL_TIMEOUT seconds [${timeout_default}]: " timeout
  timeout="${timeout:-$timeout_default}"

  if [[ -z "$smtp_host" || -z "$smtp_port" || -z "$smtp_user" || -z "$smtp_pass" || -z "$from_addr" ]]; then
    fail "SMTP setup canceled: required fields cannot be empty."
    return 1
  fi

  _email_save_smtp_settings "$smtp_host" "$smtp_port" "$smtp_tls" "$smtp_ssl" "$smtp_user" "$smtp_pass" "$from_addr" "$timeout"
  success "SMTP configuration saved in .env"
  echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
}

_email_enable_console_backend() {
  header "Enable Console Email Backend"
  echo -e "  ${YELLOW}This mode does NOT send real emails. Useful for temporary debugging.${NC}"
  read -rp "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }
  cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
  _env_upsert "EMAIL_BACKEND" "django.core.mail.backends.console.EmailBackend"
  success "Console email backend enabled"
  echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
}

_email_reset_settings() {
  header "Reset Email Settings"
  echo -e "  ${RED}This will remove EMAIL_* and DEFAULT_FROM_EMAIL from .env.${NC}"
  read -rp "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }
  cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
  sed -i '/^EMAIL_/d; /^DEFAULT_FROM_EMAIL=/d' "$ENVFILE"
  success "Email settings removed from .env"
  info "When DEBUG=0, Django will fall back to SMTP defaults unless you configure again."
  echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
}

_email_send_test() {
  local to="${1:-}"
  [[ -z "$to" ]] && read -rp "  Test recipient email: " to
  [[ -z "$to" ]] && { fail "Recipient email is required"; return 1; }

  header "Sending Test Email"
  load_env
  cd "$APP_DIR"

  if sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.conf import settings
from django.core.mail import send_mail
subject = '[Accountinox] SMTP test'
message = 'This is a test email from manage_server.sh.'
sent = send_mail(subject, message, getattr(settings, 'DEFAULT_FROM_EMAIL', None), ['$to'], fail_silently=False)
print(f'sent={sent} backend={getattr(settings, \"EMAIL_BACKEND\", \"\")}')
"; then
    success "Test email request completed. Check inbox/spam for: $to"
  else
    fail "Test email failed. Check app logs: sudo bash $0 logs django"
    return 1
  fi
}

_mail_validate_domain() {
  local domain="$1"
  [[ "$domain" =~ ^([A-Za-z0-9-]+\.)+[A-Za-z]{2,}$ ]]
}

_mail_validate_email() {
  local email="$1"
  [[ "$email" =~ ^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$ ]]
}

_mail_guess_domain() {
  local raw
  raw=$(_env_get "SITE_BASE_URL")
  [[ -z "$raw" ]] && raw=$(_env_get "SITE_URL")
  [[ -z "$raw" ]] && raw=$(_env_get "ALLOWED_HOSTS")
  raw="${raw%%,*}"
  raw="${raw#http://}"
  raw="${raw#https://}"
  raw="${raw%%/*}"
  raw="${raw#www.}"
  echo "$raw"
}

_mail_first_domain() {
  if [[ -f /etc/postfix/vmail_domains ]]; then
    awk '!/^#/ && NF >= 1 {print $1; exit}' /etc/postfix/vmail_domains 2>/dev/null
  fi
}

_mail_upsert_map_file() {
  local file="$1" key="$2" value="$3"
  touch "$file"
  local tmp
  tmp=$(mktemp)
  awk -v k="$key" -v v="$value" '
    BEGIN{done=0}
    $1==k {print k " " v; done=1; next}
    {print}
    END{if(!done) print k " " v}
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

_mail_remove_map_key() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  local tmp
  tmp=$(mktemp)
  awk -v k="$key" '$1!=k {print}' "$file" > "$tmp"
  mv "$tmp" "$file"
}

_mail_upsert_dovecot_user() {
  local email="$1" hash="$2"
  touch "$MAIL_DOVECOT_USERS_FILE"
  local tmp
  tmp=$(mktemp)
  awk -F: -v e="$email" -v h="$hash" '
    BEGIN{done=0}
    $1==e {$0=e ":" h; done=1}
    {print}
    END{if(!done) print e ":" h}
  ' "$MAIL_DOVECOT_USERS_FILE" > "$tmp"
  mv "$tmp" "$MAIL_DOVECOT_USERS_FILE"
  chown root:dovecot "$MAIL_DOVECOT_USERS_FILE" 2>/dev/null || true
  chmod 640 "$MAIL_DOVECOT_USERS_FILE"
}

_mail_remove_dovecot_user() {
  local email="$1"
  [[ -f "$MAIL_DOVECOT_USERS_FILE" ]] || return 0
  local tmp
  tmp=$(mktemp)
  awk -F: -v e="$email" '$1!=e {print}' "$MAIL_DOVECOT_USERS_FILE" > "$tmp"
  mv "$tmp" "$MAIL_DOVECOT_USERS_FILE"
}

_mail_resolve_cert_paths() {
  local mail_host="$1"
  local le_dir="/etc/letsencrypt/live/${mail_host}"
  if [[ -f "${le_dir}/fullchain.pem" && -f "${le_dir}/privkey.pem" ]]; then
    echo "${le_dir}/fullchain.pem|${le_dir}/privkey.pem"
    return 0
  fi

  local ssl_dir="/etc/ssl/accountinox-mail"
  local cert_file="${ssl_dir}/${mail_host}.crt"
  local key_file="${ssl_dir}/${mail_host}.key"
  mkdir -p "$ssl_dir"
  if [[ ! -f "$cert_file" || ! -f "$key_file" ]]; then
    warn "Let's Encrypt cert not found for ${mail_host}; generating self-signed cert (temporary)."
    openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
      -subj "/CN=${mail_host}" \
      -keyout "$key_file" \
      -out "$cert_file" >/dev/null 2>&1
  fi
  chmod 600 "$key_file"
  chmod 644 "$cert_file"
  echo "${cert_file}|${key_file}"
}

_mail_ensure_vmail_user() {
  if ! getent group "$MAIL_VMAIL_GROUP" >/dev/null 2>&1; then
    groupadd -g "$MAIL_VMAIL_GID" "$MAIL_VMAIL_GROUP" 2>/dev/null || groupadd "$MAIL_VMAIL_GROUP"
  fi
  if ! id -u "$MAIL_VMAIL_USER" >/dev/null 2>&1; then
    useradd -u "$MAIL_VMAIL_UID" -g "$MAIL_VMAIL_GROUP" -d "$MAIL_BASE_DIR" -m -s /usr/sbin/nologin "$MAIL_VMAIL_USER" 2>/dev/null || \
      useradd -g "$MAIL_VMAIL_GROUP" -d "$MAIL_BASE_DIR" -m -s /usr/sbin/nologin "$MAIL_VMAIL_USER"
  fi
  mkdir -p "$MAIL_BASE_DIR"
  chown -R "$MAIL_VMAIL_USER:$MAIL_VMAIL_GROUP" "$MAIL_BASE_DIR"
  chmod 770 "$MAIL_BASE_DIR"
}

_mail_postmap_refresh() {
  postmap /etc/postfix/vmail_domains 2>/dev/null || true
  postmap /etc/postfix/vmail_mailboxes 2>/dev/null || true
  postmap /etc/postfix/vmail_aliases 2>/dev/null || true
}

_mail_reload_services() {
  systemctl restart opendkim
  systemctl restart dovecot
  systemctl restart postfix
}

_mail_ensure_submission_service() {
  if ! grep -Eq '^submission[[:space:]]+inet' /etc/postfix/master.cf 2>/dev/null; then
    cat >> /etc/postfix/master.cf <<'EOF'
submission inet n       -       y       -       -       smtpd
  -o syslog_name=postfix/submission
  -o smtpd_tls_security_level=encrypt
  -o smtpd_sasl_auth_enable=yes
  -o smtpd_recipient_restrictions=permit_sasl_authenticated,reject
  -o milter_macro_daemon_name=ORIGINATING
EOF
  fi
}

_mail_dns_instructions() {
  local domain="${1:-$(_mail_first_domain)}"
  local mail_host="${2:-mail.${domain}}"
  [[ -z "$domain" ]] && { warn "No configured mail domain found."; return 1; }

  header "DNS Records (add on your DNS provider)"
  echo -e "  ${BOLD}A record${NC}"
  echo -e "    ${CYAN}${mail_host}${NC} -> ${BOLD}<YOUR_SERVER_IP>${NC}"
  echo -e "  ${BOLD}MX record${NC}"
  echo -e "    ${CYAN}${domain}${NC} -> ${BOLD}10 ${mail_host}.${NC}"
  echo -e "  ${BOLD}SPF TXT${NC}"
  echo -e "    ${CYAN}${domain}${NC} -> ${BOLD}v=spf1 mx a:${mail_host} ~all${NC}"
  echo -e "  ${BOLD}DMARC TXT${NC}"
  echo -e "    ${CYAN}_dmarc.${domain}${NC} -> ${BOLD}v=DMARC1; p=quarantine; rua=mailto:postmaster@${domain}; adkim=s; aspf=s${NC}"

  local dkim_txt_file="/etc/opendkim/keys/${domain}/${MAIL_DKIM_SELECTOR}.txt"
  if [[ -f "$dkim_txt_file" ]]; then
    local dkim_value
    dkim_value=$(awk -F\" '/\"/ {for(i=2;i<=NF;i+=2) printf "%s",$i}' "$dkim_txt_file")
    echo -e "  ${BOLD}DKIM TXT${NC}"
    echo -e "    ${CYAN}${MAIL_DKIM_SELECTOR}._domainkey.${domain}${NC} -> ${BOLD}${dkim_value}${NC}"
  else
    warn "DKIM key file not found: $dkim_txt_file"
  fi

  echo ""
  warn "Important: Set reverse DNS (PTR) for server IP -> ${mail_host}"
}

_mailserver_setup() {
  header "Lightweight Mail Server Setup"
  local domain="${1:-}"
  local mail_host="${2:-}"

  [[ -z "$domain" ]] && domain=$(_mail_guess_domain)
  [[ -z "$domain" ]] && read -rp "  Mail domain (e.g. example.com): " domain
  [[ -z "$mail_host" ]] && mail_host="mail.${domain}"
  read -rp "  Mail hostname [${mail_host}]: " input_mail_host
  mail_host="${input_mail_host:-$mail_host}"

  if ! _mail_validate_domain "$domain"; then
    fail "Invalid domain: $domain"
    return 1
  fi
  if ! _mail_validate_domain "$mail_host"; then
    fail "Invalid mail hostname: $mail_host"
    return 1
  fi

  echo -e "  Domain: ${CYAN}${domain}${NC}"
  echo -e "  Mail host: ${CYAN}${mail_host}${NC}"
  echo -e "  Stack: ${BOLD}Postfix + Dovecot(IMAPS only) + OpenDKIM${NC} ${DIM}(no spam/clam heavy services)${NC}"
  read -rp "  Continue setup? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }

  export DEBIAN_FRONTEND=noninteractive
  if command -v debconf-set-selections >/dev/null 2>&1; then
    echo "postfix postfix/mailname string ${domain}" | debconf-set-selections
    echo "postfix postfix/main_mailer_type string Internet Site" | debconf-set-selections
  fi

  info "Installing required packages..."
  apt-get update -qq
  apt-get install -y -qq postfix dovecot-core dovecot-imapd opendkim opendkim-tools libsasl2-modules ca-certificates

  echo "$domain" > /etc/mailname
  _mail_ensure_vmail_user

  touch /etc/postfix/vmail_domains /etc/postfix/vmail_mailboxes /etc/postfix/vmail_aliases
  chmod 644 /etc/postfix/vmail_domains /etc/postfix/vmail_mailboxes /etc/postfix/vmail_aliases
  _mail_upsert_map_file /etc/postfix/vmail_domains "$domain" "OK"
  _mail_upsert_map_file /etc/postfix/vmail_aliases "postmaster@${domain}" "root"
  _mail_postmap_refresh

  local cert_pair cert_file key_file
  cert_pair=$(_mail_resolve_cert_paths "$mail_host")
  cert_file="${cert_pair%%|*}"
  key_file="${cert_pair##*|}"

  info "Configuring Postfix..."
  postconf -e "myhostname = ${mail_host}"
  postconf -e "mydomain = ${domain}"
  postconf -e "myorigin = \$mydomain"
  postconf -e "mydestination = localhost"
  postconf -e "inet_interfaces = all"
  postconf -e "inet_protocols = ipv4"
  postconf -e "mailbox_size_limit = 0"
  postconf -e "recipient_delimiter = +"
  postconf -e "append_dot_mydomain = no"
  postconf -e "biff = no"
  postconf -e "readme_directory = no"
  postconf -e "compatibility_level = 2"
  postconf -e "virtual_mailbox_domains = hash:/etc/postfix/vmail_domains"
  postconf -e "virtual_mailbox_base = ${MAIL_BASE_DIR}"
  postconf -e "virtual_mailbox_maps = hash:/etc/postfix/vmail_mailboxes"
  postconf -e "virtual_alias_maps = hash:/etc/postfix/vmail_aliases"
  postconf -e "virtual_uid_maps = static:${MAIL_VMAIL_UID}"
  postconf -e "virtual_gid_maps = static:${MAIL_VMAIL_GID}"
  postconf -e "virtual_minimum_uid = ${MAIL_VMAIL_UID}"
  postconf -e "smtpd_sasl_type = dovecot"
  postconf -e "smtpd_sasl_path = private/auth"
  postconf -e "smtpd_sasl_auth_enable = yes"
  postconf -e "broken_sasl_auth_clients = yes"
  postconf -e "smtpd_relay_restrictions = permit_mynetworks,permit_sasl_authenticated,reject_unauth_destination"
  postconf -e "smtpd_recipient_restrictions = permit_mynetworks,permit_sasl_authenticated,reject_unauth_destination"
  postconf -e "disable_vrfy_command = yes"
  postconf -e "strict_rfc821_envelopes = yes"
  postconf -e "smtpd_tls_security_level = may"
  postconf -e "smtpd_tls_auth_only = yes"
  postconf -e "smtp_tls_security_level = may"
  postconf -e "smtpd_tls_cert_file = ${cert_file}"
  postconf -e "smtpd_tls_key_file = ${key_file}"
  postconf -e "milter_default_action = accept"
  postconf -e "milter_protocol = 6"
  postconf -e "smtpd_milters = inet:127.0.0.1:8891"
  postconf -e "non_smtpd_milters = inet:127.0.0.1:8891"
  _mail_ensure_submission_service

  info "Configuring Dovecot..."
  cat > /etc/dovecot/conf.d/90-accountinox-mail.conf <<EOF
mail_location = maildir:${MAIL_BASE_DIR}/%d/%n
disable_plaintext_auth = yes
auth_mechanisms = plain login

passdb {
  driver = passwd-file
  args = scheme=SHA512-CRYPT ${MAIL_DOVECOT_USERS_FILE}
}

userdb {
  driver = static
  args = uid=${MAIL_VMAIL_USER} gid=${MAIL_VMAIL_GROUP} home=${MAIL_BASE_DIR}/%d/%n
}

service auth {
  unix_listener /var/spool/postfix/private/auth {
    mode = 0660
    user = postfix
    group = postfix
  }
}

service imap-login {
  inet_listener imap {
    port = 0
  }
  inet_listener imaps {
    port = 993
  }
}

service pop3-login {
  inet_listener pop3 {
    port = 0
  }
  inet_listener pop3s {
    port = 0
  }
}

ssl = required
ssl_cert = <${cert_file}
ssl_key = <${key_file}
EOF

  touch "$MAIL_DOVECOT_USERS_FILE"
  chown root:dovecot "$MAIL_DOVECOT_USERS_FILE" 2>/dev/null || true
  chmod 640 "$MAIL_DOVECOT_USERS_FILE"

  info "Configuring OpenDKIM..."
  mkdir -p "/etc/opendkim/keys/${domain}"
  cat > /etc/opendkim.conf <<'EOF'
Syslog                  yes
UMask                   002
Canonicalization        relaxed/simple
Mode                    sv
SubDomains              no
AutoRestart             yes
Background              yes
DNSTimeout              5
SignatureAlgorithm      rsa-sha256
UserID                  opendkim
Socket                  inet:8891@127.0.0.1
PidFile                 /run/opendkim/opendkim.pid
KeyTable                /etc/opendkim/key.table
SigningTable            refile:/etc/opendkim/signing.table
ExternalIgnoreList      /etc/opendkim/trusted.hosts
InternalHosts           /etc/opendkim/trusted.hosts
EOF

  if [[ -f /etc/default/opendkim ]]; then
    if grep -q '^SOCKET=' /etc/default/opendkim 2>/dev/null; then
      sed -i 's|^SOCKET=.*|SOCKET="inet:8891@127.0.0.1"|' /etc/default/opendkim
    else
      echo 'SOCKET="inet:8891@127.0.0.1"' >> /etc/default/opendkim
    fi
  fi

  if [[ ! -f "/etc/opendkim/keys/${domain}/${MAIL_DKIM_SELECTOR}.private" ]]; then
    opendkim-genkey -b 2048 -D "/etc/opendkim/keys/${domain}" -d "$domain" -s "$MAIL_DKIM_SELECTOR"
  fi
  chown -R opendkim:opendkim /etc/opendkim/keys
  chmod 700 "/etc/opendkim/keys/${domain}"
  chmod 600 "/etc/opendkim/keys/${domain}/${MAIL_DKIM_SELECTOR}.private"

  cat > /etc/opendkim/key.table <<EOF
${MAIL_DKIM_SELECTOR}._domainkey.${domain} ${domain}:${MAIL_DKIM_SELECTOR}:/etc/opendkim/keys/${domain}/${MAIL_DKIM_SELECTOR}.private
EOF
  cat > /etc/opendkim/signing.table <<EOF
*@${domain} ${MAIL_DKIM_SELECTOR}._domainkey.${domain}
EOF
  cat > /etc/opendkim/trusted.hosts <<'EOF'
127.0.0.1
localhost
EOF

  systemctl enable postfix dovecot opendkim >/dev/null 2>&1 || true
  _mail_reload_services

  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
    ufw allow 25/tcp >/dev/null 2>&1 || true
    ufw allow 587/tcp >/dev/null 2>&1 || true
    ufw allow 993/tcp >/dev/null 2>&1 || true
  fi

  success "Mail server setup completed."
  info "Next: create mailbox (e.g. noreply@${domain}) from mailserver menu."
  _mail_dns_instructions "$domain" "$mail_host"
}

_mailserver_create_mailbox() {
  local email="${1:-}" password="${2:-}"
  local configured_domain
  configured_domain=$(_mail_first_domain)
  [[ -z "$email" ]] && read -rp "  Mailbox email (e.g. noreply@${configured_domain:-example.com}): " email
  if ! _mail_validate_email "$email"; then
    fail "Invalid email address."
    return 1
  fi
  if [[ -z "$password" ]]; then
    read -rsp "  Password (min 10 chars): " password; echo
  fi
  [[ ${#password} -lt 10 ]] && { fail "Password must be at least 10 characters."; return 1; }

  local localpart domain hash
  localpart="${email%@*}"
  domain="${email#*@}"
  [[ -n "$configured_domain" && "$domain" != "$configured_domain" ]] && warn "Configured domain is ${configured_domain}; adding mailbox for ${domain}."

  _mail_upsert_map_file /etc/postfix/vmail_domains "$domain" "OK"
  hash=$(doveadm pw -s SHA512-CRYPT -p "$password")
  _mail_upsert_dovecot_user "$email" "$hash"
  _mail_upsert_map_file /etc/postfix/vmail_mailboxes "$email" "${domain}/${localpart}/"
  mkdir -p "${MAIL_BASE_DIR}/${domain}/${localpart}"
  chown -R "${MAIL_VMAIL_USER}:${MAIL_VMAIL_GROUP}" "${MAIL_BASE_DIR}/${domain}/${localpart}"
  chmod 700 "${MAIL_BASE_DIR}/${domain}/${localpart}"
  _mail_postmap_refresh
  systemctl reload postfix dovecot
  success "Mailbox created/updated: ${email}"
}

_mailserver_reset_password() {
  local email="${1:-}" password="${2:-}"
  [[ -z "$email" ]] && read -rp "  Mailbox email: " email
  if ! _mail_validate_email "$email"; then
    fail "Invalid email address."
    return 1
  fi
  if [[ -z "$password" ]]; then
    read -rsp "  New password: " password; echo
  fi
  [[ ${#password} -lt 10 ]] && { fail "Password must be at least 10 characters."; return 1; }
  local hash
  hash=$(doveadm pw -s SHA512-CRYPT -p "$password")
  _mail_upsert_dovecot_user "$email" "$hash"
  systemctl reload dovecot
  success "Password updated: ${email}"
}

_mailserver_delete_mailbox() {
  local email="${1:-}"
  [[ -z "$email" ]] && read -rp "  Mailbox email to delete: " email
  if ! _mail_validate_email "$email"; then
    fail "Invalid email address."
    return 1
  fi
  local localpart domain
  localpart="${email%@*}"
  domain="${email#*@}"
  echo -e "  ${RED}This will remove mailbox account: ${email}${NC}"
  read -rp "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }

  _mail_remove_dovecot_user "$email"
  _mail_remove_map_key /etc/postfix/vmail_mailboxes "$email"
  _mail_postmap_refresh
  read -rp "  Delete mailbox data directory too? [y/N] " del_data
  if [[ "$del_data" =~ ^[Yy]$ ]]; then
    rm -rf "${MAIL_BASE_DIR}/${domain}/${localpart}"
    info "Mailbox data removed."
  fi
  systemctl reload postfix dovecot
  success "Mailbox deleted: ${email}"
}

_mailserver_list_mailboxes() {
  header "Mailboxes"
  if [[ ! -f "$MAIL_DOVECOT_USERS_FILE" ]]; then
    warn "No mailbox file found: $MAIL_DOVECOT_USERS_FILE"
    return 0
  fi
  local count
  count=$(awk -F: 'NF && $1 !~ /^#/ {print $1}' "$MAIL_DOVECOT_USERS_FILE" | wc -l)
  if [[ "$count" -eq 0 ]]; then
    info "No mailboxes configured."
    return 0
  fi
  awk -F: 'NF && $1 !~ /^#/ {print "  - " $1}' "$MAIL_DOVECOT_USERS_FILE"
  echo ""
  info "Total mailboxes: $count"
}

_mailserver_status() {
  header "Mail Server Status"
  local services=(postfix dovecot opendkim)
  for svc in "${services[@]}"; do
    local st color="$RED"
    st=$(systemctl is-active "$svc" 2>/dev/null || true)
    st="${st%%$'\n'*}"
    [[ -z "$st" ]] && st="inactive"
    [[ "$st" == "active" ]] && color="$GREEN"
    printf "  %-10s ${color}%-10s${NC}\n" "$svc" "$st"
  done
  echo ""
  info "Listening ports (mail related):"
  ss -tlnp 2>/dev/null | grep -E ':(25|465|587|993)\b' | awk '{print "  " $4 " -> " $7}' || true
  echo ""
  _mail_relay_status
  echo ""
  _mailserver_list_mailboxes
}

_mailserver_apply_app_env() {
  header "Apply Local SMTP to Django .env"
  local from_addr="${1:-}"
  local guessed_domain
  guessed_domain=$(_mail_first_domain)
  [[ -z "$from_addr" ]] && read -rp "  DEFAULT_FROM_EMAIL [noreply@${guessed_domain:-example.com}]: " from_addr
  [[ -z "$from_addr" ]] && from_addr="noreply@${guessed_domain:-example.com}"

  cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
  _env_upsert "EMAIL_BACKEND" "django.core.mail.backends.smtp.EmailBackend"
  _env_upsert "EMAIL_HOST" "127.0.0.1"
  _env_upsert "EMAIL_PORT" "25"
  _env_upsert "EMAIL_USE_TLS" "False"
  _env_upsert "EMAIL_USE_SSL" "False"
  _env_upsert "EMAIL_HOST_USER" ""
  _env_upsert "EMAIL_HOST_PASSWORD" ""
  _env_upsert "DEFAULT_FROM_EMAIL" "$from_addr"
  _env_upsert "EMAIL_TIMEOUT" "20"
  success "Django SMTP configured to local Postfix (127.0.0.1:25)."
  echo -e "  ${YELLOW}Restart app: sudo bash $0 restart${NC}"
}

_mailserver_send_probe() {
  local to="${1:-}" from="${2:-}"
  local domain
  domain=$(_mail_first_domain)
  [[ -z "$from" ]] && from="noreply@${domain:-example.com}"
  [[ -z "$to" ]] && read -rp "  Recipient email for test: " to
  if ! _mail_validate_email "$to"; then
    fail "Invalid recipient email."
    return 1
  fi
  header "Sending Mail Server Probe"
  local now
  now=$(date '+%Y-%m-%d %H:%M:%S')
  /usr/sbin/sendmail -t <<EOF
From: ${from}
To: ${to}
Subject: [Accountinox] Mail server probe

Hello,
This is a test email from Accountinox mail server.
Time: ${now}
EOF
  success "Probe queued. Check recipient inbox/spam and logs."
}

_mail_relay_status() {
  header "SMTP Relay Status"
  local relayhost sasl_enabled sasl_map tls_level
  relayhost=$(postconf -h relayhost 2>/dev/null || true)
  sasl_enabled=$(postconf -h smtp_sasl_auth_enable 2>/dev/null || true)
  sasl_map=$(postconf -h smtp_sasl_password_maps 2>/dev/null || true)
  tls_level=$(postconf -h smtp_tls_security_level 2>/dev/null || true)

  echo -e "  relayhost: ${CYAN}${relayhost:-"(empty)"}${NC}"
  echo -e "  smtp_sasl_auth_enable: ${CYAN}${sasl_enabled:-"(empty)"}${NC}"
  echo -e "  smtp_sasl_password_maps: ${CYAN}${sasl_map:-"(empty)"}${NC}"
  echo -e "  smtp_tls_security_level: ${CYAN}${tls_level:-"(empty)"}${NC}"

  if [[ -f "$MAIL_RELAY_CRED_FILE" ]]; then
    echo -e "  creds file: ${CYAN}${MAIL_RELAY_CRED_FILE}${NC} (${GREEN}present${NC})"
  else
    echo -e "  creds file: ${CYAN}${MAIL_RELAY_CRED_FILE}${NC} (${YELLOW}missing${NC})"
  fi
}

_mail_relay_configure() {
  header "Configure SMTP Relay for Postfix"
  echo -e "  ${CYAN}1${NC}) Brevo (recommended)"
  echo -e "  ${CYAN}2${NC}) Mailgun"
  echo -e "  ${CYAN}3${NC}) SMTP2GO"
  echo -e "  ${CYAN}4${NC}) Custom relay"
  echo -e "  ${CYAN}0${NC}) Back"
  read -rp "$(echo -e "${CYAN}▸${NC} Provider: ")" provider

  local relay_host relay_port user_hint
  case "$provider" in
    1) relay_host="smtp-relay.brevo.com"; relay_port="587"; user_hint="apikey" ;;
    2) relay_host="smtp.mailgun.org"; relay_port="587"; user_hint="postmaster@your-domain.com" ;;
    3) relay_host="mail.smtp2go.com"; relay_port="587"; user_hint="smtp2go-username" ;;
    4) relay_host=""; relay_port="587"; user_hint="" ;;
    0|*) return 0 ;;
  esac

  local input relay_user relay_pass
  read -rp "  Relay host [${relay_host:-smtp.example.com}]: " input
  relay_host="${input:-${relay_host:-smtp.example.com}}"
  read -rp "  Relay port [${relay_port}]: " input
  relay_port="${input:-$relay_port}"
  read -rp "  Relay username [${user_hint:-required}]: " relay_user
  read -rsp "  Relay password/API key: " relay_pass; echo

  if [[ -z "$relay_host" || -z "$relay_port" || -z "$relay_user" || -z "$relay_pass" ]]; then
    fail "Relay setup canceled: host/port/username/password are required."
    return 1
  fi
  if [[ ! "$relay_port" =~ ^[0-9]+$ ]]; then
    fail "Invalid relay port: $relay_port"
    return 1
  fi

  cp /etc/postfix/main.cf "/etc/postfix/main.cf.bak.$(date +%s)"
  [[ -f "$MAIL_RELAY_CRED_FILE" ]] && cp "$MAIL_RELAY_CRED_FILE" "${MAIL_RELAY_CRED_FILE}.bak.$(date +%s)"

  cat > "$MAIL_RELAY_CRED_FILE" <<EOF
[${relay_host}]:${relay_port} ${relay_user}:${relay_pass}
EOF
  postmap "$MAIL_RELAY_CRED_FILE"
  chown root:root "$MAIL_RELAY_CRED_FILE" "${MAIL_RELAY_CRED_FILE}.db"
  chmod 600 "$MAIL_RELAY_CRED_FILE" "${MAIL_RELAY_CRED_FILE}.db"

  postconf -e "relayhost = [${relay_host}]:${relay_port}"
  postconf -e "smtp_sasl_auth_enable = yes"
  postconf -e "smtp_sasl_password_maps = hash:${MAIL_RELAY_CRED_FILE}"
  postconf -e "smtp_sasl_security_options = noanonymous"
  postconf -e "smtp_tls_security_level = encrypt"
  postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"

  systemctl restart postfix
  success "SMTP relay configured and postfix restarted."
  info "Relay: [${relay_host}]:${relay_port}"
}

_mail_relay_disable() {
  header "Disable SMTP Relay"
  echo -e "  ${YELLOW}This will disable relayhost and return Postfix to direct outbound delivery.${NC}"
  echo -e "  ${YELLOW}If your server blocks outbound port 25, external delivery will fail again.${NC}"
  read -rp "  Continue? [y/N] " confirm
  [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }

  cp /etc/postfix/main.cf "/etc/postfix/main.cf.bak.$(date +%s)"
  postconf -e "relayhost ="
  postconf -e "smtp_sasl_auth_enable = no"
  postconf -e "smtp_sasl_password_maps ="
  postconf -e "smtp_sasl_security_options = noanonymous"
  postconf -e "smtp_tls_security_level = may"
  postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"
  systemctl restart postfix
  success "SMTP relay disabled."
}

_mail_tail_logs() {
  if [[ -f /var/log/mail.log ]]; then
    tail -n 200 /var/log/mail.log
    return 0
  fi
  if [[ -f /var/log/maillog ]]; then
    tail -n 200 /var/log/maillog
    return 0
  fi
  journalctl -u postfix -u dovecot -u opendkim -n 200 --no-pager
}

cmd_mailserver() {
  local subcmd="${1:-menu}"
  case "$subcmd" in
    setup)         _mailserver_setup "${2:-}" "${3:-}" ;;
    status)        _mailserver_status ;;
    create)        _mailserver_create_mailbox "${2:-}" "${3:-}" ;;
    passwd|password) _mailserver_reset_password "${2:-}" "${3:-}" ;;
    delete|remove) _mailserver_delete_mailbox "${2:-}" ;;
    list)          _mailserver_list_mailboxes ;;
    dns)           _mail_dns_instructions "${2:-}" "${3:-}" ;;
    app-env|apply-env) _mailserver_apply_app_env "${2:-}" ;;
    test|probe)    _mailserver_send_probe "${2:-}" "${3:-}" ;;
    relay|relay-setup) _mail_relay_configure ;;
    relay-status)  _mail_relay_status ;;
    relay-disable) _mail_relay_disable ;;
    restart)       _mail_reload_services && success "Mail services restarted" ;;
    logs)          _mail_tail_logs ;;
    menu|*)
      echo ""
      echo -e "  ${BOLD}Mail Server (Lightweight)${NC}"
      echo -e "  ${CYAN}1${NC}) Setup lightweight mail server (Postfix+Dovecot+DKIM)"
      echo -e "  ${CYAN}2${NC}) Status"
      echo -e "  ${CYAN}3${NC}) Create mailbox"
      echo -e "  ${CYAN}4${NC}) Reset mailbox password"
      echo -e "  ${CYAN}5${NC}) List mailboxes"
      echo -e "  ${CYAN}6${NC}) Delete mailbox"
      echo -e "  ${CYAN}7${NC}) Show DNS records (MX/SPF/DKIM/DMARC)"
      echo -e "  ${CYAN}8${NC}) Apply local SMTP to Django .env"
      echo -e "  ${CYAN}9${NC}) Send probe email"
      echo -e "  ${CYAN}10${NC}) Configure SMTP relay (recommended)"
      echo -e "  ${CYAN}11${NC}) Relay status"
      echo -e "  ${CYAN}12${NC}) Disable relay"
      echo -e "  ${CYAN}13${NC}) Restart mail services"
      echo -e "  ${CYAN}14${NC}) Mail logs"
      echo -e "  ${CYAN}0${NC}) Back"
      echo ""
      read -rp "$(echo -e "${CYAN}▸${NC} Choice: ")" mchoice
      case "$mchoice" in
        1)  _mailserver_setup ;;
        2)  _mailserver_status ;;
        3)  _mailserver_create_mailbox ;;
        4)  _mailserver_reset_password ;;
        5)  _mailserver_list_mailboxes ;;
        6)  _mailserver_delete_mailbox ;;
        7)  _mail_dns_instructions ;;
        8)  _mailserver_apply_app_env ;;
        9)  _mailserver_send_probe ;;
        10) _mail_relay_configure ;;
        11) _mail_relay_status ;;
        12) _mail_relay_disable ;;
        13) _mail_reload_services && success "Mail services restarted" ;;
        14) _mail_tail_logs ;;
        0|*) return 0 ;;
      esac
      ;;
  esac
}

cmd_env() {
  local subcmd="${1:-menu}"

  [[ ! -f "$ENVFILE" ]] && { fail ".env not found: $ENVFILE"; return 1; }

  case "$subcmd" in
    show)
      header ".env Contents"
      echo -e "  ${DIM}$ENVFILE${NC}"
      echo ""
      local line_num=0
      while IFS= read -r line || [[ -n "$line" ]]; do
        line_num=$((line_num + 1))
        if [[ -z "$line" ]]; then
          echo ""
        elif [[ "$line" =~ ^# ]]; then
          echo -e "  ${DIM}${line}${NC}"
        else
          local key="${line%%=*}"
          local value="${line#*=}"
          # Mask sensitive values
          if [[ "$key" =~ (SECRET|PASS|KEY|DSN|TOKEN) ]]; then
            local visible="${value:0:6}"
            echo -e "  ${CYAN}${key}${NC}=${visible}${DIM}••••••••${NC}"
          else
            echo -e "  ${CYAN}${key}${NC}=${value}"
          fi
        fi
      done < "$ENVFILE"
      echo ""
      info "Permissions: $(stat -c '%a' "$ENVFILE" 2>/dev/null || echo '?')"
      ;;

    get)
      local key="${2:-}"
      [[ -z "$key" ]] && { read -rp "  Variable name: " key; }
      [[ -z "$key" ]] && { fail "Key required"; return 1; }
      local match
      match=$(grep -E "^${key}=" "$ENVFILE" 2>/dev/null | head -1)
      if [[ -n "$match" ]]; then
        echo -e "  ${CYAN}${match}${NC}"
      else
        warn "$key not found in .env"
      fi
      ;;

    set)
      local key="${2:-}"
      local value="${3:-}"
      [[ -z "$key" ]] && { read -rp "  Variable name: " key; }
      [[ -z "$key" ]] && { fail "Key required"; return 1; }
      [[ -z "$value" ]] && { read -rp "  Value: " value; }

      # Validate key format
      if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        fail "Invalid variable name: $key"
        return 1
      fi

      # Backup before edit
      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"

      if grep -qE "^${key}=" "$ENVFILE" 2>/dev/null; then
        # Update existing
        local old_value
        old_value=$(grep -E "^${key}=" "$ENVFILE" | head -1 | cut -d= -f2-)
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENVFILE"
        success "Updated: $key"
        if [[ "$key" =~ (SECRET|PASS|KEY|DSN|TOKEN) ]]; then
          info "Old: ${old_value:0:6}•••• → New: ${value:0:6}••••"
        else
          info "Old: $old_value → New: $value"
        fi
      else
        # Add new
        echo "${key}=${value}" >> "$ENVFILE"
        success "Added: $key"
      fi

      chmod 600 "$ENVFILE"
      chown "$SERVICE_USER":"$SERVICE_USER" "$ENVFILE" 2>/dev/null || true

      echo -e "  ${YELLOW}Restart the app to apply changes: sudo bash $0 restart${NC}"
      ;;

    delete)
      local key="${2:-}"
      [[ -z "$key" ]] && { read -rp "  Variable to remove: " key; }
      [[ -z "$key" ]] && { fail "Key required"; return 1; }

      if ! grep -qE "^${key}=" "$ENVFILE" 2>/dev/null; then
        warn "$key not found in .env"
        return 1
      fi

      # Safety: prevent deleting critical vars
      local critical_vars="DEBUG DJANGO_SECRET_KEY ALLOWED_HOSTS FERNET_KEY OTP_HMAC_KEY DATABASE_URL"
      for cv in $critical_vars; do
        if [[ "$key" == "$cv" ]]; then
          fail "Cannot delete critical variable: $key"
          return 1
        fi
      done

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      sed -i "/^${key}=/d" "$ENVFILE"
      success "Removed: $key"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    toggle-debug)
      local current
      current=$(grep -E '^DEBUG=' "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2)
      if [[ "$current" == "0" || "$current" == "False" ]]; then
        echo -e "  ${RED}WARNING: Enabling DEBUG in production exposes sensitive info!${NC}"
        read -rp "  Enable DEBUG? [y/N] " confirm
        [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }
        sed -i 's/^DEBUG=.*/DEBUG=1/' "$ENVFILE"
        warn "DEBUG enabled — remember to disable after debugging!"
      else
        sed -i 's/^DEBUG=.*/DEBUG=0/' "$ENVFILE"
        success "DEBUG disabled"
      fi
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    domain)
      local new_domain="${2:-}"
      [[ -z "$new_domain" ]] && { read -rp "  New domain: " new_domain; }
      [[ -z "$new_domain" ]] && { fail "Domain required"; return 1; }

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"

      sed -i "s|^ALLOWED_HOSTS=.*|ALLOWED_HOSTS=${new_domain},www.${new_domain}|" "$ENVFILE"
      sed -i "s|^SITE_URL=.*|SITE_URL=https://${new_domain}|" "$ENVFILE"
      sed -i "s|^SITE_BASE_URL=.*|SITE_BASE_URL=https://${new_domain}|" "$ENVFILE"
      sed -i "s|^CSRF_TRUSTED_ORIGINS=.*|CSRF_TRUSTED_ORIGINS=https://${new_domain},https://www.${new_domain}|" "$ENVFILE"

      success "Domain updated to: $new_domain"
      info "Updated: ALLOWED_HOSTS, SITE_URL, SITE_BASE_URL, CSRF_TRUSTED_ORIGINS"
      echo -e "  ${YELLOW}Don't forget to:${NC}"
      echo -e "    1. Update Nginx config: /etc/nginx/sites-available/${APP_NAME}"
      echo -e "    2. Obtain SSL: sudo certbot --nginx -d ${new_domain}"
      echo -e "    3. Restart: sudo bash $0 restart"
      ;;

    regen-secret)
      header "Regenerate Secret Key"
      echo -e "  ${YELLOW}This will invalidate all existing sessions (users will be logged out).${NC}"
      read -rp "  Continue? [y/N] " confirm
      [[ "$confirm" =~ ^[Yy]$ ]] || { info "Cancelled"; return 0; }

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      source "$VENV_DIR/bin/activate"
      local new_key
      new_key=$("$VENV_DIR/bin/python" -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
      deactivate
      sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${new_key}|" "$ENVFILE"
      success "Secret key regenerated"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    email)
      local email_sub="${2:-menu}"
      case "$email_sub" in
        setup|configure) _email_configure_wizard ;;
        status|show) _email_show_status ;;
        test) _email_send_test "${3:-}" ;;
        console) _email_enable_console_backend ;;
        reset) _email_reset_settings ;;
        menu|*)
          echo ""
          echo -e "  ${BOLD}Email Setup & Management${NC}"
          echo -e "  ${CYAN}1${NC}) Status / validation"
          echo -e "  ${CYAN}2${NC}) Setup SMTP (provider wizard)"
          echo -e "  ${CYAN}3${NC}) Send test email"
          echo -e "  ${CYAN}4${NC}) Enable console backend (no real send)"
          echo -e "  ${CYAN}5${NC}) Reset email settings from .env"
          echo -e "  ${CYAN}0${NC}) Back"
          echo ""
          read -rp "$(echo -e "${CYAN}▸${NC} Choice: ")" em_choice
          case "$em_choice" in
            1) _email_show_status ;;
            2) _email_configure_wizard ;;
            3) _email_send_test ;;
            4) _email_enable_console_backend ;;
            5) _email_reset_settings ;;
            0|*) return 0 ;;
          esac
          ;;
      esac
      ;;

    backup-list)
      header ".env Backups"
      local backups
      backups=$(ls -lt "${ENVFILE}".bak.* 2>/dev/null | head -10)
      if [[ -n "$backups" ]]; then
        echo "$backups" | awk '{printf "  %s %s %s  %s\n", $6, $7, $8, $NF}'
      else
        info "No backups found"
      fi
      ;;

    restore)
      header "Restore .env from backup"
      local backups
      backups=$(ls -t "${ENVFILE}".bak.* 2>/dev/null)
      if [[ -z "$backups" ]]; then
        fail "No backups found"
        return 1
      fi
      echo "  Available backups:"
      local i=1
      while IFS= read -r bfile; do
        local ts
        ts=$(basename "$bfile" | sed 's/.*\.bak\.//')
        echo -e "  ${CYAN}${i}${NC}) $(date -d @"$ts" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "$ts")"
        i=$((i + 1))
      done <<< "$backups"
      read -rp "  Choose backup number: " bnum
      local chosen
      chosen=$(echo "$backups" | sed -n "${bnum}p")
      if [[ -n "$chosen" ]]; then
        cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"  # backup current first
        cp "$chosen" "$ENVFILE"
        chmod 600 "$ENVFILE"
        chown "$SERVICE_USER":"$SERVICE_USER" "$ENVFILE" 2>/dev/null || true
        success "Restored from $(basename "$chosen")"
        echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      else
        fail "Invalid selection"
      fi
      ;;

    google)
      header "Google OAuth Configuration"
      echo -e "  Current settings:"
      grep -E '^GOOGLE_' "$ENVFILE" 2>/dev/null | while read -r line; do
        local k="${line%%=*}"; local v="${line#*=}"
        if [[ -n "$v" ]]; then
          echo -e "    ${CYAN}${k}${NC}=${v:0:8}${DIM}••••${NC}"
        else
          echo -e "    ${CYAN}${k}${NC}=${DIM}(empty)${NC}"
        fi
      done
      echo ""
      read -rp "  Configure Google OAuth? [y/N] " doit
      [[ "$doit" =~ ^[Yy]$ ]] || return 0

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      read -rp "  Google Client ID: " gcid
      read -rp "  Google Secret: " gsec

      _env_upsert "GOOGLE_CLIENT_ID" "$gcid"
      _env_upsert "GOOGLE_SECRET" "$gsec"

      success "Google OAuth configured"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    sms)
      header "IPPanel SMS Configuration"
      echo -e "  ${DIM}See docs/OTP_IPPANEL_SETUP.md for details${NC}"
      echo -e "  Current settings:"
      grep -E '^IPPANEL_|^KAVENEGAR_' "$ENVFILE" 2>/dev/null | while read -r line; do
        local k="${line%%=*}"; local v="${line#*=}"
        if [[ "$k" =~ KEY ]]; then
          echo -e "    ${CYAN}${k}${NC}=${v:0:6}${DIM}••••${NC}"
        else
          echo -e "    ${CYAN}${k}${NC}=${v:-${DIM}(empty)${NC}}"
        fi
      done
      echo ""
      read -rp "  Configure IPPanel SMS? [y/N] " doit
      [[ "$doit" =~ ^[Yy]$ ]] || return 0

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      read -rp "  IPPANEL_API_KEY: " ipp_key
      read -rp "  IPPANEL_ORIGINATOR (sender number e.g. +983000505): " ipp_orig
      read -rp "  IPPANEL_PATTERN_CODE (OTP pattern): " ipp_pat
      read -rp "  IPPANEL_SENDER (optional, legacy): " ipp_send

      _env_upsert "IPPANEL_API_KEY" "$ipp_key"
      _env_upsert "IPPANEL_ORIGINATOR" "$ipp_orig"
      _env_upsert "IPPANEL_PATTERN_CODE" "$ipp_pat"
      [[ -n "$ipp_send" ]] && _env_upsert "IPPANEL_SENDER" "$ipp_send"

      success "IPPanel SMS configured"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    push)
      header "Web Push (VAPID) Configuration"
      echo -e "  Current settings:"
      grep -E '^(SUPPORT_PUSH_ENABLED|VAPID_)' "$ENVFILE" 2>/dev/null | while read -r line; do
        local k="${line%%=*}"; local v="${line#*=}"
        if [[ "$k" =~ KEY ]]; then
          echo -e "    ${CYAN}${k}${NC}=${v:0:8}${DIM}••••${NC}"
        else
          echo -e "    ${CYAN}${k}${NC}=${v:-${DIM}(empty)${NC}}"
        fi
      done
      echo ""
      read -rp "  Configure VAPID push? [y/N] " doit
      [[ "$doit" =~ ^[Yy]$ ]] || return 0

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"

      echo -e "  ${DIM}Generate keys: python -c \"from pywebpush import webpush; from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v)\"${NC}"
      read -rp "  VAPID_PUBLIC_KEY: " vpub
      read -rp "  VAPID_PRIVATE_KEY: " vpriv
      read -rp "  VAPID_SUBJECT (mailto:you@domain.com): " vsub
      read -rp "  Enable push? [Y/n]: " push_en
      push_en="$([[ "$push_en" =~ ^[Nn]$ ]] && echo '0' || echo '1')"

      _env_upsert "SUPPORT_PUSH_ENABLED" "$push_en"
      _env_upsert "VAPID_PUBLIC_KEY" "$vpub"
      _env_upsert "VAPID_PRIVATE_KEY" "$vpriv"
      _env_upsert "VAPID_SUBJECT" "$vsub"

      success "VAPID push configured"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    payment)
      header "Payment Gateway Configuration"
      echo -e "  Current settings:"
      grep -E '^(ZARINPAL_|ZIBAL_)' "$ENVFILE" 2>/dev/null | while read -r line; do
        local k="${line%%=*}"; local v="${line#*=}"
        echo -e "    ${CYAN}${k}${NC}=${v:0:8}${DIM}••••${NC}"
      done || info "No payment gateways configured"
      echo ""
      echo -e "  ${CYAN}1${NC}) ZarinPal    ${CYAN}2${NC}) Zibal    ${CYAN}0${NC}) Back"
      read -rp "$(echo -e "${CYAN}▸${NC} Choice: ")" pchoice
      case "$pchoice" in
        1)
          cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
          read -rp "  ZarinPal Merchant ID: " zp_mid
          _env_upsert "ZARINPAL_MERCHANT_ID" "$zp_mid"
          success "ZarinPal configured"
          ;;
        2)
          cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
          read -rp "  Zibal Merchant ID: " zb_mid
          _env_upsert "ZIBAL_MERCHANT_ID" "$zb_mid"
          success "Zibal configured"
          ;;
        *) return 0 ;;
      esac
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    redis)
      header "Redis Cache Configuration"
      local current_redis
      current_redis=$(grep -E '^REDIS_URL=' "$ENVFILE" 2>/dev/null | head -1 | cut -d= -f2-)
      if [[ -n "$current_redis" ]]; then
        echo -e "  Current: ${CYAN}${current_redis}${NC}"
      else
        echo -e "  Current: ${DIM}(not configured — using locmem)${NC}"
      fi
      echo ""
      read -rp "  Redis URL (default redis://127.0.0.1:6379/0): " redis_url
      redis_url="${redis_url:-redis://127.0.0.1:6379/0}"
      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      _env_upsert "REDIS_URL" "$redis_url"
      success "Redis URL set to: $redis_url"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    branding)
      header "Admin Panel Branding"
      echo -e "  ${DIM}Set custom colors for the admin panel (hex codes)${NC}"
      echo -e "  Current:"
      grep -E '^ADMIN_BRAND_' "$ENVFILE" 2>/dev/null | while read -r line; do
        echo -e "    ${CYAN}${line%%=*}${NC}=${line#*=}"
      done || info "Using default colors"
      echo ""
      read -rp "  Configure branding? [y/N] " doit
      [[ "$doit" =~ ^[Yy]$ ]] || return 0

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      read -rp "  Primary color (e.g. #1a73e8): " bp
      read -rp "  Secondary color (e.g. #1557b0): " bs
      read -rp "  Accent color (e.g. #34a853): " ba

      [[ -n "$bp" ]] && _env_upsert "ADMIN_BRAND_PRIMARY" "$bp"
      [[ -n "$bs" ]] && _env_upsert "ADMIN_BRAND_SECONDARY" "$bs"
      [[ -n "$ba" ]] && _env_upsert "ADMIN_BRAND_ACCENT" "$ba"

      success "Admin branding updated"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    ssl)
      header "SSL / HSTS Settings"
      echo -e "  Current:"
      grep -E '^(SECURE_|SESSION_COOKIE_SECURE|CSRF_COOKIE_SECURE|CSRF_TRUSTED)' "$ENVFILE" 2>/dev/null | while read -r line; do
        echo -e "    ${CYAN}${line%%=*}${NC}=${line#*=}"
      done || info "No SSL settings configured"
      echo ""
      echo -e "  ${CYAN}1${NC}) Quick setup (recommended defaults)"
      echo -e "  ${CYAN}2${NC}) Custom values"
      echo -e "  ${CYAN}0${NC}) Back"
      read -rp "$(echo -e "${CYAN}▸${NC} Choice: ")" schoice
      case "$schoice" in
        1)
          cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
          _env_upsert "SESSION_COOKIE_SECURE" "True"
          _env_upsert "CSRF_COOKIE_SECURE" "True"
          _env_upsert "SECURE_SSL_REDIRECT" "True"
          _env_upsert "SECURE_HSTS_SECONDS" "31536000"
          _env_upsert "SECURE_HSTS_INCLUDE_SUBDOMAINS" "True"
          _env_upsert "SECURE_HSTS_PRELOAD" "True"
          _env_upsert "SECURE_PROXY_SSL_HEADER" "HTTP_X_FORWARDED_PROTO,https"
          success "SSL hardened with recommended defaults"
          ;;
        2)
          cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
          read -rp "  SECURE_SSL_REDIRECT (True/False): " ssl_r
          read -rp "  SECURE_HSTS_SECONDS (e.g. 3600 or 31536000): " hsts_s
          read -rp "  SECURE_HSTS_INCLUDE_SUBDOMAINS (True/False): " hsts_sub
          read -rp "  SECURE_HSTS_PRELOAD (True/False): " hsts_pre
          read -rp "  SECURE_PROXY_SSL_HEADER (e.g. HTTP_X_FORWARDED_PROTO,https or empty): " proxy_h
          [[ -n "$ssl_r" ]] && _env_upsert "SECURE_SSL_REDIRECT" "$ssl_r"
          [[ -n "$hsts_s" ]] && _env_upsert "SECURE_HSTS_SECONDS" "$hsts_s"
          [[ -n "$hsts_sub" ]] && _env_upsert "SECURE_HSTS_INCLUDE_SUBDOMAINS" "$hsts_sub"
          [[ -n "$hsts_pre" ]] && _env_upsert "SECURE_HSTS_PRELOAD" "$hsts_pre"
          [[ -n "$proxy_h" ]] && _env_upsert "SECURE_PROXY_SSL_HEADER" "$proxy_h"
          _env_upsert "SESSION_COOKIE_SECURE" "True"
          _env_upsert "CSRF_COOKIE_SECURE" "True"
          success "SSL settings updated"
          ;;
        *) return 0 ;;
      esac
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    sentry)
      header "Sentry Error Tracking"
      echo -e "  Current:"
      grep -E '^SENTRY_' "$ENVFILE" 2>/dev/null | while read -r line; do
        local k="${line%%=*}"; local v="${line#*=}"
        if [[ "$k" =~ DSN ]]; then
          echo -e "    ${CYAN}${k}${NC}=${v:0:15}${DIM}••••${NC}"
        else
          echo -e "    ${CYAN}${k}${NC}=${v}"
        fi
      done || info "Sentry not configured"
      echo ""
      read -rp "  Configure Sentry? [y/N] " doit
      [[ "$doit" =~ ^[Yy]$ ]] || return 0

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"
      read -rp "  SENTRY_DSN: " sdsn
      read -rp "  SENTRY_ENVIRONMENT (e.g. production): " senv
      senv="${senv:-production}"

      _env_upsert "SENTRY_DSN" "$sdsn"
      _env_upsert "SENTRY_ENVIRONMENT" "$senv"

      success "Sentry configured"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
      ;;

    menu|*)
      echo ""
      echo -e "  ${BOLD}Environment (.env) Management${NC}"
      echo ""
      echo -e "  ${BOLD}General${NC}"
      echo -e "  ${CYAN} 1${NC}) Show all variables       ${CYAN} 2${NC}) Get a variable"
      echo -e "  ${CYAN} 3${NC}) Set / update variable    ${CYAN} 4${NC}) Delete variable"
      echo -e "  ${CYAN} 5${NC}) Toggle DEBUG             ${CYAN} 6${NC}) Change domain"
      echo -e "  ${CYAN} 7${NC}) Regenerate secret key"
      echo ""
      echo -e "  ${BOLD}Service Wizards${NC}"
      echo -e "  ${CYAN} 8${NC}) Email setup / manage     ${CYAN} 9${NC}) Google OAuth"
      echo -e "  ${CYAN}10${NC}) IPPanel SMS             ${CYAN}11${NC}) Web Push (VAPID)"
      echo -e "  ${CYAN}12${NC}) Payment gateways        ${CYAN}13${NC}) Redis cache"
      echo -e "  ${CYAN}14${NC}) Admin branding           ${CYAN}15${NC}) SSL / HSTS"
      echo -e "  ${CYAN}16${NC}) Sentry error tracking"
      echo ""
      echo -e "  ${BOLD}Backup${NC}"
      echo -e "  ${CYAN}17${NC}) List .env backups        ${CYAN}18${NC}) Restore .env backup"
      echo -e "  ${CYAN} 0${NC}) Back"
      echo ""
      read -rp "$(echo -e "${CYAN}▸${NC} Choice: ")" echoice
      case "$echoice" in
        1)  cmd_env show ;;
        2)  cmd_env get ;;
        3)  cmd_env set ;;
        4)  cmd_env delete ;;
        5)  cmd_env toggle-debug ;;
        6)  cmd_env domain ;;
        7)  cmd_env regen-secret ;;
        8)  cmd_env email ;;
        9)  cmd_env google ;;
        10) cmd_env sms ;;
        11) cmd_env push ;;
        12) cmd_env payment ;;
        13) cmd_env redis ;;
        14) cmd_env branding ;;
        15) cmd_env ssl ;;
        16) cmd_env sentry ;;
        17) cmd_env backup-list ;;
        18) cmd_env restore ;;
        0|*) return 0 ;;
      esac
      ;;
  esac
}

cmd_migrate() {
  header "Running Migrations"
  load_env
  require_database_url
  ensure_mysql_timezones
  ensure_migrations_init
  fix_blog_fk_migration
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE migrate --noinput
  success "Migrations complete"
}

cmd_collectstatic() {
  header "Collecting Static Files"
  load_env
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE collectstatic --noinput --clear 2>&1 | tail -1
  ensure_static_permissions_and_checks
  success "Static files collected"
}

# ──────────── Cache ────────────
cmd_clear_cache() {
  header "Clearing Cache"
  load_env
  cd "$APP_DIR"

  # Django cache
  sudo -u "$SERVICE_USER" $MANAGE shell -c "
from django.core.cache import cache
cache.clear()
print('Django cache cleared')
" 2>/dev/null && success "Django cache cleared"

  # Redis flush (if applicable)
  if command -v redis-cli &>/dev/null && [[ -f "$ENVFILE" ]] && grep -q 'REDIS_URL' "$ENVFILE"; then
    redis-cli FLUSHDB >/dev/null 2>&1
    success "Redis cache flushed"
  fi

  # Clear compiled Python files
  find "$APP_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  success "Python cache (__pycache__) cleared"
}

# ──────────── SSL ────────────
cmd_ssl_renew() {
  header "SSL Certificate Renewal"
  certbot renew --quiet
  systemctl reload nginx
  success "SSL renewal check complete"
}

cmd_ssl_status() {
  header "SSL Certificate Status"
  certbot certificates 2>/dev/null || warn "Certbot not configured"
}

# ──────────── Nginx ────────────
cmd_nginx_test() {
  header "Nginx Configuration Test"
  nginx -t
}

cmd_nginx_reload() {
  nginx -t && systemctl reload nginx && success "Nginx reloaded"
}

# ──────────── Security ────────────
cmd_security_check() {
  header "Security Audit"

  # File permissions
  info "Checking .env permissions..."
  local env_perms
  env_perms=$(stat -c '%a' "$ENVFILE" 2>/dev/null || echo "???")
  if [[ "$env_perms" == "600" ]]; then
    success ".env permissions: $env_perms"
  else
    fail ".env permissions: $env_perms (should be 600)"
  fi

  # DEBUG mode
  info "Checking DEBUG mode..."
  if grep -q '^DEBUG=0' "$ENVFILE" 2>/dev/null || grep -q '^DEBUG=False' "$ENVFILE" 2>/dev/null; then
    success "DEBUG is OFF"
  else
    fail "DEBUG might be ON — check .env"
  fi

  # Secret key
  info "Checking secret key..."
  if grep -q 'change-me' "$ENVFILE" 2>/dev/null; then
    fail "SECRET_KEY is still default — change it!"
  else
    success "SECRET_KEY is set"
  fi

  # Firewall
  info "Checking firewall..."
  if ufw status 2>/dev/null | grep -q "active"; then
    success "UFW firewall is active"
  else
    warn "UFW firewall is inactive"
  fi

  # Fail2Ban
  info "Checking Fail2Ban..."
  if systemctl is-active fail2ban &>/dev/null; then
    success "Fail2Ban is active"
    fail2ban-client status 2>/dev/null | grep "Jail list" || true
  else
    warn "Fail2Ban is not running"
  fi

  # Open ports
  info "Checking open ports..."
  ss -tlnp 2>/dev/null | grep -E ':(80|443|8000|3306|5432|6379)\b' | \
    awk '{printf "    %s → %s\n", $4, $7}' || true

  # SSL expiry
  if [[ -n "$(grep 'SITE_URL' "$ENVFILE" 2>/dev/null | grep 'https')" ]]; then
    local domain
    domain=$(grep 'SITE_URL' "$ENVFILE" | head -1 | sed 's|.*https://||;s|/.*||')
    if [[ -n "$domain" ]]; then
      info "Checking SSL expiry for $domain..."
      local expiry
      expiry=$(echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | \
               openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
      if [[ -n "$expiry" ]]; then
        echo "    Expires: $expiry"
      fi
    fi
  fi
}

# ──────────── Disk cleanup ────────────
cmd_cleanup() {
  header "Disk Cleanup"

  # Old backups (> 30 days)
  local old_backups
  old_backups=$(find "$BACKUP_DIR" -name 'db_*' -mtime +30 2>/dev/null | wc -l)
  if [[ $old_backups -gt 0 ]]; then
    find "$BACKUP_DIR" -name 'db_*' -mtime +30 -delete 2>/dev/null
    success "Removed $old_backups old backups"
  fi

  # Python cache
  find "$APP_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  find "$APP_DIR" -name '*.pyc' -delete 2>/dev/null || true
  success "Cleared Python cache files"

  # Old log files
  find "$LOG_DIR" -name '*.log.*' -mtime +14 -delete 2>/dev/null || true
  success "Cleared old rotated logs"

  # Apt cache
  apt-get clean 2>/dev/null || true
  apt-get autoremove -y -qq 2>/dev/null || true
  success "System package cache cleaned"

  # Journal
  journalctl --vacuum-time=7d --quiet 2>/dev/null || true
  success "Systemd journal trimmed to 7 days"

  echo ""
  info "Disk after cleanup:"
  df -h / | awk 'NR==2 {printf "  Root: %s used of %s (%s free)\n", $3, $2, $4}'
  echo "  App: $(du -sh "$APP_DIR" 2>/dev/null | awk '{print $1}')"
}

# ──────────── Performance check ────────────
cmd_perf() {
  header "Performance Summary"

  # Request timing
  info "Response time (healthz):"
  local timing
  timing=$(curl -sf -o /dev/null -w "  Connect: %{time_connect}s | TTFB: %{time_starttransfer}s | Total: %{time_total}s" \
           http://127.0.0.1:8000/healthz/ 2>/dev/null || echo "  App not responding")
  echo "$timing"

  # Gunicorn workers
  info "Gunicorn workers:"
  ps aux | grep '[g]unicorn' | awk '{printf "  PID: %s | RSS: %s MB | CPU: %s%%\n", $2, $6/1024, $3}'

  # Connections
  info "Active connections:"
  echo "  Port 8000: $(ss -tn state established '( dport = 8000 )' 2>/dev/null | tail -n +2 | wc -l)"
  echo "  Port 80:   $(ss -tn state established '( dport = 80 )' 2>/dev/null | tail -n +2 | wc -l)"
  echo "  Port 443:  $(ss -tn state established '( dport = 443 )' 2>/dev/null | tail -n +2 | wc -l)"

  # Top processes by memory
  info "Top 5 processes by memory:"
  ps aux --sort=-%mem | head -6 | awk 'NR>1 {printf "  %s (PID %s) — RSS: %.0f MB\n", $11, $2, $6/1024}'
}

# ──────────── Interactive Menu ────────────
show_menu() {
  echo ""
  echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Accountinox Server Manager${NC}                       ${GREEN}║${NC}"
  echo -e "${GREEN}╠══════════════════════════════════════════════════╣${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Monitoring${NC}                                       ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}   1) System status          2) Performance       ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}   3) View logs              4) Security audit    ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Service Control${NC}                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}   5) Restart app            6) Stop app          ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}   7) Start app              8) Reload Nginx      ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Deployment${NC}                                       ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}   9) Deploy update          10) Rollback         ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  11) Run migrations         12) Collect static   ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Admin & Database${NC}                                 ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  13) Backup database        14) Django shell     ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  15) Create superuser       16) Admin management ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Configuration (.env)${NC}                              ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  17) Manage .env / services 18) Clear caches     ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  ${BOLD}Maintenance${NC}                                      ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  19) Disk cleanup           20) SSL status       ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  21) Nginx test             22) Run Django cmd   ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  23) Pull + update project  24) Email manager    ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}  25) Mail server toolkit                          ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}   0) Exit                                        ${GREEN}║${NC}"
  echo -e "${GREEN}║${NC}                                                  ${GREEN}║${NC}"
  echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
  echo ""
}

interactive_menu() {
  while true; do
    show_menu
    read -rp "$(echo -e "${CYAN}▸${NC} Enter choice: ")" choice
    case "$choice" in
      1)  cmd_status ;;
      2)  cmd_perf ;;
      3)
        echo "  [app|access|error|nginx|django|all|follow]"
        read -rp "  Log type (default: app): " lt
        cmd_logs "${lt:-app}"
        ;;
      4)  cmd_security_check ;;
      5)  cmd_restart ;;
      6)  cmd_stop ;;
      7)  cmd_start ;;
      8)  cmd_nginx_reload ;;
      9)  cmd_deploy ;;
      10) cmd_rollback ;;
      11) cmd_migrate ;;
      12) cmd_collectstatic ;;
      13) cmd_backup_db ;;
      14) cmd_shell ;;
      15) cmd_createsuperuser ;;
      16) cmd_admins menu ;;
      17) cmd_env menu ;;
      18) cmd_clear_cache ;;
      19) cmd_cleanup ;;
      20)
        cmd_ssl_status
        read -rp "  Renew now? [y/N] " renew
        [[ "$renew" =~ ^[Yy]$ ]] && cmd_ssl_renew
        ;;
      21) cmd_nginx_test ;;
      22)
        read -rp "  Django command (e.g. showmigrations): " dcmd
        [[ -n "$dcmd" ]] && cmd_django $dcmd
        ;;
      23) cmd_pull_update ;;
      24) cmd_env email menu ;;
      25) cmd_mailserver menu ;;
      0|q|exit) echo ""; success "Goodbye!"; exit 0 ;;
      *) warn "Invalid choice" ;;
    esac
    echo ""
    read -rsp "$(echo -e "${DIM}Press Enter to continue...${NC}")" _
  done
}

###############################################################################
#                             HELP                                            #
###############################################################################
cmd_help() {
  echo ""
  echo -e "${BOLD}Accountinox Server Manager${NC}"
  echo ""
  echo -e "${BOLD}Usage:${NC} sudo bash $0 [command] [args]"
  echo ""
  echo -e "${BOLD}Commands:${NC}"
  printf "  ${CYAN}%-20s${NC} %s\n" "status"          "Full system & service status"
  printf "  ${CYAN}%-20s${NC} %s\n" "start"           "Start the application"
  printf "  ${CYAN}%-20s${NC} %s\n" "stop"            "Stop the application"
  printf "  ${CYAN}%-20s${NC} %s\n" "restart"         "Restart the application"
  printf "  ${CYAN}%-20s${NC} %s\n" "reload"          "Graceful reload"
  printf "  ${CYAN}%-20s${NC} %s\n" "deploy"          "Full deploy (pull + migrate + restart)"
  printf "  ${CYAN}%-20s${NC} %s\n" "update-all"      "Deploy update with critical checks"
  printf "  ${CYAN}%-20s${NC} %s\n" "pull-update"     "Fast-forward pull + app update (safe)"
  printf "  ${CYAN}%-20s${NC} %s\n" "rollback"        "Restore database from latest backup"
  printf "  ${CYAN}%-20s${NC} %s\n" "backup"          "Backup database now"
  printf "  ${CYAN}%-20s${NC} %s\n" "logs [type]"     "View logs (app|access|error|nginx|django|follow)"
  printf "  ${CYAN}%-20s${NC} %s\n" "migrate"         "Run Django migrations"
  printf "  ${CYAN}%-20s${NC} %s\n" "collectstatic"   "Collect static files"
  printf "  ${CYAN}%-20s${NC} %s\n" "createsuperuser" "Create Django superuser"
  printf "  ${CYAN}%-20s${NC} %s\n" "shell"           "Open Django interactive shell"
  printf "  ${CYAN}%-20s${NC} %s\n" "django [cmd]"    "Run any Django manage.py command"
  echo ""
  echo -e "  ${BOLD}Admin / Superuser:${NC}"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins"          "Interactive admin management menu"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins list"     "List all admin/staff users"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins info X"   "Show admin details + permissions"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins passwd X" "Change admin password"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins email X"  "Change admin email"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins promote X" "Promote user to superuser"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins demote X" "Demote superuser (keep staff)"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins revoke X" "Revoke all admin access"
  printf "  ${CYAN}%-20s${NC} %s\n" "admins sessions" "View active admin sessions"
  echo ""
  echo -e "  ${BOLD}Environment (.env):${NC}"
  printf "  ${CYAN}%-20s${NC} %s\n" "env"             "Interactive .env management menu"
  printf "  ${CYAN}%-20s${NC} %s\n" "env show"        "Show all env vars (secrets masked)"
  printf "  ${CYAN}%-20s${NC} %s\n" "env get KEY"     "Get a specific variable"
  printf "  ${CYAN}%-20s${NC} %s\n" "env set KEY VAL" "Set or update a variable"
  printf "  ${CYAN}%-20s${NC} %s\n" "env delete KEY"  "Remove a variable"
  printf "  ${CYAN}%-20s${NC} %s\n" "env toggle-debug" "Toggle DEBUG on/off"
  printf "  ${CYAN}%-20s${NC} %s\n" "env domain X"   "Update domain everywhere"
  printf "  ${CYAN}%-20s${NC} %s\n" "env regen-secret" "Regenerate Django secret key"
  printf "  ${CYAN}%-20s${NC} %s\n" "env email"       "Email setup/management menu"
  printf "  ${CYAN}%-20s${NC} %s\n" "env email status" "Validate current email config"
  printf "  ${CYAN}%-20s${NC} %s\n" "env email setup" "SMTP provider wizard"
  printf "  ${CYAN}%-20s${NC} %s\n" "env email test X" "Send test email to X"
  printf "  ${CYAN}%-20s${NC} %s\n" "env email console" "Enable console backend (no real send)"
  printf "  ${CYAN}%-20s${NC} %s\n" "env google"      "Configure Google OAuth"
  printf "  ${CYAN}%-20s${NC} %s\n" "env sms"         "Configure IPPanel SMS"
  printf "  ${CYAN}%-20s${NC} %s\n" "env push"        "Configure VAPID push notifications"
  printf "  ${CYAN}%-20s${NC} %s\n" "env payment"     "Configure payment gateways"
  printf "  ${CYAN}%-20s${NC} %s\n" "env redis"       "Configure Redis cache URL"
  printf "  ${CYAN}%-20s${NC} %s\n" "env branding"    "Custom admin panel colors"
  printf "  ${CYAN}%-20s${NC} %s\n" "env ssl"         "SSL / HSTS settings wizard"
  printf "  ${CYAN}%-20s${NC} %s\n" "env sentry"      "Sentry error tracking"
  printf "  ${CYAN}%-20s${NC} %s\n" "env restore"     "Restore .env from backup"
  echo ""
  echo -e "  ${BOLD}Mail Server (lightweight):${NC}"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver"      "Interactive lightweight mail server toolkit"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver setup" "Install/configure Postfix + Dovecot + OpenDKIM"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver create X" "Create mailbox (X=email)"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver passwd X" "Reset mailbox password"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver list"  "List configured mailboxes"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver dns"   "Show required DNS records"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver relay" "Configure outbound SMTP relay"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver relay-status" "Show current relay configuration"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver relay-disable" "Disable relay and use direct delivery"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver app-env" "Apply local SMTP settings to Django .env"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver test X" "Send probe email to X"
  printf "  ${CYAN}%-20s${NC} %s\n" "mailserver logs"  "Tail mail service logs"
  echo ""
  echo -e "  ${BOLD}Maintenance:${NC}"
  printf "  ${CYAN}%-20s${NC} %s\n" "clear-cache"     "Clear Django + Redis + Python caches"
  printf "  ${CYAN}%-20s${NC} %s\n" "cleanup"         "Disk cleanup (old backups, logs, cache)"
  printf "  ${CYAN}%-20s${NC} %s\n" "perf"            "Performance summary"
  printf "  ${CYAN}%-20s${NC} %s\n" "security"        "Security audit"
  printf "  ${CYAN}%-20s${NC} %s\n" "ssl-status"      "SSL certificate status"
  printf "  ${CYAN}%-20s${NC} %s\n" "ssl-renew"       "Renew SSL certificates"
  printf "  ${CYAN}%-20s${NC} %s\n" "nginx-test"      "Test Nginx configuration"
  printf "  ${CYAN}%-20s${NC} %s\n" "nginx-reload"    "Reload Nginx configuration"
  printf "  ${CYAN}%-20s${NC} %s\n" "help"            "Show this help"
  echo ""
  echo "  Run without arguments for interactive menu."
  echo ""
}

###############################################################################
#                              MAIN                                          #
###############################################################################
main() {
  check_env

  local cmd="${1:-}"
  shift 2>/dev/null || true

  case "$cmd" in
    status)          cmd_status ;;
    start)           cmd_start ;;
    stop)            cmd_stop ;;
    restart)         cmd_restart ;;
    reload)          cmd_reload ;;
    deploy|update)   cmd_deploy ;;
    update-all)      cmd_deploy ;;
    pull-update|update-safe|pullup) cmd_pull_update ;;
    rollback)        cmd_rollback ;;
    backup|backup-db) cmd_backup_db ;;
    logs|log)        cmd_logs "$@" ;;
    migrate)         cmd_migrate ;;
    collectstatic)   cmd_collectstatic ;;
    createsuperuser) cmd_createsuperuser ;;
    shell)           cmd_shell ;;
    django|manage)   cmd_django "$@" ;;
    admins|admin|users|user) cmd_admins "$@" ;;
    env|dotenv)      cmd_env "$@" ;;
    email|smtp|mail) cmd_env email "$@" ;;
    mailserver|mail-server|mailtool) cmd_mailserver "$@" ;;
    clear-cache|cache) cmd_clear_cache ;;
    cleanup|clean)   cmd_cleanup ;;
    perf|performance) cmd_perf ;;
    security|audit)  cmd_security_check ;;
    ssl-status)      cmd_ssl_status ;;
    ssl-renew)       cmd_ssl_renew ;;
    nginx-test)      cmd_nginx_test ;;
    nginx-reload)    cmd_nginx_reload ;;
    help|-h|--help)  cmd_help ;;
    "")              interactive_menu ;;
    *)               fail "Unknown command: $cmd"; cmd_help ;;
  esac
}

main "$@"
