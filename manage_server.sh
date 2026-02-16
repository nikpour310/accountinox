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
  local health
  health=$(curl -sf --max-time 5 http://127.0.0.1:8000/healthz/ 2>/dev/null || echo "")
  if [[ -n "$health" ]]; then
    success "App responding: $health"
  else
    fail "App not responding on port 8000"
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
  info "Running migrations..."
  sudo -u "$SERVICE_USER" $MANAGE migrate --noinput 2>&1 | tail -5

  info "Collecting static files..."
  sudo -u "$SERVICE_USER" $MANAGE collectstatic --noinput --clear 2>&1 | tail -1

  # 5. Restart
  info "Restarting services..."
  systemctl restart ${APP_NAME}
  systemctl reload nginx
  sleep 2

  # 6. Health check
  local health
  health=$(curl -sf --max-time 10 http://127.0.0.1:8000/healthz/ 2>/dev/null || echo "")
  if [[ -n "$health" ]]; then
    success "Deploy complete in $((SECONDS - started))s — app healthy"
  else
    fail "Deploy finished but health check failed!"
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
      header "Email Configuration"
      echo -e "  Current email settings:"
      grep -E '^(EMAIL_|DEFAULT_FROM)' "$ENVFILE" 2>/dev/null | while read -r line; do
        local k="${line%%=*}"
        local v="${line#*=}"
        if [[ "$k" =~ PASSWORD ]]; then
          echo -e "    ${CYAN}${k}${NC}=${v:0:3}••••"
        else
          echo -e "    ${CYAN}${k}${NC}=${v}"
        fi
      done || info "No email settings configured"
      echo ""
      read -rp "  Configure email now? [y/N] " do_email
      [[ "$do_email" =~ ^[Yy]$ ]] || return 0

      cp "$ENVFILE" "${ENVFILE}.bak.$(date +%s)"

      read -rp "  SMTP Host (e.g. smtp.gmail.com): " smtp_host
      read -rp "  SMTP Port (default 587): " smtp_port
      smtp_port="${smtp_port:-587}"
      read -rp "  Use TLS? [Y/n]: " smtp_tls
      smtp_tls="$([[ "$smtp_tls" =~ ^[Nn]$ ]] && echo 'False' || echo 'True')"
      read -rp "  SMTP Username: " smtp_user
      read -rsp "  SMTP Password: " smtp_pass; echo
      read -rp "  From address (e.g. noreply@domain.com): " from_addr

      # Remove old email settings (commented or active)
      sed -i '/^#.*EMAIL_/d; /^EMAIL_/d; /^DEFAULT_FROM_EMAIL/d; /^#.*DEFAULT_FROM_EMAIL/d' "$ENVFILE"

      cat >> "$ENVFILE" <<EMAILEOF

# ─── Email ($(date +%Y-%m-%d)) ───
EMAIL_HOST=${smtp_host}
EMAIL_PORT=${smtp_port}
EMAIL_USE_TLS=${smtp_tls}
EMAIL_HOST_USER=${smtp_user}
EMAIL_HOST_PASSWORD=${smtp_pass}
DEFAULT_FROM_EMAIL=${from_addr}
EMAILEOF

      chmod 600 "$ENVFILE"
      success "Email configured"
      echo -e "  ${YELLOW}Restart to apply: sudo bash $0 restart${NC}"
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
      echo -e "  ${CYAN} 8${NC}) Configure email (SMTP)   ${CYAN} 9${NC}) Google OAuth"
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
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE migrate --noinput
  success "Migrations complete"
}

cmd_collectstatic() {
  header "Collecting Static Files"
  load_env
  cd "$APP_DIR"
  sudo -u "$SERVICE_USER" $MANAGE collectstatic --noinput --clear 2>&1 | tail -1
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
  printf "  ${CYAN}%-20s${NC} %s\n" "env email"       "Configure SMTP email"
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
