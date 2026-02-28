"""
Addon mitmproxy pour capturer le trafic Discord Gateway.

Ce module fournit un addon mitmproxy qui intercepte les messages WebSocket
vers les gateways Discord et les archive pour analyse.
"""

import json
import os
from pathlib import Path
from typing import Optional, Set
from datetime import datetime

from mitmproxy import http, ctx


class DiscordArchiver:
    """Addon mitmproxy pour capturer le trafic Discord Gateway.
    
    Cette classe intercepte les messages WebSocket destinés aux gateways Discord
    et les archive dans des fichiers JSON structurés par gateway.
    
    Attributes:
        archive_path: Chemin du dossier d'archive des messages
        gatekeepers: Dictionnaire des gateways actifs avec leurs fichiers de log
        DISCORD_DOMAINS: Ensemble des domaines Discord à intercepter
    """
    
    DISCORD_DOMAINS: Set[str] = {
        "discord.com",
        "discord.gg",
        "discord.media",
        "discordapp.com",
        "discordapp.net",
        "discord.statuspage.io",
    }
    
    def __init__(self, archive_path: str = "traffic_archive") -> None:
        """Initialise l'archiver avec le chemin d'archive spécifié.
        
        Args:
            archive_path: Chemin du dossier où archiver les messages capturés
        """
        self.archive_path: Path = Path(archive_path)
        self.gatekeepers: dict[str, Path] = {}
        self._ensure_archive_dir()
    
    def _ensure_archive_dir(self) -> None:
        """Crée le répertoire d'archive s'il n'existe pas."""
        try:
            self.archive_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            ctx.log.error(f"Erreur création dossier archive {self.archive_path}: {e}")
            raise
    
    def url_is_gateway(self, url: str) -> bool:
        """Vérifie si l'URL est une gateway Discord.
        
        Args:
            url: L'URL à vérifier
            
        Returns:
            True si l'URL pointe vers une gateway Discord, False sinon
        """
        return "gateway" in url.lower() and any(
            domain in url.lower() for domain in self.DISCORD_DOMAINS
        )
    
    def _get_gateway_file(self, gateway_id: str) -> Path:
        """Obtient le chemin du fichier pour une gateway spécifique.
        
        Args:
            gateway_id: Identifiant unique de la gateway
            
        Returns:
            Chemin du fichier d'archive pour cette gateway
        """
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"gateway_{gateway_id}_{date_str}.jsonl"
        return self.archive_path / filename
    
    def _extract_gateway_id(self, url: str) -> str:
        """Extrait l'identifiant de gateway depuis l'URL.
        
        Args:
            url: L'URL de la requête
            
        Returns:
            Identifiant de la gateway (hostname normalisé)
        """
        from urllib.parse import urlparse
        parsed = urlparse(url)
        gateway_id = parsed.hostname or "unknown"
        # Nettoyer l'ID pour l'utilisation comme nom de fichier
        return gateway_id.replace(".", "_")
    
    def _archive_message(
        self, 
        gateway_id: str, 
        message_data: dict,
        direction: str = "unknown"
    ) -> None:
        """Archive un message dans le fichier approprié.
        
        Args:
            gateway_id: Identifiant de la gateway
            message_data: Données du message à archiver
            direction: Direction du message ('incoming' ou 'outgoing')
        """
        try:
            log_file = self._get_gateway_file(gateway_id)
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "gateway_id": gateway_id,
                "direction": direction,
                "data": message_data
            }
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
        except (OSError, json.JSONEncodeError) as e:
            ctx.log.error(f"Erreur archivage message {gateway_id}: {e}")
    
    def websocket_message(self, flow: http.HTTPFlow) -> None:
        """Callback appelé pour chaque message WebSocket.
        
        Capture les messages WebSocket vers les gateways Discord
        et les archive pour analyse ultérieure.
        
        Args:
            flow: Le flux HTTP contenant le message WebSocket
        """
        if not self.url_is_gateway(flow.request.pretty_url):
            return
        
        gateway_id = self._extract_gateway_id(flow.request.pretty_url)
        
        # Mettre à jour le suivi des gateways
        if gateway_id not in self.gatekeepers:
            self.gatekeepers[gateway_id] = self._get_gateway_file(gateway_id)
            ctx.log.info(f"Nouvelle gateway détectée: {gateway_id}")
        
        try:
            # Le message WebSocket est dans flow.websocket.messages
            if hasattr(flow, 'websocket') and flow.websocket:
                for msg in flow.websocket.messages:
                    if msg is None:
                        continue
                    
                    direction = "incoming" if msg.from_client else "outgoing"
                    
                    try:
                        # Essayer de parser comme JSON
                        content = msg.content.decode('utf-8', errors='replace')
                        data = json.loads(content)
                        self._archive_message(gateway_id, data, direction)
                    except json.JSONDecodeError:
                        # Si ce n'est pas du JSON, archiver tel quel
                        content = msg.content.decode('utf-8', errors='replace')
                        self._archive_message(
                            gateway_id, 
                            {"raw_content": content},
                            direction
                        )
                        
        except Exception as e:
            ctx.log.error(f"Erreur traitement WebSocket {gateway_id}: {e}")
    
    def websocket_start(self, flow: http.HTTPFlow) -> None:
        """Callback appelé au début d'une connexion WebSocket.
        
        Args:
            flow: Le flux HTTP de la connexion WebSocket
        """
        if self.url_is_gateway(flow.request.pretty_url):
            gateway_id = self._extract_gateway_id(flow.request.pretty_url)
            ctx.log.info(f"Connexion WebSocket établie: {gateway_id}")
    
    def websocket_end(self, flow: http.HTTPFlow) -> None:
        """Callback appelé à la fin d'une connexion WebSocket.
        
        Args:
            flow: Le flux HTTP de la connexion WebSocket
        """
        if self.url_is_gateway(flow.request.pretty_url):
            gateway_id = self._extract_gateway_id(flow.request.pretty_url)
            ctx.log.info(f"Connexion WebSocket terminée: {gateway_id}")


# Point d'entrée pour mitmproxy
addons = [DiscordArchiver()]
