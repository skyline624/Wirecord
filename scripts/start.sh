#!/usr/bin/env bash
# Discordless — start script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/.pids"

cd "$PROJECT_DIR"

if [ -f "$PID_FILE" ]; then
    echo "⚠️  Discordless appears to already be running (.pids exists)."
    echo "   Run scripts/stop.sh first, or delete .pids manually."
    exit 1
fi

if [ ! -f "venv/bin/activate" ]; then
    echo "❌ Virtual environment not found."
    echo "   Create it with:"
    echo "     python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi
source venv/bin/activate

PROXY_PORT=$(python3 -c "
import sys; sys.path.insert(0, '.')
from discordless.config import Config
print(Config.load().proxy_port)
" 2>/dev/null || echo "8080")

mkdir -p logs

echo "=== Discordless ==="
echo "Project : $PROJECT_DIR"
echo "Config  : config.json"
echo "Port    : $PROXY_PORT"
echo ""

PYTHONPATH="$PROJECT_DIR" "$PROJECT_DIR/venv/bin/mitmdump" \
    -s discordless/addon.py \
    --listen-port="$PROXY_PORT" \
    --allow-hosts '^(((.+\.)?discord\.com)|((.+\.)?discordapp\.com)|((.+\.)?discord\.net)|((.+\.)?discordapp\.net)|((.+\.)?discord\.gg))(?::\d+)?$' \
    >> logs/mitmdump.log 2>&1 &
MITM_PID=$!
echo "✅ mitmdump started  (PID $MITM_PID) — logs/mitmdump.log"
echo "$MITM_PID" > "$PID_FILE"

sleep 2

DISCORD_PID=""
for cmd in discord Discord discord-canary; do
    if command -v "$cmd" &>/dev/null; then
        "$cmd" --proxy-server="localhost:$PROXY_PORT" >> logs/discord.log 2>&1 &
        DISCORD_PID=$!
        echo "✅ Discord started   (PID $DISCORD_PID, cmd: $cmd) — logs/discord.log"
        echo "$DISCORD_PID" >> "$PID_FILE"
        break
    fi
done

if [ -z "$DISCORD_PID" ]; then
    echo "⚠️  Discord not found in PATH."
    echo "   Start it manually with:  discord --proxy-server=localhost:$PROXY_PORT"
fi

echo ""
echo "To stop: scripts/stop.sh"
