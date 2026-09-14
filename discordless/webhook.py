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


def split_content(text: str, limit: int = 2000) -> list:
    """Split ``text`` into chunks of at most ``limit`` characters.

    Discord webhooks cap a single message's content at 2000 characters, so a
    longer source message (e.g. a Nitro author's 4000-char post) must be sent
    as several consecutive webhook messages instead of being truncated.

    Breaks are preferred on newline boundaries so markdown stays intact; a
    single line longer than ``limit`` is hard-cut as a last resort.

    Returns:
        A list of chunks (empty list if ``text`` is empty).
    """
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining[:limit].rfind("\n")
        if cut <= 0:
            cut = limit  # no newline to break on — hard cut
        chunks.append(remaining[:cut].rstrip("\n"))
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


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

    def _wait_for_rate_limit(self) -> None:
        """Block until at least :attr:`rate_limit_delay` has passed since the last send."""
        elapsed = time.time() - self._last_sent
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

    def _payload(self, content: str, msg: DiscordMessage) -> dict:
        """Build the webhook payload for a single content chunk."""
        channel_label = f"#{msg.channel_name}" if msg.channel_name else f"#{msg.channel_id}"
        payload = {
            "username": f"@{msg.author} · {channel_label}",
            "content": content,
        }
        if msg.author_id and msg.author_avatar:
            payload["avatar_url"] = (
                f"https://cdn.discordapp.com/avatars/{msg.author_id}/{msg.author_avatar}.png?size=128"
            )
        return payload

    @staticmethod
    def _log_warn(message: str) -> None:
        """Best-effort warning log via mitmproxy ctx (no-op outside mitmdump)."""
        try:
            from mitmproxy import ctx  # type: ignore
            ctx.log.warn(message)
        except Exception:
            pass

    def _post_with_retry(self, url: str, payload: dict, max_retries: int = 5):
        """POST one payload, pacing per ``rate_limit_delay`` and retrying on HTTP 429.

        Returns the final :class:`requests.Response`, or ``None`` if the request
        raised (network error). A 429 reply is honored via its ``retry_after``
        so no chunk is silently dropped under Discord's webhook rate limit.
        """
        resp = None
        for _ in range(max_retries):
            self._wait_for_rate_limit()
            try:
                resp = requests.post(url, json=payload, timeout=10)
            except requests.RequestException as e:
                self._last_sent = time.time()
                self._log_warn(f"☎️  Wirecord: webhook request failed: {e}")
                return None
            self._last_sent = time.time()
            if resp.status_code != 429:
                return resp
            try:
                retry_after = float(resp.json().get("retry_after", 1.0))
            except Exception:
                retry_after = 1.0
            self._log_warn(f"☎️  Wirecord: webhook 429 — retrying after {retry_after}s")
            time.sleep(retry_after + 0.3)
        return resp  # exhausted retries — still 429

    def forward(self, msg: DiscordMessage) -> bool:
        """Forward a message to the webhook.

        Content longer than 2000 characters is split into several consecutive
        posts (Discord's per-message limit) rather than truncated. Each post is
        paced by :attr:`rate_limit_delay` and retried on HTTP 429.

        Args:
            msg: The Discord message to send.

        Returns:
            True only if every chunk was accepted (HTTP 204), False otherwise.
        """
        chunks = split_content(msg.content)
        if not chunks:
            return True
        ok = True
        for chunk in chunks:
            resp = self._post_with_retry(self.url, self._payload(chunk, msg))
            if resp is not None and resp.status_code == 204:
                self.stats["sent"] += 1
                continue
            self.stats["errors"] += 1
            ok = False
            if resp is not None:
                self._log_warn(f"☎️  Wirecord: webhook HTTP {resp.status_code}: {resp.text[:200]}")
        return ok

    def forward_and_get_id(self, msg: DiscordMessage) -> tuple | None:
        """Like :meth:`forward` but uses ``?wait=true`` to get the created message ID.

        Long content is split into several posts; the returned ID is that of the
        first chunk (so edit-notifications link to the start of the message).
        Each post is paced and retried on HTTP 429.

        Returns:
            ``(webhook_msg_id, channel_id, guild_id)`` of the first chunk on
            success, ``None`` if the first chunk fails.
        """
        chunks = split_content(msg.content)
        if not chunks:
            return None

        result: tuple | None = None
        for i, chunk in enumerate(chunks):
            # Only the first chunk needs ?wait=true to capture the message id.
            url = self.url + ("&wait=true" if "?" in self.url else "?wait=true") if i == 0 else self.url
            resp = self._post_with_retry(url, self._payload(chunk, msg))
            ok_status = resp is not None and (
                resp.status_code == 200 if i == 0 else resp.status_code in (200, 204)
            )
            if ok_status:
                self.stats["sent"] += 1
                if i == 0:
                    data = resp.json()
                    result = (
                        str(data.get("id") or ""),
                        str(data.get("channel_id") or ""),
                        str(data.get("guild_id") or ""),
                    )
                continue
            self.stats["errors"] += 1
            if resp is not None:
                self._log_warn(f"☎️  Wirecord: webhook HTTP {resp.status_code}: {resp.text[:200]}")
            if i == 0:
                return None
        return result

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
