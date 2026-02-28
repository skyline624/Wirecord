"""Tests pour la classe DiscordMessage.

Ce module contient les tests unitaires pour l'entité DiscordMessage
du domaine, couvrant la déduplication et le formatage des messages.
"""

import hashlib
from datetime import datetime
from pathlib import Path

import pytest

from discord_logger.domain.message import DiscordMessage


class TestDiscordMessage:
    """Tests pour la classe DiscordMessage."""

    def test_create_message_basic(self, temp_dir: str) -> None:
        """Test la création basique d'un DiscordMessage.
        
        Arrange: Créer un message avec les champs requis
        Act: Instancier DiscordMessage
        Assert: Les attributs correspondent aux valeurs fournies
        """
        # Arrange
        channel_id = "123456789"
        author = "testuser"
        content = "Hello, World!"
        timestamp = "2024-01-15T10:30:00.000Z"
        
        # Act
        message = DiscordMessage(
            channel_id=channel_id,
            author=author,
            content=content,
            timestamp=timestamp
        )
        
        # Assert
        assert message.channel_id == channel_id
        assert message.author == author
        assert message.content == content
        assert message.timestamp == timestamp

    def test_message_is_immutable(self) -> None:
        """Test que DiscordMessage est immuable (frozen dataclass).
        
        Arrange: Créer un message
        Act: Tenter de modifier un attribut
        Assert: Une exception FrozenInstanceError est levée
        """
        # Arrange
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act & Assert
        with pytest.raises(AttributeError):
            message.channel_id = "456"

    def test_dedup_key_generation(self) -> None:
        """Test la génération de la clé de déduplication.
        
        Arrange: Créer un message avec des données spécifiques
        Act: Accéder à la propriété dedup_key
        Assert: La clé contient le channel_id et un hash partiel
        """
        # Arrange
        channel_id = "987654321"
        author = "testauthor"
        content = "Test content"
        timestamp = "2024-01-15T10:30:00.000Z"
        expected_hash = hashlib.md5(
            f"{timestamp}:{author}:{content}".encode()
        ).hexdigest()[:16]
        
        message = DiscordMessage(
            channel_id=channel_id,
            author=author,
            content=content,
            timestamp=timestamp
        )
        
        # Act
        dedup_key = message.dedup_key
        
        # Assert
        assert dedup_key == f"{channel_id}:{expected_hash}"
        assert channel_id in dedup_key
        assert ":" in dedup_key

    def test_dedup_key_unique_per_content(self) -> None:
        """Test que différents contenus génèrent différentes clés.
        
        Arrange: Créer deux messages avec contenu différent
        Act: Comparer leurs clés de déduplication
        Assert: Les clés sont différentes
        """
        # Arrange
        msg1 = DiscordMessage(
            channel_id="123",
            author="user",
            content="First message",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        msg2 = DiscordMessage(
            channel_id="123",
            author="user",
            content="Second message",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        key1 = msg1.dedup_key
        key2 = msg2.dedup_key
        
        # Assert
        assert key1 != key2

    def test_dedup_key_same_for_identical_messages(self) -> None:
        """Test que messages identiques ont la même clé.
        
        Arrange: Créer deux messages identiques
        Act: Comparer leurs clés de déduplication
        Assert: Les clés sont identiques
        """
        # Arrange
        msg1 = DiscordMessage(
            channel_id="123",
            author="user",
            content="Same message",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        msg2 = DiscordMessage(
            channel_id="123",
            author="user",
            content="Same message",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        key1 = msg1.dedup_key
        key2 = msg2.dedup_key
        
        # Assert
        assert key1 == key2

    def test_to_log_line_with_iso_timestamp(self) -> None:
        """Test le formatage de ligne de log avec timestamp ISO.
        
        Arrange: Créer un message avec timestamp ISO
        Act: Appeler to_log_line()
        Assert: La ligne est formatée correctement
        """
        # Arrange
        message = DiscordMessage(
            channel_id="123456789012345678",
            author="testuser",
            content="Hello",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        log_line = message.to_log_line()
        
        # Assert
        assert "[2024-01-15 10:30:00]" in log_line
        assert "[#01234567]" in log_line  # Last 8 chars of channel_id
        assert "@testuser" in log_line
        assert "Hello" in log_line
        assert log_line.endswith("\n")

    def test_to_log_line_with_plain_timestamp(self) -> None:
        """Test le formatage avec timestamp non-ISO.
        
        Arrange: Créer un message avec timestamp simple
        Act: Appeler to_log_line()
        Assert: Le timestamp original est utilisé
        """
        # Arrange
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15 10:30:00"
        )
        
        # Act
        log_line = message.to_log_line()
        
        # Assert
        assert "[2024-01-15 10:30:00]" in log_line

    def test_to_log_line_channel_truncation(self) -> None:
        """Test que l'ID de canal est tronqué à 8 caractères.
        
        Arrange: Créer un message avec un long channel_id
        Act: Appeler to_log_line()
        Assert: Seuls les 8 derniers caractères apparaissent
        """
        # Arrange
        message = DiscordMessage(
            channel_id="987654321098765432",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        log_line = message.to_log_line()
        
        # Assert
        assert "[#09876543]" in log_line

    def test_to_log_line_short_channel_id(self) -> None:
        """Test avec un channel_id court.
        
        Arrange: Créer un message avec un court channel_id
        Act: Appeler to_log_line()
        Assert: Le channel_id complet apparaît
        """
        # Arrange
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        log_line = message.to_log_line()
        
        # Assert
        assert "[#123]" in log_line

    def test_message_with_special_characters(self) -> None:
        """Test les messages avec caractères spéciaux.
        
        Arrange: Créer un message avec caractères Unicode
        Act: Accéder aux attributs
        Assert: Les caractères sont préservés
        """
        # Arrange
        content = "Hello 🎉 Café ñoño « guillemets »"
        message = DiscordMessage(
            channel_id="123",
            author="tëstüser",
            content=content,
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Assert
        assert message.content == content
        assert "🎉" in message.to_log_line()

    def test_message_with_empty_content(self) -> None:
        """Test les messages avec contenu vide.
        
        Arrange: Créer un message avec contenu vide
        Act: Générer la clé et le log
        Assert: Fonctionne sans erreur
        """
        # Arrange
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act & Assert
        assert message.dedup_key is not None
        assert ":" in message.dedup_key
        assert "" in message.to_log_line()

    def test_message_with_multiline_content(self) -> None:
        """Test les messages avec contenu multiligne.
        
        Arrange: Créer un message avec retours à la ligne
        Act: Générer le log
        Assert: Les retours à la ligne sont préservés
        """
        # Arrange
        content = "Line 1\nLine 2\nLine 3"
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content=content,
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        log_line = message.to_log_line()
        
        # Assert
        assert "Line 1" in log_line
        assert "Line 2" in log_line
        assert "Line 3" in log_line

    def test_message_with_very_long_content(self) -> None:
        """Test les messages avec contenu très long.
        
        Arrange: Créer un message avec contenu de 1000 caractères
        Act: Générer le log
        Assert: Le contenu complet est préservé
        """
        # Arrange
        content = "A" * 1000
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content=content,
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        log_line = message.to_log_line()
        
        # Assert
        assert content in log_line
        assert len(log_line) > 1000

    def test_message_hashable(self) -> None:
        """Test que DiscordMessage peut être utilisé dans un set.
        
        Arrange: Créer plusieurs messages
        Act: Les ajouter à un set
        Assert: Fonctionne comme clé de set
        """
        # Arrange
        msg1 = DiscordMessage("123", "user1", "content1", "2024-01-15T10:30:00.000Z")
        msg2 = DiscordMessage("456", "user2", "content2", "2024-01-15T10:31:00.000Z")
        
        # Act
        message_set = {msg1, msg2}
        
        # Assert
        assert len(message_set) == 2
        assert msg1 in message_set

    def test_message_comparison(self) -> None:
        """Test la comparaison entre messages.
        
        Arrange: Créer deux messages identiques et un différent
        Act: Les comparer
        Assert: Messages identiques sont égaux
        """
        # Arrange
        msg1 = DiscordMessage("123", "user", "test", "2024-01-15T10:30:00.000Z")
        msg2 = DiscordMessage("123", "user", "test", "2024-01-15T10:30:00.000Z")
        msg3 = DiscordMessage("456", "user", "test", "2024-01-15T10:30:00.000Z")
        
        # Assert
        assert msg1 == msg2
        assert msg1 != msg3

    def test_message_repr(self) -> None:
        """Test la représentation string du message.
        
        Arrange: Créer un message
        Act: Obtenir sa représentation
        Assert: Contient les informations essentielles
        """
        # Arrange
        message = DiscordMessage(
            channel_id="123",
            author="testuser",
            content="Hello",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        repr_str = repr(message)
        
        # Assert
        assert "DiscordMessage" in repr_str
        assert "testuser" in repr_str


class TestDiscordMessageEdgeCases:
    """Tests pour les cas limites de DiscordMessage."""

    def test_empty_strings(self) -> None:
        """Test les chaînes vides.
        
        Arrange: Créer un message avec tous les champs vides
        Act: Accéder aux propriétés
        Assert: Pas d'erreur, valeurs vides préservées
        """
        # Arrange
        message = DiscordMessage(
            channel_id="",
            author="",
            content="",
            timestamp=""
        )
        
        # Assert
        assert message.channel_id == ""
        assert message.author == ""
        assert message.content == ""
        assert message.timestamp == ""
        assert message.dedup_key == ":d41d8cd98f1521e6"

    def test_unicode_edge_cases(self) -> None:
        """Test les cas limites Unicode.
        
        Arrange: Créer des messages avec caractères Unicode spéciaux
        Act: Générer les clés
        Assert: Les clés sont générées sans erreur
        """
        # Arrange
        special_chars = [
            "\x00",  # Null byte
            "\n\r\t",  # Whitespace control
            "🎉🎊🎁",  # Emojis
            "日本語テスト",  # Japonais
            "مرحبا",  # Arabe
        ]
        
        for content in special_chars:
            message = DiscordMessage(
                channel_id="123",
                author="user",
                content=content,
                timestamp="2024-01-15T10:30:00.000Z"
            )
            
            # Act & Assert
            assert message.dedup_key is not None
            assert ":" in message.dedup_key
