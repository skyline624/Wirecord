"""Module de chargement configuration JSON."""
import json
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class ForwarderConfig:
    """Configuration du forwarder webhook."""
    webhook_url: str
    source_channels: List[str]
    message_format: str = "embed"
    rate_limit_delay: float = 0.5
    enabled: bool = False

def load_forwarder_config(config_path: str = "config/forwarder.json") -> Optional[ForwarderConfig]:
    """Charge la configuration depuis fichier JSON."""
    path = Path(config_path)
    
    if not path.exists():
        print(f"⚠️  Fichier config non trouvé: {config_path}")
        print("   Copiez config/forwarder.json.example vers config/forwarder.json")
        return None
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Ignorer les commentaires (clés commençant par _)
        data = {k: v for k, v in data.items() if not k.startswith('_')}
        
        if not data.get('enabled', False):
            print("ℹ️  Forwarder désactivé (enabled: false)")
            return None
        
        if not data.get('webhook_url'):
            print("⚠️  webhook_url non configuré")
            print("   Éditez config/forwarder.json")
            return None
        
        return ForwarderConfig(
            webhook_url=data['webhook_url'],
            source_channels=data.get('source_channels', []),
            message_format=data.get('message_format', 'embed'),
            rate_limit_delay=data.get('rate_limit_delay', 0.5),
            enabled=data.get('enabled', False)
        )
    
    except Exception as e:
        print(f"❌ Erreur chargement config: {e}")
        return None
