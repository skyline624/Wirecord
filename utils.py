"""
Utilitaires partagés pour le projet discordless.

Ce module contient les constantes, fonctions utilitaires et classes
partagées par les autres modules du projet.
"""

from urllib.parse import urlparse
import re

# =============================================================================
# Constantes
# =============================================================================

DISCORD_DOMAINS = {
    "discord.com",
    "discordapp.com",
    "discord.net",
    "discordapp.net",
    "discord.gg",
    "dis.gd",
    "discord.co",
    "discord.app",
    "discord.dev",
    "discord.new",
    "discord.gift",
    "discord.gifts",
    "discord.media",
    "discord.store",
    "discordstatus.com",
    "bigbeans.solutions",
    "watchanimeattheoffice.com"
}


# =============================================================================
# Classes
# =============================================================================

class EventTypes:
    """
    Constantes pour les types d'événements Discord Gateway.
    """
    MESSAGE_CREATE = "MESSAGE_CREATE"
    MESSAGE_UPDATE = "MESSAGE_UPDATE"
    MESSAGE_DELETE = "MESSAGE_DELETE"
    TYPING_START = "TYPING_START"
    GUILD_MEMBER_ADD = "GUILD_MEMBER_ADD"
    GUILD_MEMBER_REMOVE = "GUILD_MEMBER_REMOVE"
    GUILD_MEMBER_UPDATE = "GUILD_MEMBER_UPDATE"
    GUILD_CREATE = "GUILD_CREATE"
    GUILD_UPDATE = "GUILD_UPDATE"
    GUILD_DELETE = "GUILD_DELETE"
    CHANNEL_CREATE = "CHANNEL_CREATE"
    CHANNEL_UPDATE = "CHANNEL_UPDATE"
    CHANNEL_DELETE = "CHANNEL_DELETE"
    MESSAGE_REACTION_ADD = "MESSAGE_REACTION_ADD"
    MESSAGE_REACTION_REMOVE = "MESSAGE_REACTION_REMOVE"
    PRESENCE_UPDATE = "PRESENCE_UPDATE"
    VOICE_STATE_UPDATE = "VOICE_STATE_UPDATE"
    READY = "READY"
    RESUMED = "RESUMED"


# =============================================================================
# Fonctions utilitaires
# =============================================================================

def url_has_discord_root_domain(url: str) -> bool:
    """
    Vérifie si une URL appartient à un domaine Discord.

    Args:
        url: L'URL à vérifier.

    Returns:
        True si l'URL appartient à un domaine Discord, False sinon.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        
        # Vérifier le domaine exact ou les sous-domaines
        for domain in DISCORD_DOMAINS:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
        return False
    except Exception:
        return False


def url_is_gateway(url: str) -> bool:
    """
    Vérifie si une URL est une URL Gateway Discord.

    Args:
        url: L'URL à vérifier.

    Returns:
        True si l'URL contient 'gateway', False sinon.
    """
    return "gateway" in url.lower()


def log_info(ctx, message: str) -> None:
    """
    Wrapper pour ctx.log.info avec préfixe.

    Args:
        ctx: Le contexte mitmproxy contenant le logger.
        message: Le message à logger.
    """
    ctx.log.info(f"[discordless] {message}")


def log_error(ctx, message: str) -> None:
    """
    Wrapper pour ctx.log.error avec préfixe.

    Args:
        ctx: Le contexte mitmproxy contenant le logger.
        message: Le message à logger.
    """
    ctx.log.error(f"[discordless] {message}")


def safe_filename(filename: str) -> str:
    """
    Nettoie un nom de fichier en remplaçant les caractères problématiques.

    Remplace les caractères spéciaux et réservés par des underscores
    pour garantir la compatibilité avec les systèmes de fichiers.

    Args:
        filename: Le nom de fichier original.

    Returns:
        Un nom de fichier sécurisé pour le stockage.
    """
    # Caractères interdits sur Windows: < > : " / \ | ? *
    # Caractères de contrôle: 0x00-0x1f
    # Espaces et points à la fin (Windows)
    
    if not filename:
        return "unnamed"
    
    # Remplacer les caractères interdits
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # Supprimer les espaces et points en fin de nom (Windows)
    safe = safe.rstrip(' .')
    
    # Limiter la longueur (255 caractères max pour la plupart des FS)
    if len(safe) > 255:
        name, ext = safe[:255].rsplit('.', 1) if '.' in safe else (safe[:255], '')
        if ext:
            safe = f"{name[:255-len(ext)-1]}.{ext}"
        else:
            safe = name[:255]
    
    # Si le nom est vide après nettoyage
    if not safe:
        safe = "unnamed"
    
    return safe
