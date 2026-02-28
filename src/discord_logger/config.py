"""Configuration module for Discord Logger.

This module provides configuration management using dataclasses.
When Pydantic is available, this can be migrated to Pydantic Settings.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class DiscordLoggerConfig:
    """Configuration for Discord Logger.

    Attributes:
        log_dir: Directory for log files.
        archive_dir: Directory for archived capture files.
        persistence_file: File for persistence data (dedup keys).
        channel_ids: List of channel IDs to monitor.
        scan_interval: Interval in seconds between directory scans.
        save_interval: Interval in seconds between persistence saves.
        max_keys: Maximum number of deduplication keys to store.
    """
    log_dir: Path = field(default_factory=lambda: Path("logs"))
    archive_dir: Path = field(default_factory=lambda: Path("traffic_archive"))
    persistence_file: Path = field(default_factory=lambda: Path(".persistence"))
    channel_ids: List[str] = field(default_factory=list)
    scan_interval: int = 5
    save_interval: int = 30
    max_keys: int = 10000

    @classmethod
    def from_env(cls) -> "DiscordLoggerConfig":
        """Create configuration from environment variables.

        Environment variables:
            DISCORD_LOG_DIR: Log directory path.
            DISCORD_ARCHIVE_DIR: Archive directory path.
            DISCORD_PERSISTENCE_FILE: Persistence file path.
            DISCORD_CHANNEL_IDS: Comma-separated list of channel IDs.
            DISCORD_SCAN_INTERVAL: Scan interval in seconds.
            DISCORD_SAVE_INTERVAL: Save interval in seconds.
            DISCORD_MAX_KEYS: Maximum number of deduplication keys.

        Returns:
            Configured DiscordLoggerConfig instance.
        """
        log_dir = Path(os.getenv("DISCORD_LOG_DIR", "logs"))
        archive_dir = Path(os.getenv("DISCORD_ARCHIVE_DIR", "traffic_archive"))
        persistence_file = Path(os.getenv("DISCORD_PERSISTENCE_FILE", ".persistence"))

        channel_ids_str = os.getenv("DISCORD_CHANNEL_IDS", "")
        channel_ids = [c.strip() for c in channel_ids_str.split(",") if c.strip()]

        scan_interval = int(os.getenv("DISCORD_SCAN_INTERVAL", "5"))
        save_interval = int(os.getenv("DISCORD_SAVE_INTERVAL", "30"))
        max_keys = int(os.getenv("DISCORD_MAX_KEYS", "10000"))

        return cls(
            log_dir=log_dir,
            archive_dir=archive_dir,
            persistence_file=persistence_file,
            channel_ids=channel_ids,
            scan_interval=scan_interval,
            save_interval=save_interval,
            max_keys=max_keys
        )

    def ensure_directories(self) -> None:
        """Create necessary directories if they do not exist."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def __str__(self) -> str:
        """String representation of configuration."""
        lines = [
            "DiscordLoggerConfig(",
            f"  log_dir={self.log_dir},",
            f"  archive_dir={self.archive_dir},",
            f"  persistence_file={self.persistence_file},",
            f"  channel_ids={self.channel_ids},",
            f"  scan_interval={self.scan_interval}s,",
            f"  save_interval={self.save_interval}s,",
            f"  max_keys={self.max_keys}",
            ")"
        ]
        return "\n".join(lines)