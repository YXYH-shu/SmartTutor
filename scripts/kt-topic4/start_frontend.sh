#!/usr/bin/env bash
set -euo pipefail

SMART_TUTOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SMART_TUTOR_ROOT

cd "$SMART_TUTOR_ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "frontend/node_modules does not exist. Run: cd frontend && npm install" >&2
fi

exec npm run dev
