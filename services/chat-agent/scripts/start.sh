#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8910}"
HOST="127.0.0.1"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/chatagent.pid"
LOG_FILE="$RUNTIME_DIR/chatagent.log"

mkdir -p "$RUNTIME_DIR"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "ChatAgent is already running: pid=$PID"
    echo "URL: http://$HOST:$PORT"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

cd "$ROOT_DIR"
PYTHON_BIN="$(conda run -n kt python -c 'import sys; print(sys.executable)')"
nohup setsid "$PYTHON_BIN" -m uvicorn chat_agent.server:app --host "$HOST" --port "$PORT" </dev/null >"$LOG_FILE" 2>&1 &
PID="$!"
echo "$PID" >"$PID_FILE"

sleep 1

if kill -0 "$PID" 2>/dev/null; then
  echo "ChatAgent started: pid=$PID"
  echo "URL: http://$HOST:$PORT"
  echo "Log: $LOG_FILE"
else
  echo "ChatAgent failed to start. Log:"
  tail -n 80 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi
