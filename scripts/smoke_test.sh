#!/usr/bin/env bash
#
# scripts/smoke_test.sh — boots the Streamlit app headless, waits for it to
# come up, and fails if it either never responds or logs a traceback during
# startup.
#
# Why this exists: shipping the "shipping distance" feature, the processed
# dataset gained new columns but Streamlit's @st.cache_data kept serving a
# stale in-memory copy from before the change (its cache key is based on the
# cached function's own code, not on files it happens to read) — causing a
# KeyError that only showed up on the LIVE deployed app, not in any local
# `pip install && py_compile` check, because the bug only manifests once the
# app actually *runs*. This script automates the manual check that caught it.
#
# Usage: bash scripts/smoke_test.sh [path/to/app.py]

set -euo pipefail

PORT=8599
LOG_FILE=$(mktemp)
APP_PATH="${1:-src/app.py}"

cleanup() {
  if [[ -n "${STREAMLIT_PID:-}" ]] && kill -0 "$STREAMLIT_PID" 2>/dev/null; then
    kill "$STREAMLIT_PID" 2>/dev/null || true
    wait "$STREAMLIT_PID" 2>/dev/null || true
  fi
  rm -f "$LOG_FILE"
}
trap cleanup EXIT

echo "Booting $APP_PATH on port $PORT..."
python3 -m streamlit run "$APP_PATH" --server.headless true --server.port "$PORT" > "$LOG_FILE" 2>&1 &
STREAMLIT_PID=$!

READY=0
for _ in $(seq 1 30); do
  CODE=$(curl -sS -m 2 -o /dev/null -w "%{http_code}" "http://localhost:$PORT" 2>/dev/null || true)
  if [[ "$CODE" == "200" ]]; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" -ne 1 ]]; then
  echo "FAIL: app never responded with HTTP 200 on port $PORT within 30s"
  echo "--- log ---"
  cat "$LOG_FILE"
  exit 1
fi

if grep -qi "traceback\|error\|exception" "$LOG_FILE"; then
  echo "FAIL: app responded, but logged an error during startup"
  echo "--- log ---"
  cat "$LOG_FILE"
  exit 1
fi

echo "PASS: app booted cleanly and responded with HTTP 200"
