#!/usr/bin/env bash
# Start Claude Code on free models through FreeLLMAPI (see README.md).
# Your normal `claude` command and settings are left untouched.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${FREELLMAPI_API_KEY:-}" && -f "$HERE/.key" ]]; then
  FREELLMAPI_API_KEY="$(tr -d '[:space:]' < "$HERE/.key")"
fi
if [[ -z "${FREELLMAPI_API_KEY:-}" ]]; then
  echo "No FreeLLMAPI key found. Put it in $HERE/.key or set FREELLMAPI_API_KEY." >&2
  echo "See $HERE/README.md, steps 3 and 4." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 20 or newer is needed: https://nodejs.org" >&2
  exit 1
fi

# Desktop app listens on 31415, the Docker/server install on 3001.
URL=""
for c in ${FREELLMAPI_URL:-http://localhost:31415 http://localhost:3001}; do
  if curl -fs -o /dev/null --max-time 5 "$c/v1/models" -H "Authorization: Bearer $FREELLMAPI_API_KEY"; then
    URL="$c"; break
  fi
done
if [[ -z "$URL" ]]; then
  echo "FreeLLMAPI is not answering. Open the FreeLLMAPI app first (or set FREELLMAPI_URL)." >&2
  exit 1
fi

export FREELLMAPI_URL="$URL" FREELLMAPI_API_KEY
exec npx -y freellmapi@0.8.2 launch "$@"
