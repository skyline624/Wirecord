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
            ctx.log.warn(f"☎️  Wirecord: webhook HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except requests.RequestException as e:
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Wirecord: webhook request failed: {e}")
            return False

    def forward_and_get_id(self, msg: DiscordMessage) -> tuple | None:
        """Like :meth:`forward` but uses ``?wait=true`` to get the created message ID.

        Returns:
            ``(webhook_msg_id, channel_id, guild_id)`` on success, ``None`` on failure.
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

        wait_url = self.url + ("&wait=true" if "?" in self.url else "?wait=true")
        try:
            resp = requests.post(wait_url, json=payload, timeout=10)
            self._last_sent = time.time()
            if resp.status_code == 200:
                self.stats["sent"] += 1
                data = resp.json()
                return (str(data.get("id") or ""), str(data.get("channel_id") or ""), str(data.get("guild_id") or ""))
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Wirecord: webhook HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        except requests.RequestException as e:
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Wirecord: webhook request failed: {e}")
            return None

    def forward_edit_notification(
        self,
        original_msg_id: str,
        webhook_channel_id: str,
        guild_id: str,
        new_content: str,
        author: str,
        author_id: str = "",
        author_avatar: str = "",
    ) -> bool:
        """Send an edit-notification for a previously forwarded message.

        Args:
            original_msg_id: ID of the webhook message that was originally forwarded.
            webhook_channel_id: Channel ID where the webhook message lives.
            guild_id: Guild ID (used to build the message link).
            new_content: The updated message content.
            author: Display name of the author.
            author_id: Discord user ID (for avatar URL).
            author_avatar: Avatar hash (for avatar URL).

        Returns:
            True on HTTP 204 (success), False otherwise.
        """
        elapsed = time.time() - self._last_sent
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        link = f"https://discord.com/channels/{guild_id}/{webhook_channel_id}/{original_msg_id}"
        content = f"✏️ **Edited** — [original message]({link})\n{new_content[:1800]}"
        payload = {
            "username": f"@{author} (edit)",
            "content": content,
        }
        if author_id and author_avatar:
            payload["avatar_url"] = (
                f"https://cdn.discordapp.com/avatars/{author_id}/{author_avatar}.png?size=128"
            )

        try:
            resp = requests.post(self.url, json=payload, timeout=10)
            self._last_sent = time.time()
            if resp.status_code == 204:
                self.stats["sent"] += 1
                return True
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Wirecord: edit-notification HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except requests.RequestException as e:
            self.stats["errors"] += 1
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(f"☎️  Wirecord: webhook request failed: {e}")
            return False
