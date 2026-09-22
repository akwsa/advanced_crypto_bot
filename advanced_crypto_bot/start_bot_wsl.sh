#!/usr/bin/env bash
# Tujuan: Launcher WSL/Linux untuk menjalankan bot dari root repo.
# Caller: Terminal VS Code/Windsurf atau shell WSL operator.
# Dependensi: venv/bin/activate, bot.py.
# Main Functions: validasi root repo, aktivasi venv, jalankan bot.py.
# Side Effects: menjalankan proses Telegram bot dan side effect runtime bot.

set -Eeuo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

if [[ ! -f "venv/bin/activate" ]]; then
    echo "ERROR: venv/bin/activate tidak ditemukan di $REPO_DIR" >&2
    echo "Buat venv dulu atau jalankan script ini dari repo yang benar." >&2
    exit 1
fi

if [[ ! -f "bot.py" ]]; then
    echo "ERROR: bot.py tidak ditemukan di $REPO_DIR" >&2
    exit 1
fi

source venv/bin/activate

echo "Starting Advanced Crypto Bot..."
echo "Repo: $REPO_DIR"
echo "Python: $(python --version)"

exec python bot.py "$@"
