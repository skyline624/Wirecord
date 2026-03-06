#!/usr/bin/env python3
"""Gateway Logger avec Webhook Discord."""

import os
import sys
sys.path.insert(0, 'src')

from discord_logger.forwarder import ForwarderService
from discord_logger.domain.message import DiscordMessage

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
FORWARD_CHANNELS = os.environ.get("DISCORD_FORWARD_CHANNELS", "").split(",")
FORWARD_CHANNELS = [c.strip() for c in FORWARD_CHANNELS if c.strip()]
USE_EMBEDS = os.environ.get("DISCORD_FORWARD_EMBEDS", "true").lower() == "true"

forwarder = None

if WEBHOOK_URL and FORWARD_CHANNELS:
    print(f"Webhook forwarder activé")
    print(f"Canaux: {FORWARD_CHANNELS}")
    forwarder = ForwarderService(
        webhook_url=WEBHOOK_URL,
        source_channels=FORWARD_CHANNELS,
        use_embeds=USE_EMBEDS
    )

# Importer le logger
import gateway_logger

if __name__ == "__main__":
    sys.exit(gateway_logger.main())
