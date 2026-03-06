"""Tests for discordless.decoder."""
import json
import zlib

import pytest

from discordless.decoder import GatewayDecoder


def _zlib_wrap(data: dict) -> bytes:
    """Compress a dict as a complete zlib-stream message (with sync marker)."""
    raw = json.dumps(data).encode()
    compressed = zlib.compress(raw)
    # A real zlib-stream message ends with the sync marker
    # We simulate it by appending the marker if not already present
    if not compressed.endswith(b"\x00\x00\xff\xff"):
        compressed += b"\x00\x00\xff\xff"
    return compressed


class TestGatewayDecoderNoCompression:
    def test_decodes_plain_json(self, gateway_url_json):
        decoder = GatewayDecoder(gateway_url_json)
        payload = {"t": "MESSAGE_CREATE", "op": 0}
        chunk = json.dumps(payload).encode()
        result = decoder.feed(chunk)
        assert result == payload

    def test_returns_none_for_empty_chunk(self, gateway_url_json):
        decoder = GatewayDecoder(gateway_url_json)
        assert decoder.feed(b"") is None

    def test_returns_none_for_invalid_json(self, gateway_url_json):
        decoder = GatewayDecoder(gateway_url_json)
        assert decoder.feed(b"not json") is None


class TestGatewayDecoderZlib:
    def test_incomplete_chunk_returns_none(self, gateway_url_zlib):
        decoder = GatewayDecoder(gateway_url_zlib)
        # Feed partial data without the zlib sync marker
        result = decoder.feed(b"\x78\x9c")
        assert result is None

    def test_reset_clears_buffer(self, gateway_url_zlib):
        decoder = GatewayDecoder(gateway_url_zlib)
        decoder.feed(b"\x78\x9c")  # partial data
        decoder.reset()
        # After reset, a fresh valid message should decode correctly
        payload = {"t": "READY", "op": 0}
        chunk = _zlib_wrap(payload)
        result = decoder.feed(chunk)
        assert result == payload


class TestGatewayDecoderUrlParsing:
    def test_json_encoding_detected(self, gateway_url_json):
        decoder = GatewayDecoder(gateway_url_json)
        assert decoder._encoding == "json"

    def test_zlib_compression_detected(self, gateway_url_zlib):
        decoder = GatewayDecoder(gateway_url_zlib)
        assert decoder._compression == "zlib-stream"

    def test_no_compression_when_absent(self, gateway_url_json):
        decoder = GatewayDecoder(gateway_url_json)
        assert decoder._compression is None
