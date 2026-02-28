#!/bin/bash
# Arrete Discord + le logger + mitmdump

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/logs/logger.pid"
DISCORD_PID_FILE="$SCRIPT_DIR/logs/discord.pid"
MITMDUMP_PID_FILE="$SCRIPT_DIR/logs/mitmdump.pid"

echo "=== Arret du systeme Discord + Logger ==="
echo ""

# 1. Arreter le logger
echo "[1/3] Arret du logger..."
if [ -f "$PID_FILE" ]; then
    LOGGER_PID=$(cat "$PID_FILE")
    if kill -0 "$LOGGER_PID" 2>/dev/null; then
        kill "$LOGGER_PID" 2>/dev/null
        sleep 1
        if kill -0 "$LOGGER_PID" 2>/dev/null; then
            kill -9 "$LOGGER_PID" 2>/dev/null
        fi
        echo "      Logger arrete"
    else
        echo "      Logger deja arrete"
    fi
    rm -f "$PID_FILE"
else
    LOGGER_PID=$(pgrep -f "gateway_logger.py" | head -1)
    if [ -n "$LOGGER_PID" ]; then
        kill "$LOGGER_PID" 2>/dev/null
        sleep 1
        echo "      Logger arrete"
    else
        echo "      Logger non trouve"
    fi
fi

# 2. Arreter Discord
echo ""
echo "[2/3] Arret de Discord..."
if [ -f "$DISCORD_PID_FILE" ]; then
    DISCORD_PID=$(cat "$DISCORD_PID_FILE")
    if kill -0 "$DISCORD_PID" 2>/dev/null; then
        kill "$DISCORD_PID" 2>/dev/null
        sleep 2
        if kill -0 "$DISCORD_PID" 2>/dev/null; then
            kill -9 "$DISCORD_PID" 2>/dev/null
        fi
        echo "      Discord arrete"
    else
        echo "      Discord deja arrete"
    fi
    rm -f "$DISCORD_PID_FILE"
else
    DISCORD_PID=$(pgrep -x discord | head -1)
    if [ -n "$DISCORD_PID" ]; then
        kill "$DISCORD_PID" 2>/dev/null
        sleep 2
        echo "      Discord arrete"
    else
        echo "      Discord non trouve"
    fi
fi

# 3. Arreter mitmdump
echo ""
echo "[3/3] Arret de mitmdump..."
if [ -f "$MITMDUMP_PID_FILE" ]; then
    MITMDUMP_PID=$(cat "$MITMDUMP_PID_FILE")
    if kill -0 "$MITMDUMP_PID" 2>/dev/null; then
        kill "$MITMDUMP_PID" 2>/dev/null
        sleep 1
        if kill -0 "$MITMDUMP_PID" 2>/dev/null; then
            kill -9 "$MITMDUMP_PID" 2>/dev/null
        fi
        echo "      mitmdump arrete"
    else
        echo "      mitmdump deja arrete"
    fi
    rm -f "$MITMDUMP_PID_FILE"
else
    MITMDUMP_PID=$(pgrep -f "mitmdump.*wumpus_in_the_middle" | head -1)
    if [ -n "$MITMDUMP_PID" ]; then
        kill "$MITMDUMP_PID" 2>/dev/null
        sleep 1
        echo "      mitmdump arrete"
    else
        echo "      mitmdump non trouve"
    fi
fi

echo ""
echo "=== ✅ Systeme arrete ==="
