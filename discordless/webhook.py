"""Webhook forwarder — sends captured Discord messages to a Discord webhook."""
import hashlib
import time

import requests  # type: ignore

from discordless.models import DiscordMessage


def _author_color(author: str) -> int:
    """Deterministic color per author — same name always gives the same color."""
    h = int(hashlib.md5(author.encode()).hexdigest()[:6], 16)
    # Ensure minimum brightness so the color is visible on dark backgrounds
    r, g, b = (h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF
    r, g, b = max(r, 80), max(g, 80), max(b, 80)
    return (r << 16) | (g << 8) | b


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
        username: str = "Interceptor",
        channel_id: str = "",
        rate_limit_delay: float = 0.5,
    ) -> None:
        # For forum/thread channels, thread_id is required.
        # For regular text channels, leave channel_id empty — the webhook URL
        # already targets the correct channel.
        self.url = f"{url}?thread_id={channel_id}" if channel_id else url
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

        channel_label = f"#{msg.channel_name}" if msg.channel_name else f"#{msg.channel_id}"
        payload = {
            "username": f"@{msg.author} · {channel_label}",
            "content": msg.content[:2000],
        }
        if msg.author_id and msg.author_avatar:
            payload["avatar_url"] = (
                f"https://cdn.discordapp.com/avatars/{msg.author_id}/{msg.author_avatar}.png?size=128"
            )

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
