#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.runtime/chatagent.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "ChatAgent is not running: pid file not found"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  for _ in {1..20}; do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done
  if kill -0 "$PID" 2>/dev/null; then
    kill -9 "$PID"
  fi
  echo "ChatAgent stopped: pid=$PID"
else
  echo "ChatAgent process is already stopped: pid=$PID"
fi

rm -f "$PID_FILE"
