#!/usr/bin/env python3
"""Gateway Logger avec configuration fichier JSON."""

import sys
sys.path.insert(0, 'src')

from discord_logger.config_loader import load_forwarder_config
from discord_logger.forwarder import ForwarderService

# Charger la configuration
config = load_forwarder_config('config/forwarder.json')

forwarder = None
if config:
    print(f"📡 Forwarder activé")
    print(f"   Canaux: {config.source_channels}")
    print(f"   Format: {config.message_format}")
    forwarder = ForwarderService(
        webhook_url=config.webhook_url,
        source_channels=config.source_channels,
        use_embeds=(config.message_format == 'embed')
    )
else:
    print("ℹ️  Forwarder non configuré (voir config/forwarder.json)")

# Continuer avec le logger standard
import gateway_logger

if __name__ == '__main__':
    sys.exit(gateway_logger.main())
