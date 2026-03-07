"""Configuration loading for Wirecord.

The config file is a JSON file (default: config.json) at the project root.
Keys starting with '_' are treated as comments and ignored.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


DEFAULT_CONFIG_PATH = "config.json"


@dataclass
class ForwardRule:
    """One forwarding rule: N source channels → one webhook destination.

    Attributes:
        channels: Discord channel IDs to intercept.
        webhook_url: Discord webhook URL to forward messages to.
        webhook_username: Display name shown on forwarded messages.
        rate_limit_delay: Minimum seconds between consecutive webhook POSTs.
    """

    channels: List[str] = field(default_factory=list)
    webhook_url: str = ""
    webhook_channel_id: str = ""
    webhook_username: str = "Interceptor"
    rate_limit_delay: float = 0.5

    @classmethod
    def from_dict(cls, data: dict) -> "ForwardRule":
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url and self.channels)


@dataclass
class Config:
    """Wirecord runtime configuration.

    Attributes:
        proxy_port: Port for the mitmproxy proxy server.
        traffic_archive_dir: Directory where raw captured traffic is stored.
        forwards: List of forwarding rules (channels → webhook).
    """

    proxy_port: int = 8080
    traffic_archive_dir: str = "traffic_archive"
    forwards: List[ForwardRule] = field(default_factory=list)

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
            data = {k: v for k, v in data.items() if not k.startswith("_")}
            forwards = [
                ForwardRule.from_dict(r)
                for r in data.get("forwards", [])
                if isinstance(r, dict)
            ]
            return cls(
                proxy_port=data.get("proxy_port", 8080),
                traffic_archive_dir=data.get("traffic_archive_dir", "traffic_archive"),
                forwards=forwards,
            )
        except (json.JSONDecodeError, TypeError):
            return cls()

    @property
    def forwarding_enabled(self) -> bool:
        """True when at least one rule is fully configured."""
        return any(r.enabled for r in self.forwards)
