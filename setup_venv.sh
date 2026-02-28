#!/bin/bash
# Script d'installation de l'environnement virtuel Python

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PORT=8002

echo "=========================================="
echo "Configuration de l'environnement Python"
echo "=========================================="
echo ""

# 1. Créer l'environnement virtuel
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Création de l'environnement virtuel..."
    python3 -m venv "$VENV_DIR"
    echo "  ✅ Environnement créé"
else
    echo "📦 Environnement virtuel existant"
fi

# 2. Activer et installer les dépendances
echo ""
echo "📥 Installation des dépendances..."
source "$VENV_DIR/bin/activate"

# Mise à jour de pip
pip install --upgrade pip

# Installation des packages nécessaires
pip install mitmproxy pyzstd erlpack filetype jinja2 python-dateutil

echo "  ✅ Dépendances installées"

# 3. Créer le script de lancement avec venv
echo ""
echo "📝 Création du script de lancement..."

cat > "$SCRIPT_DIR/run_discord_logger.sh" <> 'LAUNCHEOF'
#!/bin/bash
# Discord Live Logger - Lancement avec environnement virtuel
# Port: 8002

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8002

# Activer l'environnement virtuel
source "$SCRIPT_DIR/venv/bin/activate"

echo "=========================================="
echo "Discord Live Logger"
echo "=========================================="
echo "Port: $PORT"
echo "Python: $(which python3)"
echo ""

# Vérifier que mitmdump est disponible
if ! command -v mitmdump &> /dev/null; then
    echo "❌ mitmdump n'est pas trouvé"
    echo "   Vérifiez que l'environnement virtuel est configuré"
    exit 1
fi

echo "✅ mitmdump: $(which mitmdump)"
echo ""

# Lancer mitmdump
echo "🔧 Démarrage du proxy..."
cd "$SCRIPT_DIR"

mitmdump -s discord_live_logger.py --listen-port=$PORT \
  --allow-hosts '^(((.+\.)?discord\.com)|((.+\.)?discordapp\.com)|((.+\.)?discord\.net)|((.+\.)?discordapp\.net)|((.+\.)?discord\.gg))$' \
  --set console_eventlog_verbosity=warn
LAUNCHEOF

chmod +x "$SCRIPT_DIR/run_discord_logger.sh"

echo "  ✅ Script créé: run_discord_logger.sh"

# 4. Créer le script pour lancer Discord avec proxy
cat > "$SCRIPT_DIR/run_discord_with_proxy.sh" << 'DISCORDEOF'
#!/bin/bash
# Lancer Discord avec le proxy configuré

PORT=8002
PROXY_URL="http://localhost:$PORT"

echo "🚀 Lancement de Discord avec proxy..."
echo "   Proxy: $PROXY_URL"
echo ""

export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"

# Lancer Discord
if command -v discord &> /dev/null; then
    discord &
    echo "✅ Discord lancé (PID: $!)"
elif command -v Discord &> /dev/null; then
    Discord &
    echo "✅ Discord lancé (PID: $!)"
else
    echo "❌ Discord non trouvé dans le PATH"
    exit 1
fi
DISCORDEOF

chmod +x "$SCRIPT_DIR/run_discord_with_proxy.sh"

echo "  ✅ Script créé: run_discord_with_proxy.sh"

# 5. Créer le script combiné
cat > "$SCRIPT_DIR/start_all.sh" << 'COMBINEDEOF'
#!/bin/bash
# Lancer le proxy ET Discord

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8002

echo "=========================================="
echo "Discord Live Logger - Mode combiné"
echo "=========================================="
echo ""

# Activer l'environnement virtuel
source "$SCRIPT_DIR/venv/bin/activate"

# Vérifier si le port est utilisé
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Le port $PORT est déjà utilisé"
    echo "   Arrêtez d'abord l'instance précédente"
    exit 1
fi

# Lancer mitmdump en arrière-plan
echo "🔧 Démarrage du proxy sur le port $PORT..."
cd "$SCRIPT_DIR"
mitmdump -s discord_live_logger.py --listen-port=$PORT \
  --allow-hosts '^(((.+\.)?discord\.com)|((.+\.)?discordapp\.com)|((.+\.)?discord\.net)|((.+\.)?discordapp\.net)|((.+\.)?discord\.gg))$' \
  --set console_eventlog_verbosity=warn &

MITM_PID=$!
echo "✅ Proxy démarré (PID: $MITM_PID)"
echo ""

# Attendre que le proxy soit prêt
sleep 2

# Lancer Discord avec proxy
export HTTP_PROXY="http://localhost:$PORT"
export HTTPS_PROXY="http://localhost:$PORT"
export http_proxy="http://localhost:$PORT"
export https_proxy="http://localhost:$PORT"

if command -v discord &> /dev/null; then
    discord &
    DISCORD_PID=$!
    echo "✅ Discord lancé (PID: $DISCORD_PID)"
elif command -v Discord &> /dev/null; then
    Discord &
    DISCORD_PID=$!
    echo "✅ Discord lancé (PID: $DISCORD_PID)"
else
    echo "⚠️  Discord non trouvé - lancez-le manuellement avec:"
    echo "   HTTP_PROXY=http://localhost:$PORT HTTPS_PROXY=http://localhost:$PORT discord"
    DISCORD_PID=""
fi

echo ""
echo "=========================================="
echo "✅ Tous les services sont lancés !"
echo ""
echo "Pour arrêter:"
echo "  kill $MITM_PID ${DISCORD_PID:-}"
echo "=========================================="

# Attendre
trap "echo ''; echo '⏹ Arrêt...'; kill $MITM_PID ${DISCORD_PID:-} 2>/dev/null; exit" INT TERM
wait
COMBINEDEOF

chmod +x "$SCRIPT_DIR/start_all.sh"

echo "  ✅ Script créé: start_all.sh"

# Résumé
echo ""
echo "=========================================="
echo "✅ Installation terminée !"
echo ""
echo "Scripts disponibles:"
echo "  ./run_discord_logger.sh       - Lancer uniquement le proxy"
echo "  ./run_discord_with_proxy.sh   - Lancer uniquement Discord (avec proxy)"
echo "  ./start_all.sh                - Lancer proxy + Discord"
echo ""
echo "Utilisation:"
echo "  Terminal 1: ./run_discord_logger.sh"
echo "  Terminal 2: ./run_discord_with_proxy.sh"
echo ""
echo "Ou en une seule commande:"
echo "  ./start_all.sh"
echo "=========================================="
