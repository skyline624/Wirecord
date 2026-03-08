#!/bin/bash
# Redemarre uniquement le logger (pas Discord ni mitmdump)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/logger.pid"

# Arguments : IDs de canaux optionnels
CHANNEL_IDS="$@"

echo "=== Redemarrage du logger ==="

# Arreter le logger si en cours
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Arret du logger (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null
        sleep 1
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID" 2>/dev/null
        fi
    fi
    rm -f "$PID_FILE"
fi

# Demarrer le logger
echo "Demarrage du logger..."
source "$SCRIPT_DIR/venv/bin/activate"
nohup python3 "$SCRIPT_DIR/gateway_logger.py" $CHANNEL_IDS > /dev/null 2>&1 &

LOGGER_PID=$!
echo $LOGGER_PID > "$PID_FILE"
sleep 1

if ! kill -0 "$LOGGER_PID" 2>/dev/null; then
    echo "ERREUR: Le logger n'a pas demarre"
    exit 1
fi

echo "Logger OK (PID: $LOGGER_PID)"
