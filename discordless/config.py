"""Configuration loading for Wirecord.

The config file is a JSON file (default: config.json) at the project root.
Keys starting with '_' are treated as comments and ignored.
"""

import json
import hashlib
import math
import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import List


DEFAULT_CONFIG_PATH = "config.json"

# Delivery modes for a forwarding rule.
MODE_WEBHOOK = "webhook"  # POST to a webhook URL as a rich message (default)
MODE_NATIVE = "native"  # POST as a real Discord "Forward" using an account token
VALID_MODES = (MODE_WEBHOOK, MODE_NATIVE)
ACCOUNT_ID = "462628780574375936"


class ConfigError(ValueError):
    """Safe configuration error: never includes a credential or raw value."""


@dataclass
class ForwardRule:
    """One forwarding rule: N source channels → one destination.

    Attributes:
        channels: Discord channel IDs to intercept.
        webhook_url: Discord webhook URL (webhook mode only).
        webhook_channel_id: Destination thread ID, when the target is a thread.
        webhook_username: Display name shown on forwarded messages (webhook mode only).
        rate_limit_delay: Minimum seconds between consecutive POSTs.
        forward_mode: ``webhook`` or ``native``; inherits the global mode when unset.
        dest_channel_id: Destination channel for native mode; falls back to
            ``webhook_channel_id`` so existing rules work unchanged.
        send_delay_min/send_delay_max: When both set (native mode), each forward
            waits a random delay drawn in this range — so no two posts share the
            same timing. Left unset, the fixed ``rate_limit_delay`` is used.
        user_ids: Native mode account pool. Each forward is posted by one account
            picked at random from this list. Empty falls back to the global
            ``user_id``.
    """

    channels: List[str] = field(default_factory=list)
    webhook_url: str = ""
    webhook_channel_id: str = ""
    webhook_username: str = "Interceptor"
    rate_limit_delay: float = 0.5
    forward_mode: str = MODE_WEBHOOK
    dest_channel_id: str = ""
    send_delay_min: float = 0.0
    send_delay_max: float = 0.0
    user_ids: List[str] = field(default_factory=list)
    rule_id: str = ""
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict, default_mode: str = MODE_WEBHOOK) -> "ForwardRule":
        """Build a rule from raw JSON, inheriting *default_mode* when unspecified."""
        known = cls.__dataclass_fields__
        rule = cls(**{k: v for k, v in data.items() if k in known})
        if not data.get("forward_mode"):
            rule.forward_mode = default_mode
        rule.forward_mode = str(rule.forward_mode).lower()
        if rule.forward_mode not in VALID_MODES:
            rule.forward_mode = MODE_WEBHOOK
        rule.user_ids = [str(u) for u in (rule.user_ids or [])]
        return rule

    @property
    def native(self) -> bool:
        """True when this rule posts real Discord forwards instead of webhook messages."""
        return self.forward_mode == MODE_NATIVE

    @property
    def destination(self) -> str:
        """Channel (or thread) ID that native forwards are posted to."""
        return str(self.dest_channel_id or self.webhook_channel_id or "")

    @property
    def delay_range(self) -> tuple:
        """``(min, max)`` seconds for the per-message delay before posting.

        Falls back to a fixed ``rate_limit_delay`` (min == max) when no valid
        ``send_delay_min``/``send_delay_max`` range is configured.
        """
        lo = float(self.send_delay_min or 0.0)
        hi = float(self.send_delay_max or 0.0)
        if hi > 0 and hi >= lo:
            return (lo, hi)
        return (float(self.rate_limit_delay), float(self.rate_limit_delay))

    def poster_ids(self, global_user_id: str = "") -> list:
        """Account ids that may post this rule's forwards (native mode).

        The rule's own ``user_ids`` win; otherwise the global ``user_id`` is used;
        otherwise an empty list (caller falls back to the first token found).
        """
        if self.user_ids:
            return list(self.user_ids)
        if global_user_id:
            return [str(global_user_id)]
        return []

    @property
    def enabled(self) -> bool:
        """True when the rule has everything its mode requires."""
        if not self.channels:
            return False
        if self.native:
            return bool(self.destination)
        return bool(self.webhook_url)


@dataclass
class Config:
    """Wirecord runtime configuration.

    Attributes:
        proxy_port: Port for the mitmproxy proxy server.
        traffic_archive_dir: Directory where raw captured traffic is stored.
        forward_mode: Default delivery mode for every rule (``webhook`` or ``native``).
        user_token: Discord account token for native mode. Left empty, the token
            is auto-detected from the local Discord client's leveldb store.
        user_id: Discord account id that native forwards should post as. When the
            client holds several accounts, this pins the poster to one of them
            (auto-detection otherwise takes the first token found). Ignored when
            ``user_token`` is set.
        forwards: List of forwarding rules (channels → destination).
    """

    proxy_port: int = 8080
    traffic_archive_dir: str = "traffic_archive"
    forward_mode: str = MODE_WEBHOOK
    user_token: str = ""
    user_id: str = ""
    forwards: List[ForwardRule] = field(default_factory=list)
    state_path: str = "state/wirecord.sqlite3"
    delivery_enabled: bool = False
    recovery_enabled: bool = True
    recovery_since: str = "2026-09-08T16:24:00Z"
    recovery_interval: float = 300

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "Config":
        """Load configuration from a JSON file.

        Missing or malformed files fail explicitly without exposing their content.

        Args:
            path: Path to the JSON config file.

        Returns:
            Config instance populated from the file.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ConfigError("Configuration must be an object")
            data = {k: v for k, v in data.items() if not k.startswith("_")}
            mode = str(data.get("forward_mode", MODE_WEBHOOK)).lower()
            if mode not in VALID_MODES:
                raise ConfigError("Invalid forward_mode")
            raw_rules = data.get("forwards", [])
            if not isinstance(raw_rules, list) or any(
                not isinstance(r, dict) for r in raw_rules
            ):
                raise ConfigError("forwards must be a list of objects")
            for r in raw_rules:
                if r.get("forward_mode", mode) not in VALID_MODES:
                    raise ConfigError("Invalid rule forward_mode")
            forwards = [ForwardRule.from_dict(r, mode) for r in raw_rules]
            cfg = cls(
                proxy_port=data.get("proxy_port", 8080),
                traffic_archive_dir=data.get("traffic_archive_dir", "traffic_archive"),
                forward_mode=mode,
                user_token=str(data.get("user_token", "") or ""),
                user_id=str(data.get("user_id", ACCOUNT_ID) or ACCOUNT_ID),
                forwards=forwards,
                state_path=data.get("state_path", "state/wirecord.sqlite3"),
                delivery_enabled=data.get("delivery_enabled", False),
                recovery_enabled=data.get("recovery_enabled", True),
                recovery_since=data.get("recovery_since", "2026-09-08T16:24:00Z"),
                recovery_interval=data.get("recovery_interval", 300),
            )
            cfg.validate()
            return cfg
        except ConfigError:
            raise
        except (OSError, ValueError, TypeError, AttributeError):
            raise ConfigError(
                "Cannot load configuration: missing, malformed or invalid file"
            ) from None

    def validate(self):
        if type(self.proxy_port) is not int or not 1 <= self.proxy_port <= 65535:
            raise ConfigError("Invalid proxy_port")
        if self.user_id != ACCOUNT_ID:
            raise ConfigError("Only the configured Jarl Panda account is permitted")
        if self.user_token:
            import base64

            try:
                owner = base64.urlsafe_b64decode(
                    self.user_token.split(".")[0] + "==="
                ).decode()
            except Exception:
                raise ConfigError("Invalid user_token account encoding") from None
            if owner != ACCOUNT_ID:
                raise ConfigError("user_token belongs to a disallowed account")
        for key in ("delivery_enabled", "recovery_enabled"):
            if type(getattr(self, key)) is not bool:
                raise ConfigError(f"{key} must be boolean")
        for key in ("state_path", "traffic_archive_dir"):
            if (
                not isinstance(getattr(self, key), str)
                or not getattr(self, key).strip()
            ):
                raise ConfigError(f"Invalid {key}")
        dt = datetime.fromisoformat(self.recovery_since.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ConfigError("recovery_since must include timezone")
        if (
            isinstance(self.recovery_interval, bool)
            or not math.isfinite(float(self.recovery_interval))
            or float(self.recovery_interval) < 1
        ):
            raise ConfigError("Invalid recovery_interval")
        self.recovery_interval = float(self.recovery_interval)
        ids = set()
        routes = set()
        for rule in self.forwards:
            if (
                not isinstance(rule.channels, list)
                or not rule.channels
                or any(not str(c).isdigit() for c in rule.channels)
            ):
                raise ConfigError("Invalid source channels")
            rule.channels = [str(c) for c in rule.channels]
            if any(uid != ACCOUNT_ID for uid in rule.user_ids):
                raise ConfigError("Rule contains disallowed account")
            if rule.native and not rule.destination.isdigit():
                raise ConfigError("Native rule requires destination channel ID")
            if not rule.native and not rule.destination.isdigit():
                raise ConfigError("Webhook rule requires destination channel ID")
            if not rule.native and not re.fullmatch(
                r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api(?:/v\d+)?/webhooks/\d+/[^/?#]+",
                rule.webhook_url,
            ):
                raise ConfigError("Invalid webhook destination")
            if rule.webhook_channel_id and not str(rule.webhook_channel_id).isdigit():
                raise ConfigError("Invalid webhook channel ID")
            for name in ("rate_limit_delay", "send_delay_min", "send_delay_max"):
                v = getattr(rule, name)
                if isinstance(v, bool) or not math.isfinite(float(v)) or float(v) < 0:
                    raise ConfigError("Invalid rule delay")
            if float(rule.send_delay_max) < float(rule.send_delay_min):
                raise ConfigError("Invalid rule delay range")
            identity = json.dumps(
                [
                    sorted(rule.channels),
                    rule.forward_mode,
                    rule.destination,
                    rule.webhook_url.split("/")[-2] if not rule.native else "",
                ]
            )
            rule.rule_id = (
                rule.rule_id or hashlib.sha256(identity.encode()).hexdigest()[:16]
            )
            if (
                not isinstance(rule.rule_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", rule.rule_id)
                or rule.rule_id in ids
            ):
                raise ConfigError("Invalid or duplicate rule_id")
            ids.add(rule.rule_id)
            rule.label = (
                rule.label
                or f"{','.join(rule.channels)} -> {rule.destination or 'webhook'}"
            )
            if not isinstance(rule.label, str):
                raise ConfigError("Invalid rule label")
            for channel in rule.channels:
                route = (channel, rule.destination or rule.webhook_url)
                if route in routes:
                    raise ConfigError("Duplicate source/destination route")
                routes.add(route)

    @property
    def forwarding_enabled(self) -> bool:
        """True when at least one rule is fully configured."""
        return any(r.enabled for r in self.forwards)

    @property
    def native_enabled(self) -> bool:
        """True when at least one enabled rule posts native Discord forwards."""
        return any(r.enabled and r.native for r in self.forwards)
