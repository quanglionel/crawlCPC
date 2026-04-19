#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash deploy/gcp-trial/scripts/install_docker_ubuntu.sh"
  exit 1
fi

TARGET_USER="${SUDO_USER:-ubuntu}"

echo "[1/4] Updating apt index..."
apt-get update -y

echo "[2/4] Installing Docker engine + compose plugin..."
apt-get install -y docker.io docker-compose-plugin

echo "[3/4] Enabling Docker service..."
systemctl enable docker
systemctl restart docker

echo "[4/4] Adding user '${TARGET_USER}' to docker group..."
usermod -aG docker "${TARGET_USER}" || true

echo "Done. Re-login the shell to apply docker group permissions."
