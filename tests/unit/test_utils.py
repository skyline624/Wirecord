"""
Tests unitaires pour utils.py - Fonctions utilitaires partagées.
"""

import pytest
from utils import (
    url_has_discord_root_domain,
    url_is_gateway,
    safe_filename,
    log_info,
    log_error,
    EventTypes
)


@pytest.mark.unit
class TestUrlHasDiscordRootDomain:
    """Tests pour url_has_discord_root_domain."""
    
    @pytest.mark.parametrize("url,expected", [
        ("https://discord.com/api/v9", True),
        ("https://discordapp.com/api/v9", True),
        ("https://gateway.discord.gg/?v=10", True),
        ("https://cdn.discordapp.com/attachments/", True),
        ("https://media.discordapp.net/", True),
        ("https://discord.gg/invite", True),
        ("https://dis.gd/short", True),
        ("https://discord.co/api", True),
        ("https://discordstatus.com/", True),
        ("https://bigbeans.solutions/", True),
        ("https://watchanimeattheoffice.com/", True),
        ("https://example.com/", False),
        ("https://google.com/", False),
        ("https://fake-discord.com/", False),
        ("https://discord.fake.com/", False),
        ("", False),
        ("invalid-url", False),
        ("ftp://discord.com/file", True),
    ])
    def test_url_detection(self, url, expected):
        """Test la détection des domaines Discord."""
        assert url_has_discord_root_domain(url) == expected
    
    def test_subdomain_detection(self):
        """Test la détection des sous-domaines."""
        assert url_has_discord_root_domain("https://api.discord.com/") is True
        assert url_has_discord_root_domain("https://status.discord.com/") is True
        assert url_has_discord_root_domain("https://deep.sub.domain.discord.com/") is True
    
    def test_edge_cases(self):
        """Test des cas limites."""
        assert url_has_discord_root_domain(None) is False


@pytest.mark.unit
class TestUrlIsGateway:
    """Tests pour url_is_gateway."""
    
    def test_gateway_url_detection(self):
        """Test la détection des URLs Gateway."""
        assert url_is_gateway("wss://gateway.discord.gg/?v=10") is True
        assert url_is_gateway("https://gateway.discord.com/") is True
    
    def test_non_gateway_url(self):
        """Test les URLs non-Gateway."""
        assert url_is_gateway("https://discord.com/api/v9") is False
        assert url_is_gateway("https://gateway.example.com/") is False


@pytest.mark.unit
class TestSafeFilename:
    """Tests pour safe_filename."""
    
    def test_basic_filename(self):
        """Test un nom de fichier basique."""
        assert safe_filename("test.txt") == "test.txt"
    
    def test_special_characters(self):
        """Test le nettoyage des caractères spéciaux."""
        assert safe_filename("file<name>.txt") == "file_name_.txt"
        assert safe_filename('file:name".txt') == "file_name_.txt"
        assert safe_filename("file/name\\|.txt") == "file_name_.txt"
        assert safe_filename("file?name*.txt") == "file_name_.txt"
    
    def test_control_characters(self):
        """Test le nettoyage des caractères de contrôle."""
        assert safe_filename("file\x00name.txt") == "file_name.txt"
        assert safe_filename("file\x1fname.txt") == "file_name.txt"
    
    def test_trailing_spaces_dots(self):
        """Test la suppression des espaces et points en fin."""
        assert safe_filename("file.txt ") == "file.txt"
        assert safe_filename("file.txt.") == "file.txt"
    
    def test_empty_filename(self):
        """Test un nom de fichier vide."""
        assert safe_filename("") == "unnamed"
    
    def test_only_special_chars(self):
        """Test un nom composé uniquement de caractères spéciaux."""
        assert safe_filename("<>:\"/\\|?*") == "unnamed"
    
    def test_long_filename(self):
        """Test la limitation de la longueur."""
        long_name = "a" * 300 + ".txt"
        result = safe_filename(long_name)
        assert len(result) <= 255


@pytest.mark.unit
class TestEventTypes:
    """Tests pour les constantes EventTypes."""
    
    def test_message_events(self):
        """Test les constantes d'événements message."""
        assert EventTypes.MESSAGE_CREATE == "MESSAGE_CREATE"
        assert EventTypes.MESSAGE_UPDATE == "MESSAGE_UPDATE"
        assert EventTypes.MESSAGE_DELETE == "MESSAGE_DELETE"
    
    def test_guild_events(self):
        """Test les constantes d'événements guild."""
        assert EventTypes.GUILD_CREATE == "GUILD_CREATE"
        assert EventTypes.GUILD_UPDATE == "GUILD_UPDATE"
        assert EventTypes.GUILD_DELETE == "GUILD_DELETE"
    
    def test_member_events(self):
        """Test les constantes d'événements membre."""
        assert EventTypes.GUILD_MEMBER_ADD == "GUILD_MEMBER_ADD"
        assert EventTypes.GUILD_MEMBER_REMOVE == "GUILD_MEMBER_REMOVE"
        assert EventTypes.GUILD_MEMBER_UPDATE == "GUILD_MEMBER_UPDATE"
    
    def test_reaction_events(self):
        """Test les constantes d'événements réaction."""
        assert EventTypes.MESSAGE_REACTION_ADD == "MESSAGE_REACTION_ADD"
        assert EventTypes.MESSAGE_REACTION_REMOVE == "MESSAGE_REACTION_REMOVE"


@pytest.mark.unit
class TestLoggingFunctions:
    """Tests pour les fonctions de logging."""
    
    def test_log_info(self, mock_mitmproxy_context):
        """Test log_info avec le mock."""
        log_info(mock_mitmproxy_context, "test message")
        mock_mitmproxy_context.log.info.assert_called_once()
        call_args = mock_mitmproxy_context.log.info.call_args[0][0]
        assert "[discordless]" in call_args
        assert "test message" in call_args
    
    def test_log_error(self, mock_mitmproxy_context):
        """Test log_error avec le mock."""
        log_error(mock_mitmproxy_context, "error message")
        mock_mitmproxy_context.log.error.assert_called_once()
        call_args = mock_mitmproxy_context.log.error.call_args[0][0]
        assert "[discordless]" in call_args
        assert "error message" in call_args
