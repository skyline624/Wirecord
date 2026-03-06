#!/usr/bin/env python3
"""Gateway Logger avec support Webhook Discord."""

import os
import sys
import time

# Ajouter src au path
sys.path.insert(0, 'src')

# Importer le logger existant
exec(open('gateway_logger.py').read())

# Importer le forwarder
from discord_logger.forwarder import ForwarderService

def main_with_forwarder():
    """Version principale avec forwarding."""
    global forwarder
    
    # Configuration depuis environnement
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    forward_channels = os.environ.get('DISCORD_FORWARD_CHANNELS', '').split(',')
    forward_channels = [c.strip() for c in forward_channels if c.strip()]
    
    if webhook_url and forward_channels:
        print(f'📡 Forwarder activé vers webhook')
        print(f'   Canaux surveillés: {forward_channels}')
        forwarder = ForwarderService(
            webhook_url=webhook_url,
            source_channels=forward_channels,
            use_embeds=True
        )
    
    # Appeler le main original modifié
    return main()

if __name__ == '__main__':
    sys.exit(main_with_forwarder())
