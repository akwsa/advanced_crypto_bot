#!/bin/bash
# watch_signals.sh — Real-time signal monitor with color highlights
LOG_FILE="logs/trading_bot.log"

if [ ! -f "$LOG_FILE" ]; then
  echo "❌ Log file not found: $LOG_FILE"
  echo "💡 Make sure bot is running and log directory exists."
  exit 1
fi

echo "🚀 Watching signals in real-time (press Ctrl+C to stop)..."
echo "💡 Filtering: BUY (green), SELL (red), HOLD (yellow), strength (cyan), signal (magenta)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Tail + grep + highlight
tail -f "$LOG_FILE" 2>/dev/null | \
  while IFS= read -r line; do
    if echo "$line" | grep -q -i "BUY"; then
      echo -e "${GREEN}$(date '+%H:%M:%S') [BUY]${NC} $(echo "$line" | sed 's/[Bb][Uu][Yy]/"${GREEN}BUY${NC}"/g')"
    elif echo "$line" | grep -q -i "SELL"; then
      echo -e "${RED}$(date '+%H:%M:%S') [SELL]${NC} $(echo "$line" | sed 's/[Ss][Ee][Ll][Ll]/"${RED}SELL${NC}"/g')"
    elif echo "$line" | grep -q -i "HOLD"; then
      echo -e "${YELLOW}$(date '+%H:%M:%S') [HOLD]${NC} $(echo "$line" | sed 's/[Hh][Oo][Ll][Dd]/"${YELLOW}HOLD${NC}"/g')"
    elif echo "$line" | grep -q -i "strength"; then
      echo -e "${CYAN}$(date '+%H:%M:%S') [STRENGTH]${NC} $line"
    elif echo "$line" | grep -q -i "signal"; then
      echo -e "${MAGENTA}$(date '+%H:%M:%S') [SIGNAL]${NC} $line"
    fi
  done