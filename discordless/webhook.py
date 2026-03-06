"""Webhook forwarder — sends captured Discord messages to a Discord webhook."""
import time

import requests  # type: ignore

from discordless.models import DiscordMessage

_EMBED_COLOR = 5793266  # #587B32 muted green


class WebhookForwarder:
    """Sends :class:`DiscordMessage` objects to a Discord webhook as rich embeds.

    Attributes:
        url: Discord webhook URL.
        username: Display name shown on forwarded messages.
        rate_limit_delay: Minimum seconds between consecutive requests.
        stats: Running counters — ``sent`` and ``errors``.
    """

    def __init__(
        self,
        url: str,
        username: str = "Discordless",
        rate_limit_delay: float = 0.5,
    ) -> None:
        self.url = url
        self.username = username
        self.rate_limit_delay = rate_limit_delay
        self._last_sent: float = 0.0
        self.stats: dict = {"sent": 0, "errors": 0}

    def forward(self, msg: DiscordMessage) -> bool:
        """Forward a message to the webhook.

        Blocks briefly to respect :attr:`rate_limit_delay`.

        Args:
            msg: The Discord message to send.

        Returns:
            True on HTTP 204 (success), False otherwise.
        """
        elapsed = time.time() - self._last_sent
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        payload = {
            "username": self.username,
            "embeds": [
                {
                    "description": msg.content[:2000],
                    "color": _EMBED_COLOR,
                    "fields": [
                        {"name": "Author", "value": f"@{msg.author}", "inline": True},
                        {"name": "Channel", "value": msg.channel_id, "inline": True},
                    ],
                    "timestamp": msg.timestamp,
                }
            ],
        }

        try:
            resp = requests.post(self.url, json=payload, timeout=10)
            self._last_sent = time.time()
            if resp.status_code == 204:
                self.stats["sent"] += 1
                return True
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Discordless: webhook HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except requests.RequestException as e:
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Discordless: webhook request failed: {e}")
            return False
