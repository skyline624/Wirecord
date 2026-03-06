"""Tests for discordless.models."""
import pytest

from discordless.models import DiscordMessage


class TestDiscordMessage:
    def test_dedup_key_stable(self, sample_message):
        assert sample_message.dedup_key == sample_message.dedup_key

    def test_dedup_key_differs_for_different_content(self):
        a = DiscordMessage("123", "user", "hello", "2024-01-01T00:00:00Z")
        b = DiscordMessage("123", "user", "world", "2024-01-01T00:00:00Z")
        assert a.dedup_key != b.dedup_key

    def test_dedup_key_differs_for_different_channels(self):
        a = DiscordMessage("111", "user", "hello", "2024-01-01T00:00:00Z")
        b = DiscordMessage("222", "user", "hello", "2024-01-01T00:00:00Z")
        assert a.dedup_key != b.dedup_key

    def test_to_log_line_contains_author_and_content(self, sample_message):
        line = sample_message.to_log_line()
        assert "@testuser" in line
        assert "Hello, World!" in line

    def test_to_log_line_formats_iso_timestamp(self, sample_message):
        line = sample_message.to_log_line()
        assert "2024-01-15 10:30:00" in line

    def test_to_log_line_shows_last_8_chars_of_channel(self, sample_message):
        line = sample_message.to_log_line()
        assert "#11111111" in line

    def test_to_log_line_fallback_for_bad_timestamp(self):
        msg = DiscordMessage("123", "user", "hi", "not-a-date")
        line = msg.to_log_line()
        assert "not-a-date" in line

    def test_immutable(self, sample_message):
        with pytest.raises(Exception):
            sample_message.content = "modified"
