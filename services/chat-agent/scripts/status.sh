#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.runtime/chatagent.pid"
LOG_FILE="$ROOT_DIR/.runtime/chatagent.log"

if [[ ! -f "$PID_FILE" ]]; then
  echo "ChatAgent is not running"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  echo "ChatAgent is running: pid=$PID"
  echo "Log: $LOG_FILE"
else
  echo "ChatAgent pid file exists, but process is not running: pid=$PID"
  exit 1
fi
