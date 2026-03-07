#!/usr/bin/env bash
# Wirecord — stop script
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$(dirname "${BASH_SOURCE[0]}")")" && pwd)"
PID_FILE="$PROJECT_DIR/.pids"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  No .pids file found — nothing to stop."
    echo "   If processes are still running, kill them manually:"
    echo "     pkill -f 'mitmdump.*discordless' && pkill -f 'discord.*proxy-server'"
    exit 0
fi

echo "Stopping Wirecord..."
while IFS= read -r pid; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" && echo "  ✅ Stopped PID $pid"
    else
        echo "  ℹ️  PID $pid already stopped"
    fi
done < "$PID_FILE"

rm -f "$PID_FILE"
echo "Done."
