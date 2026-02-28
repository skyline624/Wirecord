"""Capture service for Discord gateway data.

This module provides the main orchestration service for processing
Discord gateway capture files and extracting messages.
"""
from typing import Any, Dict, Optional, Protocol

from discord_logger.domain.message import DiscordMessage


class PayloadParser(Protocol):
    """Protocol pour le parsing des payloads.
    
    Définit l'interface attendue pour tout parseur capable de
    lire et décoder des fichiers de capture.
    """
    
    def parse_file(self, filepath: str) -> list[Dict[str, Any]]:
        """Parse un fichier de capture.
        
        Args:
            filepath: Chemin vers le fichier à parser.
            
        Returns:
            Liste des payloads bruts extraits.
        """
        ...


class MessageLogger(Protocol):
    """Protocol pour l'écriture des messages.
    
    Définit l'interface attendue pour tout logger capable d'écrire
    des messages formatés.
    """
    
    def write(self, message: DiscordMessage) -> None:
        """Écrit un message dans le log.
        
        Args:
            message: Message Discord à écrire.
        """
        ...


class DedupChecker(Protocol):
    """Protocol pour la vérification de déduplication.
    
    Définit l'interface attendue pour tout service de déduplication.
    """
    
    def is_seen(self, message: DiscordMessage) -> bool:
        """Vérifie si un message a déjà été vu."""
        ...
    
    def mark_seen(self, message: DiscordMessage) -> None:
        """Marque un message comme vu."""
        ...


class Archiver(Protocol):
    """Protocol pour l'archivage des fichiers.
    
    Définit l'interface attendue pour tout archiver de fichiers.
    """
    
    def archive(self, filepath: str) -> None:
        """Archive un fichier traité.
        
        Args:
            filepath: Chemin vers le fichier à archiver.
        """
        ...


class CaptureService:
    """Service orchestration capture.
    
    Orchestrateur principal qui coordonne le parsing, la déduplication,
    et l'écriture des messages Discord depuis les fichiers de capture.
    
    Attributes:
        archiver: Service d'archivage des fichiers traités.
        parser: Parseur de payloads de capture.
        logger: Logger pour l'écriture des messages.
        dedup: Service de déduplication des messages.
    """
    
    def __init__(
        self,
        archiver: Archiver,
        parser: PayloadParser,
        logger: MessageLogger,
        dedup: DedupChecker
    ) -> None:
        """Initialise le service avec ses dépendances.
        
        Args:
            archiver: Service d'archivage des fichiers.
            parser: Parseur de payloads.
            logger: Logger pour les messages.
            dedup: Service de déduplication.
        """
        self.archiver = archiver
        self.parser = parser
        self.logger = logger
        self.dedup = dedup
    
    def process_gateway_file(self, filepath: str) -> int:
        """Traite un fichier gateway.
        
        Parse le fichier, extrait les messages, filtre les doublons,
        écrit les nouveaux messages et archive le fichier.
        
        Args:
            filepath: Chemin vers le fichier gateway à traiter.
            
        Returns:
            Nombre de nouveaux messages traités et écrits.
        """
        count = 0
        
        for raw_payload in self.parser.parse_file(filepath):
            message = self._extract_message(raw_payload)
            if message and not self.dedup.is_seen(message):
                self.dedup.mark_seen(message)
                self.logger.write(message)
                count += 1
        
        self.archiver.archive(filepath)
        return count
    
    def _extract_message(
        self,
        raw_payload: Dict[str, Any]
    ) -> Optional[DiscordMessage]:
        """Extrait un DiscordMessage d'un payload brut.
        
        Args:
            raw_payload: Dictionnaire contenant les données du message.
            
        Returns:
            DiscordMessage si les données sont valides, None sinon.
        """
        try:
            if not isinstance(raw_payload, dict):
                return None
            
            # Extraction des champs requis
            channel_id = raw_payload.get("channel_id")
            author_data = raw_payload.get("author", {})
            author = author_data.get("username") if isinstance(author_data, dict) else None
            content = raw_payload.get("content")
            timestamp = raw_payload.get("timestamp")
            
            # Validation des champs obligatoires
            if not all([channel_id, author, content is not None, timestamp]):
                return None
            
            return DiscordMessage(
                channel_id=str(channel_id),
                author=str(author),
                content=str(content),
                timestamp=str(timestamp)
            )
            
        except (KeyError, AttributeError, TypeError):
            return None
