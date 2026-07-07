#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

test -d "$ROOT_DIR/services/chat-agent"
test -d "$ROOT_DIR/services/kt-runtime-skill"

test ! -d "$ROOT_DIR/services/chat-agent/.git"
test ! -d "$ROOT_DIR/services/kt-runtime-skill/.git"
git -C "$ROOT_DIR" check-ignore -q services/chat-agent/.env
git -C "$ROOT_DIR" check-ignore -q services/kt-runtime-skill/.env
test -z "$(git -C "$ROOT_DIR" ls-files 'services/**/.env')"
test ! -f "$ROOT_DIR/services/chat-agent/Agents.md"
test ! -f "$ROOT_DIR/services/kt-runtime-skill/Agents.md"
test ! -f "$ROOT_DIR/services/chat-agent/.gitignore"
test ! -f "$ROOT_DIR/services/kt-runtime-skill/.gitignore"
test ! -d "$ROOT_DIR/services/chat-agent/docs/superpowers"
test ! -d "$ROOT_DIR/services/kt-runtime-skill/docs/superpowers"

grep -q 'path = "../kt-runtime-skill"' "$ROOT_DIR/services/chat-agent/config/skills.toml"
grep -q 'CHATAGENT_LLM_API_KEY' "$ROOT_DIR/services/chat-agent/.env.example"
grep -q 'services/chat-agent' "$ROOT_DIR/services/chat-agent/README.md"
grep -q 'scripts/run_kt.py' "$ROOT_DIR/services/kt-runtime-skill/README.md"
grep -q 'VITE_KT_CHATAGENT_URL' "$ROOT_DIR/frontend/src/pages/KtDiagnosisPage.tsx"
grep -q "embed', '1" "$ROOT_DIR/frontend/src/pages/KtDiagnosisPage.tsx"
grep -q '<iframe' "$ROOT_DIR/frontend/src/pages/KtDiagnosisPage.tsx"
grep -q 'kt-diagnosis' "$ROOT_DIR/frontend/src/App.tsx"
grep -q 'kt-diagnosis' "$ROOT_DIR/frontend/src/components/layout/Sidebar.tsx"
grep -q 'leftPanelToggle' "$ROOT_DIR/services/chat-agent/web/index.html"
grep -q 'rightPanelToggle' "$ROOT_DIR/services/chat-agent/web/index.html"
grep -q 'services/\*\*/\.env' "$ROOT_DIR/.gitignore"
grep -q 'services/\*\*/Agents.md' "$ROOT_DIR/.gitignore"
grep -q 'services/\*\*/docs/superpowers/' "$ROOT_DIR/.gitignore"
