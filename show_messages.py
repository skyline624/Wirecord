#!/usr/bin/env python3
"""Affiche les messages capturés (simple et rapide)."""
import json
import sys

filepath = "traffic_archive/requests/64_discord.com_api_v9_channels_1473018573571231856_messages"

if len(sys.argv) > 1:
    # Cherche un fichier spécifique
    import os
    for f in os.listdir("traffic_archive/requests"):
        if sys.argv[1] in f:
            filepath = os.path.join("traffic_archive/requests", f)
            break

try:
    with open(filepath) as f:
        data = json.load(f)
    
    print(f"📊 {len(data)} message(s) trouvé(s):\n")
    
    for msg in data[:10]:  # Affiche les 10 premiers
        author = msg.get('author', {}).get('username', 'Unknown')
        content = msg.get('content', '')
        time = msg.get('timestamp', '')[:19].replace('T', ' ')
        print(f"[{time}] @{author}: {content}")
    
    if len(data) > 10:
        print(f"\n... et {len(data) - 10} autres messages")
        
except Exception as e:
    print(f"Erreur: {e}")
    print("Usage: python show_messages.py [channel_id]")
