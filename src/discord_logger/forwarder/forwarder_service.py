"""Service de retransmission des messages."""
from typing import Optional, Set
from discord_logger.domain.message import DiscordMessage
from .webhook_client import WebhookClient, WebhookMessage
from .message_formatter import MessageFormatter

class ForwarderService:
    """Service de retransmission des messages vers webhook."""

    def __init__(
        self,
        webhook_url: str,
        source_channels: list[str],
        use_embeds: bool = True
    ):
        self.webhook = WebhookClient(webhook_url)
        self.formatter = MessageFormatter()
        self.source_channels: Set[str] = set(source_channels)
        self.use_embeds = use_embeds
        self.stats = {"forwarded": 0, "skipped": 0, "errors": 0}

    def should_forward(self, msg: DiscordMessage) -> bool:
        """Vérifie si le message doit être retransmis."""
        return msg.channel_id in self.source_channels

    def forward(self, msg: DiscordMessage) -> bool:
        """Retransmet un message via webhook."""
        if not self.should_forward(msg):
            self.stats["skipped"] += 1
            return False

        try:
            if self.use_embeds:
                embed = self.formatter.format_embed(msg)
                webhook_msg = WebhookMessage(content="", embeds=[embed])
            else:
                content = self.formatter.format_simple(msg)
                webhook_msg = WebhookMessage(content=content)

            success = self.webhook.send(webhook_msg)
            if success:
                self.stats["forwarded"] += 1
            else:
                self.stats["errors"] += 1
            return success
        except Exception as e:
            print(f"Erreur forwarding: {e}")
            self.stats["errors"] += 1
            return False
