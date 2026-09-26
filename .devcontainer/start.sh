#!/usr/bin/env bash
# Builds and runs RADHA inside a GitHub Codespace. Runs automatically in a
# terminal whenever the Codespace opens, so you can watch the progress.
set -u
cd "$(dirname "$0")/.."

echo "=================================================================="
echo " RADHA is starting."
echo " First time: about 10-15 minutes. Please keep this window open."
echo " When you see 'Application startup complete', open the Ports tab"
echo " and click the globe icon next to port 8080."
echo "=================================================================="

echo "Waiting for Docker..."
for _ in $(seq 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker isn't available in this Codespace."
  echo "Fix: press Ctrl+Shift+P, choose 'Codespaces: Full Rebuild Container'."
  exit 1
fi

if [ -z "${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}${GEMINI_API_KEY:-}" ] && [ ! -f .env ]; then
  echo "NOTE: no API key found. RADHA will start, but chat needs a key."
  echo "Add one at https://github.com/settings/codespaces (then rebuild), or create a .env file."
fi

# Build, start in the background, then follow the app's log here.
docker compose up -d --build && docker compose logs -f radha
