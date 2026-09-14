"""Tests for discordless.webhook."""
from unittest.mock import MagicMock, patch

import pytest

from discordless.models import DiscordMessage
from discordless.webhook import WebhookForwarder, split_content


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

    def test_payload_contains_content(self, forwarder, message):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch("discordless.webhook.requests.post", return_value=mock_resp) as mock_post:
            forwarder.forward(message)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["content"] == "Hello!"
        assert payload["username"].startswith("@testuser")

    def test_long_content_split_into_chunks(self, forwarder):
        long_msg = DiscordMessage("123", "user", "x" * 3000, "2024-01-01T00:00:00Z")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        with patch("discordless.webhook.requests.post", return_value=mock_resp) as mock_post:
            result = forwarder.forward(long_msg)
        assert result is True
        assert mock_post.call_count == 2  # 3000 chars → 2000 + 1000
        sent = [c.kwargs["json"]["content"] for c in mock_post.call_args_list]
        assert all(len(s) <= 2000 for s in sent)
        assert "".join(sent) == "x" * 3000
        assert forwarder.stats["sent"] == 2

    def test_retries_on_429_then_succeeds(self, forwarder, message):
        r429 = MagicMock(); r429.status_code = 429
        r429.json.return_value = {"retry_after": 0.01}
        r204 = MagicMock(); r204.status_code = 204
        with patch("discordless.webhook.time.sleep"), \
             patch("discordless.webhook.requests.post", side_effect=[r429, r204]) as mock_post:
            result = forwarder.forward(message)
        assert result is True
        assert mock_post.call_count == 2  # retried once after 429
        assert forwarder.stats == {"sent": 1, "errors": 0}

    def test_persistent_429_exhausts_retries_and_errors(self, forwarder, message):
        r429 = MagicMock(); r429.status_code = 429
        r429.json.return_value = {"retry_after": 0.01}
        with patch("discordless.webhook.time.sleep"), \
             patch("discordless.webhook.requests.post", return_value=r429) as mock_post:
            result = forwarder.forward(message)
        assert result is False
        assert mock_post.call_count == 5  # max_retries
        assert forwarder.stats["errors"] == 1


class TestSplitContent:
    def test_empty_returns_empty_list(self):
        assert split_content("") == []

    def test_short_returns_single_chunk(self):
        assert split_content("hello") == ["hello"]

    def test_exactly_at_limit_is_one_chunk(self):
        assert split_content("x" * 2000) == ["x" * 2000]

    def test_hard_cut_when_no_newline(self):
        assert split_content("x" * 3000) == ["x" * 2000, "x" * 1000]

    def test_prefers_newline_boundary(self):
        text = "a" * 1500 + "\n" + "b" * 1500
        assert split_content(text) == ["a" * 1500, "b" * 1500]

    def test_every_chunk_within_limit(self):
        chunks = split_content("x" * 9000)
        assert chunks and all(len(c) <= 2000 for c in chunks)
        assert "".join(chunks) == "x" * 9000
