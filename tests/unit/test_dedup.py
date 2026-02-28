"""Tests pour le service de déduplication.

Ce module contient les tests unitaires pour InMemoryDedupService
et les implémentations du protocole DedupStore.
"""

from typing import Set

import pytest

from discord_logger.domain.message import DiscordMessage
from discord_logger.application.dedup_service import InMemoryDedupService, DedupStore


class TestInMemoryDedupService:
    """Tests pour InMemoryDedupService."""

    def test_create_empty_service(self) -> None:
        """Test la création d'un service vide.
        
        Arrange: Créer un nouveau service
        Act: Vérifier l'état initial
        Assert: Le service est vide
        """
        # Act
        service = InMemoryDedupService()
        
        # Assert
        assert len(service) == 0
        assert isinstance(service._seen_keys, set)

    def test_mark_single_message(self) -> None:
        """Test le marquage d'un message unique.
        
        Arrange: Créer un service et un message
        Act: Marquer le message comme vu
        Assert: Le service contient la clé
        """
        # Arrange
        service = InMemoryDedupService()
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        service.mark_seen(message)
        
        # Assert
        assert len(service) == 1
        assert message.dedup_key in service._seen_keys

    def test_is_seen_true(self) -> None:
        """Test is_seen retourne True pour message déjà vu.
        
        Arrange: Créer un service, marquer un message
        Act: Vérifier si le message est vu
        Assert: Retourne True
        """
        # Arrange
        service = InMemoryDedupService()
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        service.mark_seen(message)
        
        # Act
        result = service.is_seen(message)
        
        # Assert
        assert result is True

    def test_is_seen_false(self) -> None:
        """Test is_seen retourne False pour message jamais vu.
        
        Arrange: Créer un service sans marquer de message
        Act: Vérifier un message inconnu
        Assert: Retourne False
        """
        # Arrange
        service = InMemoryDedupService()
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        result = service.is_seen(message)
        
        # Assert
        assert result is False

    def test_mark_seen_multiple_times(self) -> None:
        """Test que marquer plusieurs fois ne duplique pas.
        
        Arrange: Créer un service et un message
        Act: Marquer le message plusieurs fois
        Assert: Une seule clé dans le service
        """
        # Arrange
        service = InMemoryDedupService()
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        service.mark_seen(message)
        service.mark_seen(message)
        service.mark_seen(message)
        
        # Assert
        assert len(service) == 1

    def test_clear_service(self) -> None:
        """Test la méthode clear.
        
        Arrange: Créer un service avec des messages marqués
        Act: Appeler clear
        Assert: Le service est vide
        """
        # Arrange
        service = InMemoryDedupService()
        for i in range(5):
            message = DiscordMessage(
                channel_id=f"{i}",
                author="user",
                content=f"content{i}",
                timestamp="2024-01-15T10:30:00.000Z"
            )
            service.mark_seen(message)
        
        # Act
        service.clear()
        
        # Assert
        assert len(service) == 0

    def test_different_messages_different_keys(self) -> None:
        """Test que messages différents ont des clés différentes.
        
        Arrange: Créer plusieurs messages uniques
        Act: Les marquer tous
        Assert: Chaque message compte comme unique
        """
        # Arrange
        service = InMemoryDedupService()
        messages = [
            DiscordMessage(
                channel_id="123",
                author="user1",
                content="content1",
                timestamp="2024-01-15T10:30:00.000Z"
            ),
            DiscordMessage(
                channel_id="124",
                author="user2",
                content="content2",
                timestamp="2024-01-15T10:31:00.000Z"
            ),
            DiscordMessage(
                channel_id="125",
                author="user3",
                content="content3",
                timestamp="2024-01-15T10:32:00.000Z"
            ),
        ]
        
        # Act
        for msg in messages:
            service.mark_seen(msg)
        
        # Assert
        assert len(service) == 3

    def test_len_method(self) -> None:
        """Test la méthode __len__.
        
        Arrange: Créer un service avec plusieurs messages
        Act: Obtenir la longueur
        Assert: Correspond au nombre de messages
        """
        # Arrange
        service = InMemoryDedupService()
        
        # Act & Assert
        assert len(service) == 0
        
        service.mark_seen(DiscordMessage(
            channel_id="1",
            author="user",
            content="msg1",
            timestamp="2024-01-15T10:30:00.000Z"
        ))
        assert len(service) == 1
        
        service.mark_seen(DiscordMessage(
            channel_id="2",
            author="user",
            content="msg2",
            timestamp="2024-01-15T10:30:00.000Z"
        ))
        assert len(service) == 2

    def test_identical_messages_same_key(self) -> None:
        """Test que messages identiques partagent la même clé.
        
        Arrange: Créer deux messages identiques
        Act: Marquer le premier, vérifier le deuxième
        Assert: Le deuxième est considéré comme vu
        """
        # Arrange
        service = InMemoryDedupService()
        msg1 = DiscordMessage(
            channel_id="123",
            author="user",
            content="same content",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        msg2 = DiscordMessage(
            channel_id="123",
            author="user",
            content="same content",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        service.mark_seen(msg1)
        
        # Assert
        assert service.is_seen(msg2) is True
        assert len(service) == 1

    def test_large_number_of_messages(self) -> None:
        """Test avec un grand nombre de messages.
        
        Arrange: Créer beaucoup de messages uniques
        Act: Les marquer tous
        Assert: Toutes les clés sont stockées
        """
        # Arrange
        service = InMemoryDedupService()
        count = 1000
        
        # Act
        for i in range(count):
            message = DiscordMessage(
                channel_id=f"channel_{i % 10}",
                author=f"user_{i}",
                content=f"content_{i}",
                timestamp=f"2024-01-15T{i:02d}:30:00.000Z"
            )
            service.mark_seen(message)
        
        # Assert
        assert len(service) == count

    def test_message_with_same_content_different_channel(self) -> None:
        """Test messages même contenu mais canaux différents.
        
        Arrange: Créer messages identiques sur canaux différents
        Act: Les marquer
        Assert: Sont considérés comme différents
        """
        # Arrange
        service = InMemoryDedupService()
        msg1 = DiscordMessage(
            channel_id="channel_a",
            author="user",
            content="same",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        msg2 = DiscordMessage(
            channel_id="channel_b",
            author="user",
            content="same",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        service.mark_seen(msg1)
        
        # Assert
        assert service.is_seen(msg2) is False
        assert len(service) == 1

    def test_is_seen_with_none_message(self) -> None:
        """Test is_seen avec message None.
        
        Arrange: Créer un service
        Act: Appeler is_seen avec None
        Assert: Gère correctement l'erreur
        """
        # Arrange
        service = InMemoryDedupService()
        
        # Act & Assert - Devrait lever AttributeError car None n'a pas dedup_key
        with pytest.raises(AttributeError):
            service.is_seen(None)  # type: ignore

    def test_mark_seen_with_none_message(self) -> None:
        """Test mark_seen avec message None.
        
        Arrange: Créer un service
        Act: Appeler mark_seen avec None
        Assert: Gère correctement l'erreur
        """
        # Arrange
        service = InMemoryDedupService()
        
        # Act & Assert
        with pytest.raises(AttributeError):
            service.mark_seen(None)  # type: ignore


class TestInMemoryDedupServiceEdgeCases:
    """Tests pour les cas limites du service de déduplication."""

    def test_empty_strings_in_message(self) -> None:
        """Test messages avec champs vides.
        
        Arrange: Créer un message avec champs vides
        Act: Le marquer et vérifier
        Assert: Fonctionne correctement
        """
        # Arrange
        service = InMemoryDedupService()
        message = DiscordMessage(
            channel_id="",
            author="",
            content="",
            timestamp=""
        )
        
        # Act
        service.mark_seen(message)
        
        # Assert
        assert service.is_seen(message) is True
        assert len(service) == 1

    def test_very_long_content(self) -> None:
        """Test messages avec contenu très long.
        
        Arrange: Créer un message avec contenu de 10000 caractères
        Act: Le marquer
        Assert: La clé est générée (hash tronqué)
        """
        # Arrange
        service = InMemoryDedupService()
        content = "A" * 10000
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content=content,
            timestamp="2024-01-15T10:30:00.000Z"
        )
        
        # Act
        service.mark_seen(message)
        
        # Assert
        assert len(service) == 1
        assert len(message.dedup_key) == 20  # channel_id + ":" + 16 chars hash

    def test_unicode_in_dedup_key(self) -> None:
        """Test messages avec caractères Unicode.
        
        Arrange: Créer des messages avec contenu Unicode
        Act: Générer les clés de déduplication
        Assert: Les clés sont générées sans erreur
        """
        # Arrange
        service = InMemoryDedupService()
        contents = [
            "Hello 世界",
            "مرحبا",
            "🎉🎊",
            "café à l'été",
        ]
        
        # Act
        for content in contents:
            message = DiscordMessage(
                channel_id="123",
                author="user",
                content=content,
                timestamp="2024-01-15T10:30:00.000Z"
            )
            service.mark_seen(message)
        
        # Assert
        assert len(service) == 4

    def test_clear_empty_service(self) -> None:
        """Test clear sur service déjà vide.
        
        Arrange: Créer un service vide
        Act: Appeler clear
        Assert: Toujours vide
        """
        # Arrange
        service = InMemoryDedupService()
        
        # Act
        service.clear()
        
        # Assert
        assert len(service) == 0

    def test_multiple_clear_calls(self) -> None:
        """Test plusieurs appels à clear.
        
        Arrange: Créer un service avec des messages
        Act: Appeler clear plusieurs fois
        Assert: Toujours vide
        """
        # Arrange
        service = InMemoryDedupService()
        message = DiscordMessage(
            channel_id="123",
            author="user",
            content="test",
            timestamp="2024-01-15T10:30:00.000Z"
        )
        service.mark_seen(message)
        
        # Act
        service.clear()
        service.clear()
        service.clear()
        
        # Assert
        assert len(service) == 0
