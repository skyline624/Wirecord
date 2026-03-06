"""Tests for discordless.config."""
import json
from pathlib import Path

import pytest

from discordless.config import Config


class TestConfigLoad:
    def test_defaults_when_file_missing(self, tmp_path):
        cfg = Config.load(str(tmp_path / "nonexistent.json"))
        assert cfg.proxy_port == 8080
        assert cfg.intercept_channels == []
        assert cfg.webhook_url == ""
        assert cfg.forwarding_enabled is False

    def test_loads_values_from_file(self, minimal_config_file):
        cfg = Config.load(minimal_config_file)
        assert cfg.proxy_port == 8080
        assert cfg.intercept_channels == ["111111111111111111"]
        assert cfg.webhook_url == "https://discord.com/api/webhooks/test/token"
        assert cfg.webhook_username == "TestBot"
        assert cfg.rate_limit_delay == 0.0

    def test_strips_comment_keys(self, tmp_path):
        data = {"_comment": "ignored", "proxy_port": 9090}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data))
        cfg = Config.load(str(p))
        assert cfg.proxy_port == 9090

    def test_ignores_unknown_keys(self, tmp_path):
        data = {"proxy_port": 1234, "unknown_key": "value"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data))
        cfg = Config.load(str(p))
        assert cfg.proxy_port == 1234

    def test_defaults_on_invalid_json(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("not valid json")
        cfg = Config.load(str(p))
        assert cfg.proxy_port == 8080


class TestForwardingEnabled:
    def test_disabled_when_no_webhook(self):
        cfg = Config(webhook_url="", intercept_channels=["123"])
        assert cfg.forwarding_enabled is False

    def test_disabled_when_no_channels(self):
        cfg = Config(webhook_url="https://example.com/webhook", intercept_channels=[])
        assert cfg.forwarding_enabled is False

    def test_enabled_when_both_set(self):
        cfg = Config(
            webhook_url="https://example.com/webhook",
            intercept_channels=["123"],
        )
        assert cfg.forwarding_enabled is True
