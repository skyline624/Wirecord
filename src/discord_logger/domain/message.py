"""Domain entity for Discord messages.

This module defines the core business entity representing a Discord message
with deduplication capabilities and log formatting.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib


@dataclass(frozen=True)
class DiscordMessage:
    """Entité métier message Discord.
    
    Cette entité immuable représente un message Discord avec ses attributs
    essentiels et fournit des méthodes pour la déduplication et le formatage.
    
    Attributes:
        channel_id: Identifiant unique du canal Discord.
        author: Nom d'utilisateur de l'auteur du message.
        content: Contenu textuel du message.
        timestamp: Horodatage ISO du message.
    """
    channel_id: str
    author: str
    content: str
    timestamp: str
    
    @property
    def dedup_key(self) -> str:
        """Clé unique pour déduplication.
        
        Génère une clé de déduplication basée sur un hash MD5 partiel
        du contenu, de l'auteur et du timestamp, combiné avec l'ID du canal.
        
        Returns:
            Chaîne unique identifiant ce message pour la déduplication.
        """
        content_hash = hashlib.md5(
            f"{self.timestamp}:{self.author}:{self.content}".encode()
        ).hexdigest()[:16]
        return f"{self.channel_id}:{content_hash}"
    
    def to_log_line(self) -> str:
        """Format ligne de log.
        
        Convertit le message en une ligne de log formatée avec horodatage,
        identifiant de canal raccourci, auteur et contenu.
        
        Returns:
            Ligne de log formatée prête pour l'écriture.
        """
        try:
            dt = datetime.fromisoformat(
                self.timestamp.replace('Z', '+00:00')
            )
            formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            formatted = self.timestamp
        
        channel_short = (
            self.channel_id[-8:] 
            if len(self.channel_id) > 8 
            else self.channel_id
        )
        return (
            f"[{formatted}] [#{channel_short}] "
            f"@{self.author}: {self.content}\n"
        )
