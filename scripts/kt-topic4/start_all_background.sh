#!/usr/bin/env bash
set -euo pipefail

SMART_TUTOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SMART_TUTOR_ROOT

RUNTIME_DIR="${SMART_TUTOR_RUNTIME_DIR:-$SMART_TUTOR_ROOT/.runtime/kt-topic4}"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"

BACKEND_PORT="${SMART_TUTOR_BACKEND_PORT:-8010}"
FRONTEND_PORT="${SMART_TUTOR_FRONTEND_PORT:-3000}"
CHATAGENT_PORT="${CHATAGENT_PORT:-8910}"
KT_ENV="${KT_CONDA_ENV:-kt}"

mkdir -p "$LOG_DIR" "$PID_DIR"

port_is_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_port() {
  local name="$1"
  local port="$2"

  for _ in $(seq 1 60); do
    if port_is_listening "$port"; then
      echo "$name is listening on 127.0.0.1:$port"
      return 0
    fi
    sleep 1
  done

  echo "$name did not start on port $port within 60 seconds." >&2
  return 1
}

start_service() {
  local name="$1"
  local port="$2"
  local log_file="$LOG_DIR/$name.log"
  local pid_file="$PID_DIR/$name.pid"
  shift 2

  if port_is_listening "$port"; then
    echo "$name skipped: port $port is already in use."
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
    return 0
  fi

  echo "Starting $name on port $port ..."
  (
    cd "$SMART_TUTOR_ROOT"
    setsid nohup "$@" >"$log_file" 2>&1 </dev/null &
    echo "$!" >"$pid_file"
  )
  echo "$name pid: $(cat "$pid_file")"
  echo "$name log: $log_file"
  wait_for_port "$name" "$port"
}

if ! command -v conda >/dev/null 2>&1; then
  echo "conda command not found. Please initialize conda before running this script." >&2
  exit 1
fi

if [ ! -f "$SMART_TUTOR_ROOT/frontend/.env" ]; then
  echo "frontend/.env does not exist. Copy frontend/.env.example to frontend/.env first." >&2
  exit 1
fi

if ! grep -Eq "^VITE_API_URL=http://127\.0\.0\.1:${BACKEND_PORT}/?$|^VITE_API_URL=http://localhost:${BACKEND_PORT}/?$" "$SMART_TUTOR_ROOT/frontend/.env"; then
  echo "Warning: frontend/.env should contain VITE_API_URL=http://127.0.0.1:$BACKEND_PORT when backend avoids port 8000." >&2
fi

start_service \
  "backend" \
  "$BACKEND_PORT" \
  env SMART_TUTOR_BACKEND_PORT="$BACKEND_PORT" \
    conda run -n "$KT_ENV" --no-capture-output \
    bash "$SMART_TUTOR_ROOT/scripts/kt-topic4/start_backend.sh"

start_service \
  "frontend" \
  "$FRONTEND_PORT" \
  bash "$SMART_TUTOR_ROOT/scripts/kt-topic4/start_frontend.sh"

start_service \
  "chat-agent" \
  "$CHATAGENT_PORT" \
  env CHATAGENT_PORT="$CHATAGENT_PORT" KT_CONDA_ENV="$KT_ENV" \
    bash "$SMART_TUTOR_ROOT/scripts/kt-topic4/start_chat_agent.sh"

echo
echo "SmartTutor background services are ready:"
echo "  frontend:   http://127.0.0.1:$FRONTEND_PORT"
echo "  backend:    http://127.0.0.1:$BACKEND_PORT/docs"
echo "  ChatAgent:  http://127.0.0.1:$CHATAGENT_PORT/"
echo
echo "Runtime files:"
echo "  logs: $LOG_DIR"
echo "  pids: $PID_DIR"
