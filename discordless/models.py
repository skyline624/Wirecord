"""Domain model for a captured Discord message."""
import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DiscordMessage:
    """An immutable captured Discord message.

    Attributes:
        channel_id: Discord channel snowflake ID.
        author: Username of the message author.
        content: Text content of the message.
        timestamp: ISO 8601 timestamp string from the Discord API.
    """

    channel_id: str
    author: str
    content: str
    timestamp: str

    @property
    def dedup_key(self) -> str:
        """Unique key for deduplication, derived from content + metadata."""
        h = hashlib.md5(
            f"{self.timestamp}:{self.author}:{self.content}".encode()
        ).hexdigest()[:16]
        return f"{self.channel_id}:{h}"

    def to_log_line(self) -> str:
        """Return a human-readable log line for this message."""
        try:
            dt = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            ts = self.timestamp
        short = self.channel_id[-8:] if len(self.channel_id) > 8 else self.channel_id
        return f"[{ts}] [#{short}] @{self.author}: {self.content}"
