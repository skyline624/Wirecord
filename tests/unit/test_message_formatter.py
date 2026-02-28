"""
Tests unitaires pour message_formatter.py - Formatage des messages Discord.
"""

import pytest
import re
from datetime import datetime
from message_formatter import (
    Colors,
    colorize,
    get_username,
    format_timestamp,
    get_channel_name,
    get_guild_name,
    MessageFormatter,
    format_message,
    format_edit,
    format_delete,
    format_typing,
    format_join,
    USE_COLORS
)


@pytest.mark.unit
class TestColors:
    """Tests pour les codes couleur ANSI."""
    
    def test_color_codes_exist(self):
        """Test que les codes couleur existent."""
        assert Colors.RESET == "\033[0m"
        assert Colors.GREEN == "\033[32m"
        assert Colors.RED == "\033[31m"
        assert Colors.BLUE == "\033[34m"
        assert Colors.YELLOW == "\033[33m"
        assert Colors.CYAN == "\033[36m"
        assert Colors.MAGENTA == "\033[35m"
        assert Colors.GRAY == "\033[90m"
        assert Colors.BOLD == "\033[1m"


@pytest.mark.unit
class TestColorize:
    """Tests pour la fonction colorize."""
    
    def test_colorize_with_colors_enabled(self, monkeypatch):
        """Test colorize avec couleurs activées."""
        monkeypatch.setattr('message_formatter.USE_COLORS', True)
        result = colorize("test", Colors.GREEN)
        assert Colors.GREEN in result
        assert Colors.RESET in result
        assert "test" in result
    
    def test_colorize_with_colors_disabled(self, monkeypatch):
        """Test colorize avec couleurs désactivées."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = colorize("test", Colors.GREEN)
        assert result == "test"
        assert Colors.GREEN not in result


@pytest.mark.unit
class TestGetUsername:
    """Tests pour get_username."""
    
    def test_global_name_priority(self):
        """Test que global_name est prioritaire sur username."""
        author = {"global_name": "Display Name", "username": "username"}
        assert get_username(author) == "Display Name"
    
    def test_username_fallback(self):
        """Test le fallback sur username."""
        author = {"username": "testuser"}
        assert get_username(author) == "testuser"
    
    def test_none_global_name(self):
        """Test quand global_name est None."""
        author = {"global_name": None, "username": "testuser"}
        assert get_username(author) == "testuser"
    
    def test_empty_author(self):
        """Test avec author vide."""
        assert get_username({}) == "Unknown"
    
    def test_none_author(self):
        """Test avec author None."""
        assert get_username(None) == "Unknown"
    
    def test_no_username_fields(self):
        """Test sans champs username."""
        author = {"id": "123", "avatar": "abc"}
        assert get_username(author) == "Unknown"


@pytest.mark.unit
class TestFormatTimestamp:
    """Tests pour format_timestamp."""
    
    def test_timestamp_format(self):
        """Test le format du timestamp."""
        result = format_timestamp()
        # Format attendu: HH:MM:SS
        assert re.match(r'^\d{2}:\d{2}:\d{2}$', result)
    
    def test_timestamp_current_time(self):
        """Test que le timestamp est l'heure actuelle."""
        before = datetime.now()
        result = format_timestamp()
        after = datetime.now()
        
        result_time = datetime.strptime(result, "%H:%M:%S")
        assert before.hour <= result_time.hour <= after.hour


@pytest.mark.unit
class TestGetChannelName:
    """Tests pour get_channel_name."""
    
    def test_valid_channel_id(self):
        """Test avec un channel_id valide."""
        result = get_channel_name("123456789012345678")
        assert result.startswith("#")
        assert "345678" in result
    
    def test_empty_channel_id(self):
        """Test avec channel_id vide."""
        assert get_channel_name("") == "unknown-channel"
    
    def test_none_channel_id(self):
        """Test avec channel_id None."""
        assert get_channel_name(None) == "unknown-channel"


@pytest.mark.unit
class TestGetGuildName:
    """Tests pour get_guild_name."""
    
    def test_valid_guild_id(self):
        """Test avec un guild_id valide."""
        result = get_guild_name("123456789012345678")
        assert result.startswith("Server-")
        assert "345678" in result
    
    def test_empty_guild_id(self):
        """Test avec guild_id vide (DM)."""
        assert get_guild_name("") == "DM"
    
    def test_none_guild_id(self):
        """Test avec guild_id None (DM)."""
        assert get_guild_name(None) == "DM"


@pytest.mark.unit
class TestMessageFormatter:
    """Tests pour MessageFormatter."""
    
    def test_format_guild_message(self, sample_message_data, monkeypatch):
        """Test le formatage d'un message de serveur."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_message(sample_message_data)
        assert "[" in result and "]" in result
        assert "@" in result
        assert "Test User" in result
        assert "Hello, World!" in result
    
    def test_format_dm_message(self, sample_dm_message, monkeypatch):
        """Test le formatage d'un message privé."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_message(sample_dm_message)
        assert "[DM" in result
        assert "DM User" in result
        assert "Private message" in result
    
    def test_format_edit(self, sample_message_update, monkeypatch):
        """Test le formatage d'une édition."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_edit(sample_message_update)
        assert "[EDIT]" in result
        assert "Test User" in result
        assert "Message modifié" in result
    
    def test_format_delete_full_data(self, sample_message_data, monkeypatch):
        """Test le formatage d'une suppression avec données complètes."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_delete(sample_message_data)
        assert "[DELETE]" in result
        assert "Test User" in result
    
    def test_format_delete_partial(self, sample_message_delete, monkeypatch):
        """Test le formatage d'une suppression partielle."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_delete(sample_message_delete)
        assert "[DELETE]" in result
        assert "Unknown" in result
    
    def test_format_typing(self, sample_typing_event, monkeypatch):
        """Test le formatage d'un événement typing."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_typing(sample_typing_event)
        assert "[TYPING]" in result
        assert "Typing User" in result
        assert "dans" in result
    
    def test_format_typing_no_member(self, monkeypatch):
        """Test le formatage sans member info."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        data = {
            "channel_id": "123",
            "user": {"username": "testuser", "global_name": "Test User"}
        }
        result = MessageFormatter.format_typing(data)
        assert "Test User" in result
    
    def test_format_join(self, sample_guild_member_add, monkeypatch):
        """Test le formatage d'un événement join."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = MessageFormatter.format_join(sample_guild_member_add)
        assert "[JOIN]" in result
        assert "New Member" in result
        assert "a rejoint" in result
    
    def test_disable_colors(self, monkeypatch):
        """Test la désactivation des couleurs."""
        MessageFormatter.disable_colors()
        assert USE_COLORS is False
    
    def test_enable_colors(self, monkeypatch):
        """Test l'activation des couleurs."""
        MessageFormatter.enable_colors()
        assert USE_COLORS is True


@pytest.mark.unit
class TestConvenienceFunctions:
    """Tests pour les fonctions de convenance."""
    
    def test_format_message_function(self, sample_message_data, monkeypatch):
        """Test la fonction format_message directe."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = format_message(sample_message_data)
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_format_edit_function(self, sample_message_update, monkeypatch):
        """Test la fonction format_edit directe."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = format_edit(sample_message_update)
        assert "[EDIT]" in result
    
    def test_format_delete_function(self, sample_message_data, monkeypatch):
        """Test la fonction format_delete directe."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = format_delete(sample_message_data)
        assert "[DELETE]" in result
    
    def test_format_typing_function(self, sample_typing_event, monkeypatch):
        """Test la fonction format_typing directe."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = format_typing(sample_typing_event)
        assert "[TYPING]" in result
    
    def test_format_join_function(self, sample_guild_member_add, monkeypatch):
        """Test la fonction format_join directe."""
        monkeypatch.setattr('message_formatter.USE_COLORS', False)
        result = format_join(sample_guild_member_add)
        assert "[JOIN]" in result
