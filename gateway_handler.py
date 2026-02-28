import zlib
import pyzstd
import json
import erlpack
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any


def deserialize_erlpackage(data: bytes) -> Dict[str, Any]:
    """
    Convertit les données ETF (Erlang Term Format) en dictionnaire Python.
    
    Args:
        data: Données binaires au format ETF
        
    Returns:
        Dictionnaire Python représentant les données décodées
    """
    return erlpack.unpack(data)


class GatewayHandler:
    """
    Gestionnaire de décompression des messages Gateway Discord en temps réel.
    
    Supporte les compressions zlib-stream et zstd-stream,
    ainsi que les encodages json et etf.
    """
    
    def __init__(self, url: str):
        """
        Initialise le handler avec une URL Gateway.
        
        Args:
            url: URL WebSocket du Gateway Discord avec paramètres
                 (ex: wss://gateway.discord.gg/?v=10&encoding=json&compress=zlib-stream)
        """
        self.url = url
        self._buffer = b""
        self._decompressor = None
        self._encoding = "json"
        self._compression = None
        
        self._parse_url_params()
        self._init_decompressor()
    
    def _parse_url_params(self) -> None:
        """
        Extrait les paramètres d'encodage et de compression depuis l'URL.
        """
        parsed = urlparse(self.url)
        params = parse_qs(parsed.query)
        
        # Extraction de l'encodage (json ou etf)
        if "encoding" in params:
            self._encoding = params["encoding"][0].lower()
        
        # Extraction de la compression (zlib-stream ou zstd-stream)
        if "compress" in params:
            self._compression = params["compress"][0].lower()
    
    def _init_decompressor(self) -> None:
        """
        Initialise le décompresseur approprié selon le type de compression.
        """
        if self._compression == "zlib-stream":
            # Création d'un objet de décompression zlib
            self._decompressor = zlib.decompressobj()
        elif self._compression == "zstd-stream":
            # Création d'un objet de décompression zstd
            self._decompressor = pyzstd.ZstdDecompressor()
        else:
            self._decompressor = None
    
    def feed_chunk(self, chunk: bytes) -> Optional[Dict[str, Any]]:
        """
        Ajoute un chunk au buffer et tente de récupérer un message complet.
        
        Args:
            chunk: Données binaires reçues du WebSocket
            
        Returns:
            Dictionnaire JSON du message décodé, ou None si le message est incomplet
        """
        if not chunk:
            return None
        
        # Si pas de compression, traitement direct
        if self._compression is None:
            return self._decode_message(chunk)
        
        # Ajout au buffer
        self._buffer += chunk
        
        # Vérification si message complet selon le type de compression
        if self._compression == "zlib-stream":
            # Un message zlib complet se termine par b'\x00\x00\xff\xff'
            if not self._buffer.endswith(b'\x00\x00\xff\xff'):
                return None
            
            try:
                decompressed = self._decompressor.decompress(self._buffer)
                self._buffer = b""
                return self._decode_message(decompressed)
            except zlib.error:
                # Erreur de décompression, on vide le buffer
                self._buffer = b""
                return None
        
        elif self._compression == "zstd-stream":
            # Pour zstd, on tente de décompresser
            try:
                decompressed = self._decompressor.decompress(self._buffer)
                self._buffer = b""
                return self._decode_message(decompressed)
            except (pyzstd.ZstdError, Exception):
                # Message incomplet ou erreur, on garde le buffer
                # Note: pyzstd peut lever une exception si les données sont incomplètes
                return None
        
        return None
    
    def _decode_message(self, data: bytes) -> Optional[Dict[str, Any]]:
        """
        Décode les données selon l'encodage configuré.
        
        Args:
            data: Données binaires à décoder
            
        Returns:
            Dictionnaire Python ou None en cas d'erreur
        """
        if not data:
            return None
        
        try:
            if self._encoding == "json":
                return json.loads(data.decode('utf-8'))
            elif self._encoding == "etf":
                return deserialize_erlpackage(data)
            else:
                # Fallback sur JSON si encodage inconnu
                return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError, Exception):
            return None
    
    def reset(self) -> None:
        """
        Réinitialise le buffer et le décompresseur.
        Utile en cas de reconnexion.
        """
        self._buffer = b""
        self._init_decompressor()
    
    def get_encoding(self) -> str:
        """Retourne l'encodage utilisé."""
        return self._encoding
    
    def get_compression(self) -> Optional[str]:
        """Retourne le type de compression utilisé."""
        return self._compression
