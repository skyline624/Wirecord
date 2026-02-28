"""Domain layer for Discord Logger.

This package contains the core business entities and domain logic
for the Discord Logger application, following hexagonal architecture principles.
"""

from discord_logger.domain.message import DiscordMessage

__all__ = ["DiscordMessage"]
