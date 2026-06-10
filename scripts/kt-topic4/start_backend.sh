#!/usr/bin/env bash
set -euo pipefail

SMART_TUTOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SMART_TUTOR_ROOT

cd "$SMART_TUTOR_ROOT/backend"

if [ ! -f ".env" ]; then
  echo "backend/.env does not exist. Copy backend/.env.example to backend/.env and fill SmartTutor LLM settings." >&2
fi

exec uvicorn app.main:app --reload --port "${SMART_TUTOR_BACKEND_PORT:-8000}"
