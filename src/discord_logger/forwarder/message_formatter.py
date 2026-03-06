"""Formattage des messages pour webhook Discord."""
from typing import Dict
from discord_logger.domain.message import DiscordMessage

class MessageFormatter:
    """Formatte les messages pour Discord webhook."""

    def format_simple(self, msg: DiscordMessage) -> str:
        """Format texte simple."""
        return f"**[{msg.channel_id[-8:]}]** @{msg.author}: {msg.content}"

    def format_embed(self, msg: DiscordMessage) -> Dict:
        """Format rich embed."""
        return {
            "title": f"Message dans #{msg.channel_id[-8:]}",
            "description": msg.content[:2000] if len(msg.content) > 2000 else msg.content,
            "color": 3447003,
            "fields": [
                {"name": "Auteur", "value": f"@{msg.author}", "inline": True},
                {"name": "Canal source", "value": msg.channel_id, "inline": True}
            ],
            "timestamp": msg.timestamp
        }
