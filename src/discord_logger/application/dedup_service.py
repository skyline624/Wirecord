"""Deduplication service for Discord messages.

This module provides services for tracking and deduplicating Discord messages
to prevent duplicate entries in the log output.
"""
from typing import Protocol, Set

from discord_logger.domain.message import DiscordMessage


class DedupStore(Protocol):
    """Protocol pour le stockage de déduplication.
    
    Définit l'interface attendue pour tout stockage capable de
    gérer les clés de déduplication.
    """
    
    def is_seen(self, key: str) -> bool:
        """Vérifie si une clé a déjà été vue.
        
        Args:
            key: Clé de déduplication à vérifier.
            
        Returns:
            True si la clé a déjà été vue, False sinon.
        """
        ...
    
    def mark_seen(self, key: str) -> None:
        """Marque une clé comme vue.
        
        Args:
            key: Clé de déduplication à marquer.
        """
        ...


class InMemoryDedupService:
    """Service de déduplication en mémoire.
    
    Implémentation simple stockant les clés de déduplication
    dans un ensemble Python en mémoire.
    
    Attributes:
        _seen_keys: Ensemble des clés déjà rencontrées.
    """
    
    def __init__(self) -> None:
        """Initialise le service avec un ensemble vide."""
        self._seen_keys: Set[str] = set()
    
    def is_seen(self, message: DiscordMessage) -> bool:
        """Vérifie si un message a déjà été vu.
        
        Args:
            message: Message Discord à vérifier.
            
        Returns:
            True si le message a déjà été vu, False sinon.
        """
        return message.dedup_key in self._seen_keys
    
    def mark_seen(self, message: DiscordMessage) -> None:
        """Marque un message comme vu.
        
        Args:
            message: Message Discord à marquer.
        """
        self._seen_keys.add(message.dedup_key)
    
    def clear(self) -> None:
        """Efface toutes les clés de déduplication."""
        self._seen_keys.clear()
    
    def __len__(self) -> int:
        """Retourne le nombre de clés stockées."""
        return len(self._seen_keys)
