#!/usr/bin/env bash
# Manual launcher (without Pinokio). Usage: ./start.sh [--mock]
set -euo pipefail
cd "$(dirname "$0")"
if [ "${1:-}" = "--mock" ]; then
  export MUSIXER_MUSIC_ENGINE=mock
elif [ -d app/ACE-Step-1.5 ]; then
  (cd app/ACE-Step-1.5 && uv run acestep-api) &
  ACE_PID=$!
  trap 'kill $ACE_PID 2>/dev/null || true' EXIT
fi
"${PYTHON:-.venv/bin/python}" -m musixer
