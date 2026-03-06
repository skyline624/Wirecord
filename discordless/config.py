"""Configuration loading for Discordless.

The config file is a JSON file (default: config.json) at the project root.
Keys starting with '_' are treated as comments and ignored.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


DEFAULT_CONFIG_PATH = "config.json"


@dataclass
class Config:
    """Discordless runtime configuration.

    Attributes:
        proxy_port: Port for the mitmproxy proxy server.
        intercept_channels: Discord channel IDs whose messages will be forwarded.
        webhook_url: Discord webhook URL to send forwarded messages to.
        webhook_username: Display name shown on forwarded webhook messages.
        rate_limit_delay: Minimum seconds between consecutive webhook requests.
        traffic_archive_dir: Directory where raw captured traffic is stored.
    """

    proxy_port: int = 8080
    intercept_channels: List[str] = field(default_factory=list)
    webhook_url: str = ""
    webhook_channel_id: str = ""
    webhook_username: str = "Discordless"
    rate_limit_delay: float = 0.5
    traffic_archive_dir: str = "traffic_archive"

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "Config":
        """Load configuration from a JSON file.

        Falls back to default values for a missing or malformed file.

        Args:
            path: Path to the JSON config file.

        Returns:
            Config instance populated from the file.
        """
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Strip comment keys (keys starting with '_')
            data = {k: v for k, v in data.items() if not k.startswith("_")}
            known = cls.__dataclass_fields__
            return cls(**{k: v for k, v in data.items() if k in known})
        except (json.JSONDecodeError, TypeError):
            return cls()

    @property
    def forwarding_enabled(self) -> bool:
        """True when both a webhook URL and at least one channel are configured."""
        return bool(self.webhook_url and self.intercept_channels)
