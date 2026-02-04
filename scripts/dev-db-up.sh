#!/usr/bin/env bash
# Helper: start local Postgres db via docker compose
# Usage: ./scripts/dev-db-up.sh

set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  cat <<'MSG'
Docker is not installed or not in PATH.

Please install Docker Desktop (Windows) or Docker Engine and ensure it's running.

On Windows, install Docker Desktop and enable WSL2 backend.

After installing Docker, run:
  docker compose up -d db

MSG
  exit 1
fi

echo "Starting Postgres service via docker compose..."
docker compose up -d db

echo "Done. Check 'docker ps' to confirm the container is running."

echo "Export DATABASE_URL and run migrations:"
cat <<'CMD'
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/accountinox"
# On PowerShell (Windows):
# $env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/accountinox'

npx prisma migrate dev --name init
npx prisma generate
npm run build
CMD
