#!/usr/bin/env bash
set -euo pipefail

SMART_TUTOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SMART_TUTOR_ROOT

cd "$SMART_TUTOR_ROOT/backend"

# 6403 vLLM 直连不走 shell 代理，否则 httpx 会经代理返回 502
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}172.17.43.38"
export no_proxy="${no_proxy:+$no_proxy,}172.17.43.38"

if [ ! -f ".env" ]; then
  echo "backend/.env does not exist. Copy backend/.env.example to backend/.env and fill SmartTutor LLM settings." >&2
fi

exec uvicorn app.main:app --reload --port "${SMART_TUTOR_BACKEND_PORT:-8010}"
