#!/bin/bash
# Lance Discord + le logger de messages Gateway

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs/messages"
PID_FILE="$SCRIPT_DIR/logs/logger.pid"
DISCORD_PID_FILE="$SCRIPT_DIR/logs/discord.pid"
MITMDUMP_PID_FILE="$SCRIPT_DIR/logs/mitmdump.pid"

# Creer les repertoires
mkdir -p "$LOG_DIR"
mkdir -p "$SCRIPT_DIR/logs"

# Arguments : IDs de canaux optionnels
CHANNEL_IDS="$@"

echo "=== Discord + Gateway Message Logger ==="
echo "Date: $(date)"
if [ -n "$CHANNEL_IDS" ]; then
    echo "Canaux specifiques: $CHANNEL_IDS"
fi
echo ""

# Verifier que le venv existe
if [ ! -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "Erreur: Virtual environment non trouve"
    exit 1
fi

# Arreter si deja en cours
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Arret de l'instance precedente..."
        kill "$OLD_PID" 2>/dev/null
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

# 1. Demarrer mitmdump (pour capturer le Gateway)
echo "[1/4] Demarrage de mitmdump..."
MITMDUMP_LOG="$SCRIPT_DIR/logs/mitmdump.log"
nohup /usr/bin/mitmdump \
    -s "$SCRIPT_DIR/wumpus_in_the_middle.py" \
    --listen-port=8082 \
    --allow-hosts 'discord.com|discord.gg' \
    > "$MITMDUMP_LOG" 2>&1 &

MITMDUMP_PID=$!
echo $MITMDUMP_PID > "$MITMDUMP_PID_FILE"
sleep 2

if ! kill -0 "$MITMDUMP_PID" 2>/dev/null; then
    echo "ERREUR: mitmdump n'a pas demarre"
    exit 1
fi
echo "      mitmdump OK (PID: $MITMDUMP_PID)"

# 2. Demarrer Discord
echo ""
echo "[2/4] Demarrage de Discord..."
nohup discord \
    --proxy-server=localhost:8082 \
    --ignore-certificate-errors \
    > "$SCRIPT_DIR/logs/discord.log" 2>&1 &

DISCORD_PID=$!
echo $DISCORD_PID > "$DISCORD_PID_FILE"
sleep 3

if ! kill -0 "$DISCORD_PID" 2>/dev/null; then
    echo "ATTENTION: Discord n'a peut-etre pas demarre correctement"
else
    echo "      Discord OK (PID: $DISCORD_PID)"
fi

# 3. Demarrer le logger
echo ""
echo "[3/4] Demarrage du logger..."
source "$SCRIPT_DIR/venv/bin/activate"
nohup python3 "$SCRIPT_DIR/gateway_logger.py" $CHANNEL_IDS > /dev/null 2>&1 &

LOGGER_PID=$!
echo $LOGGER_PID > "$PID_FILE"
sleep 1

if ! kill -0 "$LOGGER_PID" 2>/dev/null; then
    echo "ERREUR: Le logger n'a pas demarre"
    exit 1
fi
echo "      Logger OK (PID: $LOGGER_PID)"

# 4. Resume
echo ""
echo "[4/4] Verification..."
sleep 2

echo ""
echo "========================================"
echo "✅ SYSTEME ACTIF !"
echo ""
echo "Processus:"
echo "  - mitmdump:  PID $MITMDUMP_PID"
echo "  - Discord:   PID $DISCORD_PID"
echo "  - Logger:    PID $LOGGER_PID"
echo ""
echo "Logs des messages:"
echo "  - General: $LOG_DIR/all_messages_YYYYMMDD.log"
if [ -n "$CHANNEL_IDS" ]; then
    for cid in $CHANNEL_IDS; do
        echo "  - Canal $cid: $LOG_DIR/channel_${cid}_YYYYMMDD.log"
    done
fi
echo ""
echo "Commandes:"
echo "  - Voir logs:   tail -f $LOG_DIR/all_messages_*.log"
echo "  - Arreter:     ./stop_logger.sh"
echo "========================================"
