#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f "deploy/oracle/.env.oracle" ]]; then
  echo "Missing deploy/oracle/.env.oracle"
  echo "Create it from deploy/oracle/.env.oracle.example"
  exit 1
fi

set -a
source "deploy/oracle/.env.oracle"
set +a

if [[ -z "${DOMAIN:-}" || -z "${LETSENCRYPT_EMAIL:-}" ]]; then
  echo "DOMAIN and LETSENCRYPT_EMAIL must be set in deploy/oracle/.env.oracle"
  exit 1
fi

echo "Building and starting services..."
docker compose \
  --env-file deploy/oracle/.env.oracle \
  -f docker-compose.yml \
  -f docker-compose.oracle.yml \
  up -d --build web caddy

echo "Deployment completed."
echo "Check status: docker compose -f docker-compose.yml -f docker-compose.oracle.yml ps"
