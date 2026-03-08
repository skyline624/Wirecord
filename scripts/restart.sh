#!/usr/bin/env bash
# Wirecord — restart mitmdump only (keeps Discord running)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/.pids"

cd "$PROJECT_DIR"

# ── Read current PIDs ────────────────────────────────────────────────
MITM_PID=""
DISCORD_PID=""
if [ -f "$PID_FILE" ]; then
    MITM_PID=$(sed -n '1p' "$PID_FILE")
    DISCORD_PID=$(sed -n '2p' "$PID_FILE")
fi

# ── Stop mitmdump ────────────────────────────────────────────────────
if [ -n "$MITM_PID" ] && kill -0 "$MITM_PID" 2>/dev/null; then
    kill "$MITM_PID"
    echo "✅ mitmdump stopped (PID $MITM_PID)"
    sleep 1
else
    echo "ℹ️  mitmdump was not running"
    # Try to kill any stray mitmdump process
    pkill -f 'mitmdump.*addon' 2>/dev/null && echo "✅ killed stray mitmdump" && sleep 1 || true
fi

# ── Ensure venv exists ───────────────────────────────────────────────
if [ ! -f "venv/bin/activate" ]; then
    echo "❌ Virtual environment not found."
    echo "   Create it with:"
    echo "     python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi
source venv/bin/activate

# ── Read proxy port from config ──────────────────────────────────────
PROXY_PORT=$(python3 -c "
import sys; sys.path.insert(0, '.')
from discordless.config import Config
print(Config.load().proxy_port)
" 2>/dev/null || echo "8080")

# ── Start mitmdump ───────────────────────────────────────────────────
mkdir -p logs

PYTHONPATH="$PROJECT_DIR" "$PROJECT_DIR/venv/bin/mitmdump" \
    -s discordless/addon.py \
    --listen-port="$PROXY_PORT" \
    --allow-hosts '^(((.+\.)?discord\.com)|((.+\.)?discordapp\.com)|((.+\.)?discord\.net)|((.+\.)?discordapp\.net)|((.+\.)?discord\.gg))(?::\d+)?$' \
    >> logs/mitmdump.log 2>&1 &
NEW_MITM_PID=$!

sleep 2

if ! kill -0 "$NEW_MITM_PID" 2>/dev/null; then
    echo "❌ mitmdump failed to start — check logs/mitmdump.log"
    exit 1
fi

echo "✅ mitmdump restarted (PID $NEW_MITM_PID) — port $PROXY_PORT"

# ── Update .pids (keep Discord PID on line 2) ────────────────────────
echo "$NEW_MITM_PID" > "$PID_FILE"
if [ -n "$DISCORD_PID" ] && kill -0 "$DISCORD_PID" 2>/dev/null; then
    echo "$DISCORD_PID" >> "$PID_FILE"
    echo "ℹ️  Discord still running (PID $DISCORD_PID)"
else
    echo "⚠️  Discord not running"
fi

echo ""
echo "To stop everything: scripts/stop.sh"
