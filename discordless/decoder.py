"""Real-time decoder for Discord Gateway WebSocket messages.

Discord Gateway connections use transport-level stream compression (not
per-message), so a stateful decoder object must be kept alive for the
lifetime of each WebSocket connection.

Supported compression : zlib-stream, zstd-stream
Supported encoding    : json, etf (Erlang Term Format via erlpack)
"""
import json
import zlib
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

try:
    import pyzstd  # type: ignore

    _HAS_ZSTD = True
except ImportError:
    _HAS_ZSTD = False

try:
    import erlpack  # type: ignore

    _HAS_ERLPACK = True
except ImportError:
    _HAS_ERLPACK = False


def _deserialize_erlpack(payload: Any) -> Any:
    """Recursively convert erlpack Atom / bytes objects to plain Python types."""
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    if _HAS_ERLPACK and isinstance(payload, erlpack.Atom):
        return str(payload)
    if isinstance(payload, list):
        return [_deserialize_erlpack(item) for item in payload]
    if isinstance(payload, dict):
        return {_deserialize_erlpack(k): _deserialize_erlpack(v) for k, v in payload.items()}
    return payload


class GatewayDecoder:
    """Stateful decoder for one Discord Gateway WebSocket connection.

    Feed raw WebSocket chunks via :meth:`feed`; a complete decoded payload
    dict is returned when a full message has been assembled, otherwise None.
    """

    def __init__(self, url: str) -> None:
        """Initialise from a Gateway WebSocket URL.

        Args:
            url: WebSocket URL, e.g.
                 ``wss://gateway.discord.gg/?v=10&encoding=json&compress=zlib-stream``
        """
        params = parse_qs(urlparse(url).query)
        self._encoding: str = params.get("encoding", ["json"])[0].lower()
        compress = params.get("compress", [None])[0]
        self._compression: Optional[str] = compress.lower() if compress else None
        self._buffer = b""
        self._decompressor: Any = None
        self._reset_decompressor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def feed(self, chunk: bytes) -> Optional[Dict[str, Any]]:
        """Feed a raw WebSocket chunk and return a decoded payload if complete.

        Args:
            chunk: Raw bytes from a single WebSocket message frame.

        Returns:
            Decoded payload dict when a full message is available, else None.
        """
        if not chunk:
            return None

        if self._compression is None:
            return self._decode(chunk)

        self._buffer += chunk

        if self._compression == "zlib-stream":
            # A complete zlib-stream message ends with the sync marker 0x00 0x00 0xFF 0xFF
            if not self._buffer.endswith(b"\x00\x00\xff\xff"):
                return None
            try:
                data = self._decompressor.decompress(self._buffer)
                self._buffer = b""
                return self._decode(data)
            except zlib.error:
                self._buffer = b""
                return None

        if self._compression == "zstd-stream":
            # Discord zstd-stream is a single continuous zstd stream for the
            # lifetime of the connection — use the stateful decompressor, NOT
            # pyzstd.decompress() which requires a self-contained zstd frame.
            self._buffer = b""
            try:
                data = self._decompressor.decompress(chunk)
                return self._decode(data) if data else None
            except Exception:
                self._reset_decompressor()
                return None

        return None

    def reset(self) -> None:
        """Reset buffer and decompressor — call this on reconnect."""
        self._buffer = b""
        self._reset_decompressor()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _reset_decompressor(self) -> None:
        if self._compression == "zlib-stream":
            self._decompressor = zlib.decompressobj()
        elif self._compression == "zstd-stream" and _HAS_ZSTD:
            self._decompressor = pyzstd.ZstdDecompressor()
        else:
            self._decompressor = None

    def _decode(self, data: bytes) -> Optional[Dict[str, Any]]:
        if not data:
            return None
        try:
            if self._encoding == "etf" and _HAS_ERLPACK:
                return _deserialize_erlpack(erlpack.unpack(data))
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None
