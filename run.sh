#!/bin/bash
# Daily AI/Robotics Paper Briefing runner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Run with venv python
"$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/daily_briefing.py" >> "$SCRIPT_DIR/logs/briefing.log" 2>&1
