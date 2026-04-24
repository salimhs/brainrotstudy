#!/usr/bin/env bash
# Launch the FastAPI server in the background and the Next.js server in the foreground.
set -euo pipefail

mkdir -p "$STORAGE_ROOT"

brainrotstudy --host 0.0.0.0 --port "$PORT" &
API_PID=$!

trap 'kill $API_PID 2>/dev/null || true' EXIT

exec node /app/web/server.js
