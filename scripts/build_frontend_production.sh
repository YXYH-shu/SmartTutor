#!/usr/bin/env bash
set -euo pipefail

smarttutor_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${smarttutor_repo_root}/frontend"

# The deployed browser must reach API routes through the forwarded page port.
# Override development .env URLs while retaining the normal Vite production build.
VITE_API_URL= npm run build
