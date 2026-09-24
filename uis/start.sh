#!/bin/sh
# Starts both website (port 3000) and backoffice (port 3001) dev servers.
set -e

cleanup() {
  echo "Shutting down frontend servers..."
  kill "$WEBSITE_PID" "$BACKOFFICE_PID" 2>/dev/null
  exit 0
}

trap cleanup INT TERM

cd /app/website && npm run dev &
WEBSITE_PID=$!

cd /app/backoffice && npm run dev &
BACKOFFICE_PID=$!

echo "Website dev server running on :3000"
echo "Backoffice dev server running on :3001"
echo "Press Ctrl+C to stop."

wait