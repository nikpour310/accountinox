#!/usr/bin/env bash
set -euo pipefail

# Build and run the mypy docker image locally
docker compose -f docker-compose.mypy.yml build --no-cache
docker compose -f docker-compose.mypy.yml run --rm mypy
