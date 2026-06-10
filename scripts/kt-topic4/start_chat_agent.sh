#!/usr/bin/env bash
set -euo pipefail

SMART_TUTOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SMART_TUTOR_ROOT

cd "$SMART_TUTOR_ROOT/services/chat-agent"

if [ ! -f ".env" ]; then
  echo "services/chat-agent/.env does not exist. Copy services/chat-agent/.env.example to services/chat-agent/.env and fill ChatAgent LLM settings." >&2
fi

exec conda run -n "${KT_CONDA_ENV:-kt}" uvicorn chat_agent.server:app --host 127.0.0.1 --port "${CHATAGENT_PORT:-8910}"
