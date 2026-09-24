#!/usr/bin/env bash
# Starts RADHA inside a GitHub Codespace (runs automatically on every start).
set -u
cd "$(dirname "$0")/.."

echo "Waiting for Docker…"
for _ in $(seq 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
if ! docker info >/dev/null 2>&1; then
  echo "Docker isn't available in this Codespace. Run: Ctrl+Shift+P → 'Codespaces: Full Rebuild Container'."
  exit 0
fi

echo "Building and starting RADHA (the first time takes about 10 minutes)…"
nohup docker compose up -d --build > /tmp/radha-start.log 2>&1 &
echo "Progress: see /tmp/radha-start.log, then 'docker compose logs -f radha'."
echo "RADHA opens in a new browser tab when it's ready (Ports tab → RADHA, port 8080)."
