"""Tests for discordless.webhook."""
from unittest.mock import MagicMock, patch

import pytest

from discordless.models import DiscordMessage
from discordless.webhook import WebhookForwarder


@pytest.fixture
def forwarder():
    return WebhookForwarder(
        url="https://discord.com/api/webhooks/test/token",
        username="TestBot",
        rate_limit_delay=0.0,
    )


@pytest.fixture
def message():
    return DiscordMessage(
        channel_id="111111111111111111",
        author="testuser",
        content="Hello!",
        timestamp="2024-01-15T10:30:00.000Z",
    )


class TestWebhookForwarder:
    def test_returns_true_on_204(self, forwarder, message):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch("discordless.webhook.requests.post", return_value=mock_resp):
            result = forwarder.forward(message)
        assert result is True
        assert forwarder.stats["sent"] == 1
        assert forwarder.stats["errors"] == 0

    def test_returns_false_on_non_204(self, forwarder, message):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch("discordless.webhook.requests.post", return_value=mock_resp):
            result = forwarder.forward(message)
        assert result is False
        assert forwarder.stats["errors"] == 1

    def test_returns_false_on_request_exception(self, forwarder, message):
        import requests as req
        with patch("discordless.webhook.requests.post", side_effect=req.RequestException):
            result = forwarder.forward(message)
        assert result is False
        assert forwarder.stats["errors"] == 1

    def test_payload_contains_embed_with_content(self, forwarder, message):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch("discordless.webhook.requests.post", return_value=mock_resp) as mock_post:
            forwarder.forward(message)
        call_kwargs = mock_post.call_args.kwargs
        payload = call_kwargs["json"]
        assert payload["username"] == "TestBot"
        assert len(payload["embeds"]) == 1
        assert payload["embeds"][0]["description"] == "Hello!"

    def test_content_truncated_to_2000_chars(self, forwarder):
        long_msg = DiscordMessage("123", "user", "x" * 3000, "2024-01-01T00:00:00Z")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch("discordless.webhook.requests.post", return_value=mock_resp) as mock_post:
            forwarder.forward(long_msg)
        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["embeds"][0]["description"]) == 2000
