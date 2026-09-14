"""Wirecord mitmproxy addon.

Intercepts Discord traffic (REST API + Gateway WebSocket), archives it to
``traffic_archive/`` in the same binary format as the original
``wumpus_in_the_middle.py`` (compatible with ``exporter.py``), and
optionally forwards messages from configured channels to a Discord webhook.

Usage::

    mitmdump -s discordless/addon.py \\
        --listen-port=8080 \\
        --allow-hosts '^(((.+\\.)?discord\\.com)|((.+\\.)?discordapp\\.com)|((.+\\.)?discord\\.net)|((.+\\.)?discordapp\\.net)|((.+\\.)?discord\\.gg))(?:\\:\\d+)?$'
"""
import os
import sys
import time

# Ensure the project root is on sys.path so 'discordless' is importable
# regardless of the working directory mitmdump is launched from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:

    sys.path.insert(0, _PROJECT_ROOT)

from typing import Dict, Set
from urllib.parse import urlparse

from mitmproxy import ctx, http  # type: ignore

from discordless.archive import ArchiveWriter
from discordless.runtime import Runtime
from discordless.config import Config
from discordless.decoder import GatewayDecoder

# Domains whose traffic is archived (mirrors wumpus_in_the_middle.py)

_DISCORD_DOMAINS: Set[str] = {
    "discord.com",
    "discordapp.com",
    "discord.net",
    "discordapp.net",
    "discord.gg",
    "dis.gd",
    "discord.co",
    "discord.app",
    "discord.dev",
    "discord.new",
    "discord.gift",
    "discord.gifts",
    "discord.media",
    "discord.store",
    "discordstatus.com",
    "bigbeans.solutions",
    "watchanimeattheoffice.com",
}

# Regex passed to --allow-hosts to restrict mitmproxy to Discord traffic only
ALLOW_HOSTS = (
    r"^(((.+\.)?discord\.com)|((.+\.)?discordapp\.com)"
    r"|((.+\.)?discord\.net)|((.+\.)?discordapp\.net)"
    r"|((.+\.)?discord\.gg))(?::\d+)?$"
)


def _is_discord(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return any(hostname == d or hostname.endswith(f".{d}") for d in _DISCORD_DOMAINS)


def _is_gateway(url: str) -> bool:
    return _is_discord(url) and "gateway" in url.lower()


def _safe_filename(s: str) -> str:
    """Return a filesystem-safe version of *s*, max 255 chars."""
    return "".join(c if c.isalnum() or c == "." else "_" for c in s).rstrip()[:255]


def _log(msg: str) -> None:
    ctx.log.info(f"☎️  Wirecord: {msg}")


class _Gatekeeper:
    """Writes raw compressed Gateway chunks to ``{prefix}_data`` + ``{prefix}_timeline``."""

    def __init__(self, data_path: str, timeline_path: str) -> None:
        # "x" mode = exclusive create — raises FileExistsError if file already exists
        self._data = open(data_path, "xb", buffering=0)
        self._timeline = open(timeline_path, "x", buffering=1)

    def save(self, message: http.Message) -> None:  # type: ignore[name-defined]
        length = self._data.write(message.content)
        self._timeline.write(f"{message.timestamp} {length}\n")

    def close(self) -> None:
        self._data.close()
        self._timeline.close()


class WirecordAddon:
    """mitmproxy addon: archive Discord traffic and forward to webhook."""

    def __init__(self) -> None:
        self._config = Config()
        self._gatekeepers: Dict[int, _Gatekeeper] = {}
        self._decoders: Dict[int, GatewayDecoder] = {}
        self._gateway_count: int = 0
        self._channel_info: Dict[str, tuple] = {}  # channel_id → (channel_name, guild_name)
        self._archive: str = "traffic_archive"
        self._request_index = None
        self._gateway_index = None

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def running(self) -> None:
        """Called once the proxy is fully started and ready."""
        self._config = Config.load()
        self._archive = self._config.traffic_archive_dir

        requests_dir = os.path.join(self._archive, "requests")
        gateways_dir = os.path.join(self._archive, "gateways")
        os.makedirs(requests_dir, exist_ok=True)
        os.makedirs(gateways_dir, exist_ok=True)

        # Open index files in line-buffered mode so each write is flushed immediately
        self._request_index = open(
            os.path.join(self._archive, "request_index"), "a+", buffering=1
        )
        self._gateway_index = open(
            os.path.join(self._archive, "gateway_index"), "a+", buffering=1
        )

        self._writer = ArchiveWriter(self._archive)
        self._gateway_index.seek(0)
        self._gateway_count = max(
            (int(line.split()[-1]) + 1 for line in self._gateway_index if line.strip()), default=0)
        self._runtime = Runtime(self._config, self._writer)
        self._runtime.start()

        _log(f"archiving to {os.path.abspath(self._archive)}/")
        _log(f"next gateway ID: {self._gateway_count}")

    def done(self) -> None:
        """Flush and close all open file handles."""
        if getattr(self, '_runtime', None):
            self._runtime.close()
        if self._request_index:
            self._request_index.close()
        if self._gateway_index:
            self._gateway_index.close()
        for gk in self._gatekeepers.values():
            gk.close()

    # ------------------------------------------------------------------
    # HTTP responses (REST API)
    # ------------------------------------------------------------------

    def requestheaders(self, flow: http.HTTPFlow) -> None:
        """Stream file upload requests to avoid buffering large POST bodies."""
        if not _is_discord(flow.request.pretty_url):
            return
        if flow.request.method == "POST" and flow.request.pretty_url.endswith("/attachments"):
            _log("streaming attachment upload")
            flow.request.stream = True

    def response(self, flow: http.HTTPFlow) -> None:
        """Archive REST API responses, skipping exact duplicates."""
        url = flow.request.pretty_url
        if not _is_discord(url) or not flow.response.content:
            return

        self._writer.response(url, flow.response.content, flow.request.method, flow.response.timestamp_start)

    # ------------------------------------------------------------------
    # WebSocket Gateway
    # ------------------------------------------------------------------

    def websocket_message(self, flow: http.HTTPFlow) -> None:
        """Archive each Gateway chunk and forward MESSAGE_CREATE events."""
        if not _is_gateway(flow.request.pretty_url):
            return

        message = flow.websocket.messages[-1]
        if message.from_client:
            return  # Only process server → client messages

        flow_key = id(flow)

        # Lazily initialise Gatekeeper + Decoder on first message for this flow
        if flow_key not in self._gatekeepers:
            prefix = str(self._gateway_count)
            self._gateway_count += 1
            gateways_dir = os.path.join(self._archive, "gateways")
            self._gatekeepers[flow_key] = _Gatekeeper(
                os.path.join(gateways_dir, f"{prefix}_data"),
                os.path.join(gateways_dir, f"{prefix}_timeline"),
            )
            self._decoders[flow_key] = GatewayDecoder(flow.request.pretty_url)
            ts = flow.response.timestamp_start if flow.response else time.time()
            self._gateway_index.write(
                f"{ts} {flow.request.pretty_url} {prefix}\n"
            )
            _log(f"new gateway connection #{prefix}")

        # Archive raw compressed chunk (preserves binary format for exporters)
        self._gatekeepers[flow_key].save(message)

        # Decode and optionally forward
        payload = self._decoders[flow_key].feed(message.content)
        if not isinstance(payload, dict):
            _log(f"DBG chunk={len(message.content)}b type={type(payload).__name__} first4={message.content[:4].hex()}")
            return
        self._runtime.observe(flow_key, payload)
        t = payload.get("t")
        _log(f"DBG decoded t={t!r}")
        if t == "READY":
            self._index_channels_ready(payload.get("d", {}))
        elif t == "GUILD_CREATE":
            self._index_channels_guild(payload.get("d", {}))
        elif t in ("CHANNEL_CREATE", "CHANNEL_UPDATE"):
            self._index_channel(payload.get("d", {}))
        elif t == "MESSAGE_CREATE":
            _log(f"MESSAGE_CREATE channel={payload.get('d', {}).get('channel_id')}")
            self._maybe_forward(payload.get("d", {}))
        elif t == "MESSAGE_UPDATE":
            _log(f"MESSAGE_UPDATE channel={payload.get('d', {}).get('channel_id')}")
            self._maybe_forward_edit(payload.get("d", {}))

    def websocket_end(self, flow: http.HTTPFlow) -> None:
        """Clean up state when a Gateway connection closes."""
        flow_key = id(flow)
        self._runtime.health.disconnected(flow_key)
        gk = self._gatekeepers.pop(flow_key, None)
        if gk:
            gk.close()
        self._decoders.pop(flow_key, None)
        _log("gateway connection closed")

    # ------------------------------------------------------------------
    # Forwarding
    # ------------------------------------------------------------------

    def _index_channels_guild(self, d: dict) -> None:
        """Build channel_id → (channel_name, guild_name) from a GUILD_CREATE payload."""
        guild_name = str(d.get("name", ""))
        for ch in d.get("channels", []):
            if not isinstance(ch, dict):
                continue
            cid = str(ch.get("id", ""))
            cname = str(ch.get("name", ""))
            if cid:
                self._channel_info[cid] = (cname, guild_name)

    def _index_channel(self, d: dict) -> None:
        """Update channel_id → (channel_name, guild_name) from a CHANNEL_CREATE/UPDATE payload."""
        cid = str(d.get("id", ""))
        cname = str(d.get("name", ""))
        if not cid or not cname:
            return
        _, existing_guild = self._channel_info.get(cid, ("", ""))
        self._channel_info[cid] = (cname, existing_guild)

    def _index_channels_ready(self, d: dict) -> None:
        """Build channel_id → (channel_name, guild_name) from a READY payload.

        In practice READY guilds are often unavailable stubs — real data comes
        via GUILD_CREATE events handled by :meth:`_index_channels_guild`.
        """
        for guild in d.get("guilds", []):
            if not isinstance(guild, dict):
                continue
            guild_name = str(guild.get("name", ""))
            for ch in guild.get("channels", []):
                if not isinstance(ch, dict):
                    continue
                cid = str(ch.get("id", ""))
                cname = str(ch.get("name", ""))
                if cid:
                    self._channel_info[cid] = (cname, guild_name)

    def _maybe_forward(self, d: dict) -> None:
        channel_name, _ = self._channel_info.get(str(d.get('channel_id', '')), ('', ''))
        self._runtime.capture(d, channel_name)

    def _maybe_forward_edit(self, d: dict) -> None:
        self._runtime.edit(d)


addons = [WirecordAddon()]
