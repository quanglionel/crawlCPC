#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f "deploy/gcp-trial/.env.gcp-trial" ]]; then
  echo "Missing deploy/gcp-trial/.env.gcp-trial"
  echo "Create it from deploy/gcp-trial/.env.gcp-trial.example"
  exit 1
fi

set -a
source "deploy/gcp-trial/.env.gcp-trial"
set +a

if [[ -z "${DOMAIN:-}" || -z "${LETSENCRYPT_EMAIL:-}" ]]; then
  echo "DOMAIN and LETSENCRYPT_EMAIL must be set in deploy/gcp-trial/.env.gcp-trial"
  exit 1
fi

echo "Building and starting services..."
docker compose \
  --env-file deploy/gcp-trial/.env.gcp-trial \
  -f docker-compose.yml \
  -f docker-compose.gcp-trial.yml \
  up -d --build web caddy

echo "Deployment completed."
echo "Check status: docker compose -f docker-compose.yml -f docker-compose.gcp-trial.yml ps"
