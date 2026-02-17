#!/usr/bin/env bash
set -u
DIR="/srv/accountinox"
ENVFILE="$DIR/.env"

echotitle(){ printf "\n===== %s =====\n" "$1"; }

safe_run_as_app(){
  # Run a command as service user if possible, preserving safe env loading
  if id accountinox &>/dev/null; then
    sudo -u accountinox bash -lc "ENVFILE=${ENVFILE}; set -a; while IFS='=' read -r k v; do k=\"\${k:-}\"; v=\"\${v:-}\"; [[ -z \"\$k\" || \"\$k\" =~ ^# ]] && continue; v=\"\${v%\"}\"; v=\"\${v#\"}\"; v=\"\${v%\'}\"; v=\"\${v#\'}\"; export \"\$k\"=\"\$v\"; done < \"$ENVFILE\"; set +a; $*"
  else
    bash -lc "ENVFILE=${ENVFILE}; set -a; while IFS='=' read -r k v; do k=\"\${k:-}\"; v=\"\${v:-}\"; [[ -z \"\$k\" || \"\$k\" =~ ^# ]] && continue; v=\"\${v%\"}\"; v=\"\${v#\"}\"; v=\"\${v%\'}\"; v=\"\${v#\'}\"; export \"\$k\"=\"\$v\"; done < \"$ENVFILE\"; set +a; $*"
  fi
}

echotitle "Environment file preview"
if [[ -f "$ENVFILE" ]]; then
  sed -n '1,40p' "$ENVFILE" || true
else
  echo ".env not found at $ENVFILE"
fi

echotitle "Masked important env values"
if [[ -f "$ENVFILE" ]]; then
  awk -F= '/^DJANGO_SECRET_KEY=/{print "DJANGO_SECRET_KEY=***MASKED***"} /^DATABASE_URL=/{printf "DATABASE_URL="; print substr($0, index($0,$2))} /^VAPID_PUBLIC_KEY=/{print "VAPID_PUBLIC_KEY="substr($0, index($0,$2), 16)"..."} /^VAPID_PRIVATE_KEY=/{print "VAPID_PRIVATE_KEY=(present)"}' "$ENVFILE" || true
else
  echo ".env missing"
fi

echotitle "Django migrations (showmigrations)"
if [[ -f "$DIR/manage.py" ]]; then
  safe_run_as_app "/srv/accountinox/.venv/bin/python $DIR/manage.py showmigrations --list" || true
else
  echo "manage.py not found in $DIR"
fi

echotitle "Django migrate (plan)"
if [[ -f "$DIR/manage.py" ]]; then
  safe_run_as_app "/srv/accountinox/.venv/bin/python $DIR/manage.py migrate --plan" || true
fi

# Extract DB creds from .env DATABASE_URL
DBURL_LINE=""
if [[ -f "$ENVFILE" ]]; then
  DBURL_LINE=$(grep -E '^DATABASE_URL=' "$ENVFILE" | head -1 | cut -d= -f2- || true)
fi

if [[ -n "$DBURL_LINE" ]]; then
  echotitle "Database connection info (parsed)"
  DB_USER=$(echo "$DBURL_LINE" | sed -n 's|.*://\([^:]*\):.*|\1|p' )
  DB_PASS=$(echo "$DBURL_LINE" | sed -n "s|.*://[^:]*:\([^@]*\)@.*|\1|p")
  DB_HOST=$(echo "$DBURL_LINE" | sed -n 's|.*@\([^:/]*\).*|\1|p')
  DB_NAME=$(echo "$DBURL_LINE" | sed -n 's|.*/\([^?]*\).*|\1|p')
  printf "DB_USER=%s DB_HOST=%s DB_NAME=%s\n" "$DB_USER" "$DB_HOST" "$DB_NAME"

  if command -v mysql &>/dev/null; then
    echotitle "Last 50 entries in django_migrations"
    mysql -u"$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -e "SELECT id, app, name FROM django_migrations ORDER BY id DESC LIMIT 50;" "$DB_NAME" || true

    echotitle "List tables in DB"
    mysql -u"$DB_USER" -p"$DB_PASS" -h "$DB_HOST" -e "SHOW TABLES;" "$DB_NAME" || true
  else
    echo "mysql client not installed on this host"
  fi
else
  echo "No DATABASE_URL found in .env"
fi

echotitle "Tail application logs (last 200 lines each)"
if [[ -d "$DIR/logs" ]]; then
  for f in "$DIR"/logs/*.log; do
    [[ -f "$f" ]] || continue
    printf "\n--- %s ---\n" "$f"
    tail -n 200 "$f" || true
  done
else
  echo "No logs directory at $DIR/logs"
fi

echotitle "Systemd service status (accountinox)"
if command -v systemctl &>/dev/null; then
  systemctl status accountinox --no-pager || true
else
  echo "systemctl not available"
fi

echotitle "Done"

exit 0
