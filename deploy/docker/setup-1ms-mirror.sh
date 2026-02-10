#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILE="${SCRIPT_DIR}/daemon.1ms.json"

if [[ ! -f "${SOURCE_FILE}" ]]; then
  echo "missing ${SOURCE_FILE}" >&2
  exit 1
fi

sudo mkdir -p /etc/docker
sudo cp "${SOURCE_FILE}" /etc/docker/daemon.json

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart docker
elif command -v service >/dev/null 2>&1; then
  sudo service docker restart
else
  echo "Please restart Docker daemon manually." >&2
fi

echo "Docker registry mirror is set to https://docker.1ms.run"
