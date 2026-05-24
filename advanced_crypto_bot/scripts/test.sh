#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$ROOT_DIR/venv/bin/python" ]] && "$ROOT_DIR/venv/bin/python" -c 'import pytest' >/dev/null 2>&1; then
  PYTHON_BIN="$ROOT_DIR/venv/bin/python"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]] && "$ROOT_DIR/.venv/bin/python" -c 'import pytest' >/dev/null 2>&1; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif [[ -x "/home/officer/.hermes/bin/python" ]] && /home/officer/.hermes/bin/python -c 'import pytest' >/dev/null 2>&1; then
  PYTHON_BIN="/home/officer/.hermes/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if ! "$PYTHON_BIN" -c 'import pytest' >/dev/null 2>&1; then
  echo "ERROR: pytest is not installed for $PYTHON_BIN" >&2
  echo "Install dev dependencies with: $PYTHON_BIN -m pip install -r requirements.txt" >&2
  exit 2
fi

echo "[test] root: $ROOT_DIR"
echo "[test] python: $PYTHON_BIN"
exec "$PYTHON_BIN" -m pytest "$@"
