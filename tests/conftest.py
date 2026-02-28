"""
Configuration pytest et fixtures pour le projet discordless.

Ce fichier contient les fixtures réutilisables pour tous les tests.
"""

import pytest
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

# Ajouter le répertoire parent au path pour les imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Fixtures de chemins et répertoires
# =============================================================================

@pytest.fixture
def project_root():
    """Retourne le répertoire racine du projet."""
    return PROJECT_ROOT


@pytest.fixture
def temp_dir():
    """Crée un répertoire temporaire pour les tests."""
    tmpdir = tempfile.mkdtemp(prefix="discordless_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def traffic_archive_dir(temp_dir):
    """Crée une structure traffic_archive simulée."""
    archive_dir = Path(temp_dir) / "traffic_archive"
    (archive_dir / "requests").mkdir(parents=True)
    (archive_dir / "gateways").mkdir(parents=True)
    return archive_dir


@pytest.fixture
def logs_dir(temp_dir):
    """Crée un répertoire de logs temporaire."""
    logs = Path(temp_dir) / "logs" / "messages"
    logs.mkdir(parents=True)
    return logs


# =============================================================================
# Fixtures de données de test
# =============================================================================

@pytest.fixture
def sample_message_data():
    """Données de message Discord standard."""
    return {
        "id": "1234567890123456789",
        "channel_id": "987654321098765432",
        "guild_id": "111111111111111111",
        "author": {
            "id": "222222222222222222",
            "username": "testuser",
            "global_name": "Test User",
            "discriminator": "1234"
        },
        "content": "Hello, World!",
        "timestamp": "2024-01-15T10:30:00.000Z",
        "edited_timestamp": None,
        "attachments": [],
        "embeds": [],
        "mentions": [],
        "mention_roles": [],
        "pinned": False,
        "type": 0
    }


@pytest.fixture
def sample_dm_message():
    """Message de conversation privée (sans guild_id)."""
    return {
        "id": "1234567890123456789",
        "channel_id": "987654321098765432",
        "author": {
            "id": "222222222222222222",
            "username": "dmuser",
            "global_name": "DM User",
            "discriminator": "5678"
        },
        "content": "Private message",
        "timestamp": "2024-01-15T10:30:00.000Z",
        "edited_timestamp": None,
        "attachments": [],
        "embeds": [],
        "mentions": []
    }


@pytest.fixture
def sample_message_update():
    """Événement MESSAGE_UPDATE."""
    return {
        "id": "1234567890123456789",
        "channel_id": "987654321098765432",
        "guild_id": "111111111111111111",
        "author": {
            "id": "222222222222222222",
            "username": "testuser",
            "global_name": "Test User"
        },
        "content": "Message modifié",
        "timestamp": "2024-01-15T10:30:00.000Z",
        "edited_timestamp": "2024-01-15T10:35:00.000Z"
    }


@pytest.fixture
def sample_message_delete():
    """Événement MESSAGE_DELETE."""
    return {
        "id": "1234567890123456789",
        "channel_id": "987654321098765432",
        "guild_id": "111111111111111111"
    }


@pytest.fixture
def sample_typing_event():
    """Événement TYPING_START."""
    return {
        "channel_id": "987654321098765432",
        "guild_id": "111111111111111111",
        "user_id": "222222222222222222",
        "timestamp": 1705315800,
        "member": {
            "user": {
                "id": "222222222222222222",
                "username": "typinguser",
                "global_name": "Typing User"
            },
            "nick": "Nickname"
        }
    }


@pytest.fixture
def sample_guild_member_add():
    """Événement GUILD_MEMBER_ADD."""
    return {
        "guild_id": "111111111111111111",
        "user": {
            "id": "333333333333333333",
            "username": "newmember",
            "global_name": "New Member"
        }
    }


@pytest.fixture
def sample_gateway_payload():
    """Payload Gateway Discord standard."""
    return {
        "t": "MESSAGE_CREATE",
        "s": 1,
        "op": 0,
        "d": {
            "id": "1234567890123456789",
            "channel_id": "987654321098765432",
            "author": {
                "id": "222222222222222222",
                "username": "testuser",
                "global_name": "Test User"
            },
            "content": "Test message"
        }
    }


@pytest.fixture
def sample_etf_data():
    """Données ETF (Erlang Term Format) encodées en binaire."""
    # Format ETF simple: 0x83 = version, suivi de données
    # C'est une simplification - les vraies données ETF sont plus complexes
    return b'\x83h\x03d\x00\x05hello'


@pytest.fixture
def sample_zlib_compressed():
    """Données compressées zlib pour les tests de décompression."""
    import zlib
    original = b'{"t":"MESSAGE_CREATE","d":{"id":"123","content":"test"}}'
    compressed = zlib.compress(original)
    return compressed


@pytest.fixture
def sample_zstd_compressed():
    """Données compressées zstd pour les tests (si pyzstd disponible)."""
    try:
        import pyzstd
        original = b'{"t":"MESSAGE_CREATE","d":{"id":"123","content":"test"}}'
        compressed = pyzstd.compress(original)
        return compressed
    except ImportError:
        return None


# =============================================================================
# Fixtures de mocks
# =============================================================================

@pytest.fixture
def mock_mitmproxy_context():
    """Mock du contexte mitmproxy pour les tests."""
    ctx = MagicMock()
    ctx.log = MagicMock()
    ctx.log.info = MagicMock()
    ctx.log.error = MagicMock()
    return ctx


@pytest.fixture
def mock_http_flow():
    """Mock d'un flux HTTP mitmproxy."""
    flow = MagicMock()
    flow.request = MagicMock()
    flow.request.pretty_url = "https://discord.com/api/v9/channels/123/messages"
    flow.request.method = "GET"
    flow.response = MagicMock()
    flow.response.content = b'{"id": "123", "content": "test"}'
    flow.response.timestamp_start = 1705315800.0
    return flow


@pytest.fixture
def mock_websocket_flow():
    """Mock d'un flux WebSocket mitmproxy."""
    flow = MagicMock()
    flow.request = MagicMock()
    flow.request.pretty_url = "wss://gateway.discord.gg/?v=10&encoding=json&compress=zlib-stream"
    message = MagicMock()
    message.content = b'test message content'
    message.timestamp = 1705315800.0
    message.from_client = False
    flow.websocket = MagicMock()
    flow.websocket.messages = [message]
    return flow


# =============================================================================
# Fixtures de configuration
# =============================================================================

@pytest.fixture
def mock_discord_config():
    """Configuration Discord pour les tests."""
    return {
        "api_version": 9,
        "encoding": "json",
        "compression": "zlib-stream",
        "gateway_url": "wss://gateway.discord.gg/?v=10&encoding=json&compress=zlib-stream"
    }


@pytest.fixture
def target_channels():
    """Liste de canaux cibles pour les tests."""
    return {"987654321098765432", "555555555555555555"}


# =============================================================================
# Fixtures de fichiers de test
# =============================================================================

@pytest.fixture
def create_request_index(traffic_archive_dir):
    """Crée un fichier request_index de test."""
    index_path = traffic_archive_dir / "request_index"
    with open(index_path, 'w') as f:
        f.write("1705315800.0 GET https://discord.com/api/v9/channels/123/messages hash123 0_channels_123_messages\n")
        f.write("1705315900.0 GET https://discord.com/api/v9/guilds/456/profile hash456 0_guilds_456_profile\n")
    return index_path


@pytest.fixture
def create_gateway_index(traffic_archive_dir):
    """Crée un fichier gateway_index de test."""
    index_path = traffic_archive_dir / "gateway_index"
    with open(index_path, 'w') as f:
        f.write("1705315800.0 wss://gateway.discord.gg/?v=10&encoding=json&compress=zlib-stream 0\n")
    return index_path


@pytest.fixture
def create_test_log_file(logs_dir):
    """Crée un fichier de log de test."""
    log_path = logs_dir / "test_messages.log"
    with open(log_path, 'w') as f:
        f.write("[2024-01-15 10:30:00] [#87654321] @testuser: Test message\n")
    return log_path
