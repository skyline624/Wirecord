"""
Discord Message Formatter
Handles formatted display of Discord messages in the console with optional ANSI colors.
"""

from datetime import datetime


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"


# Global setting for colors (can be toggled)
USE_COLORS = True


def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes if colors are enabled."""
    if USE_COLORS:
        return f"{color}{text}{Colors.RESET}"
    return text


def get_username(author_dict: dict) -> str:
    """Extract display name from author dictionary.
    
    Prioritizes global_name, falls back to username.
    """
    if not author_dict:
        return "Unknown"
    return author_dict.get("global_name") or author_dict.get("username") or "Unknown"


def format_timestamp() -> str:
    """Return current timestamp in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


def get_channel_name(channel_id: str) -> str:
    """Placeholder for channel name lookup.
    
    TODO: Implement actual channel name resolution.
    For now, returns the channel ID truncated.
    """
    if not channel_id:
        return "unknown-channel"
    return f"#{channel_id[-6:]}"


def get_guild_name(guild_id: str) -> str:
    """Placeholder for guild name lookup.
    
    TODO: Implement actual guild name resolution.
    For now, returns the guild ID truncated.
    """
    if not guild_id:
        return "DM"
    return f"Server-{guild_id[-6:]}"


class MessageFormatter:
    """Formatter for Discord gateway events.
    
    Provides static methods to format various Discord events into
    human-readable console output with optional ANSI colorization.
    """

    @staticmethod
    def format_message(data: dict) -> str:
        """Format a MESSAGE_CREATE event.
        
        Format: [HH:MM:SS] [SERVEUR #canal] @utilisateur: contenu
                [HH:MM:SS] [DM @utilisateur] contenu
        """
        timestamp = format_timestamp()
        author = get_username(data.get("author", {}))
        content = data.get("content", "")
        
        # Check if DM or guild message
        guild_id = data.get("guild_id")
        if guild_id:
            channel_name = get_channel_name(data.get("channel_id"))
            guild_name = get_guild_name(guild_id)
            location = f"[{guild_name} {channel_name}]"
        else:
            location = f"[DM @{author}]"
        
        timestamp_str = colorize(f"[{timestamp}]", Colors.GRAY)
        location_str = colorize(location, Colors.CYAN)
        author_str = colorize(f"@{author}", Colors.GREEN + Colors.BOLD)
        content_str = colorize(content, Colors.WHITE)
        
        if guild_id:
            return f"{timestamp_str} {location_str} {author_str}: {content_str}"
        else:
            return f"{timestamp_str} {location_str} {content_str}"

    @staticmethod
    def format_edit(data: dict) -> str:
        """Format a MESSAGE_UPDATE event.
        
        Format: [HH:MM:SS] [EDIT] @utilisateur: nouveau contenu
        """
        timestamp = format_timestamp()
        author = get_username(data.get("author", {}))
        content = data.get("content", "")
        
        timestamp_str = colorize(f"[{timestamp}]", Colors.GRAY)
        edit_label = colorize("[EDIT]", Colors.YELLOW + Colors.BOLD)
        author_str = colorize(f"@{author}", Colors.YELLOW)
        content_str = colorize(content, Colors.WHITE)
        
        return f"{timestamp_str} {edit_label} {author_str}: {content_str}"

    @staticmethod
    def format_delete(data: dict) -> str:
        """Format a MESSAGE_DELETE event.
        
        Format: [HH:MM:SS] [DELETE] @utilisateur: (ancien contenu si dispo)
        
        Note: MESSAGE_DELETE events typically only contain message_id,
        not the full message data. The previous content would need to be
        cached separately.
        """
        timestamp = format_timestamp()
        
        # Try to get author from cached data if available
        author = "Unknown"
        content = "(message deleted)"
        
        # If full message data is somehow available (rare for deletes)
        if "author" in data:
            author = get_username(data.get("author", {}))
            content = data.get("content", "(message deleted)")
        
        timestamp_str = colorize(f"[{timestamp}]", Colors.GRAY)
        delete_label = colorize("[DELETE]", Colors.RED + Colors.BOLD)
        author_str = colorize(f"@{author}", Colors.RED)
        content_str = colorize(content, Colors.GRAY)
        
        return f"{timestamp_str} {delete_label} {author_str}: {content_str}"

    @staticmethod
    def format_typing(data: dict) -> str:
        """Format a TYPING_START event.
        
        Format: [HH:MM:SS] [TYPING] @utilisateur dans #canal
        """
        timestamp = format_timestamp()
        
        # Typing events have member info with user nested
        member = data.get("member", {})
        user = member.get("user", data.get("user", {}))
        author = get_username(user)
        
        channel_id = data.get("channel_id", "")
        channel_name = get_channel_name(channel_id)
        
        timestamp_str = colorize(f"[{timestamp}]", Colors.GRAY)
        typing_label = colorize("[TYPING]", Colors.BLUE + Colors.BOLD)
        author_str = colorize(f"@{author}", Colors.BLUE)
        channel_str = colorize(f"dans {channel_name}", Colors.CYAN)
        
        return f"{timestamp_str} {typing_label} {author_str} {channel_str}"

    @staticmethod
    def format_join(data: dict) -> str:
        """Format a GUILD_MEMBER_ADD event.
        
        Format: [HH:MM:SS] [JOIN] @utilisateur a rejoint SERVEUR
        """
        timestamp = format_timestamp()
        
        # Member events have user nested
        user = data.get("user", {})
        author = get_username(user)
        
        guild_id = data.get("guild_id", "")
        guild_name = get_guild_name(guild_id)
        
        timestamp_str = colorize(f"[{timestamp}]", Colors.GRAY)
        join_label = colorize("[JOIN]", Colors.MAGENTA + Colors.BOLD)
        author_str = colorize(f"@{author}", Colors.MAGENTA)
        guild_str = colorize(guild_name, Colors.CYAN)
        
        return f"{timestamp_str} {join_label} {author_str} a rejoint {guild_str}"

    @staticmethod
    def disable_colors():
        """Disable ANSI color output globally."""
        global USE_COLORS
        USE_COLORS = False

    @staticmethod
    def enable_colors():
        """Enable ANSI color output globally."""
        global USE_COLORS
        USE_COLORS = True


# Convenience functions for direct import
def format_message(data: dict) -> str:
    """Shortcut to MessageFormatter.format_message."""
    return MessageFormatter.format_message(data)


def format_edit(data: dict) -> str:
    """Shortcut to MessageFormatter.format_edit."""
    return MessageFormatter.format_edit(data)


def format_delete(data: dict) -> str:
    """Shortcut to MessageFormatter.format_delete."""
    return MessageFormatter.format_delete(data)


def format_typing(data: dict) -> str:
    """Shortcut to MessageFormatter.format_typing."""
    return MessageFormatter.format_typing(data)


def format_join(data: dict) -> str:
    """Shortcut to MessageFormatter.format_join."""
    return MessageFormatter.format_join(data)
