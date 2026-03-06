"""Client webhook Discord."""
import requests
import time
from dataclasses import dataclass
from typing import Optional, List, Dict

@dataclass
class WebhookMessage:
    content: str
    username: str = "Gateway Logger"
    avatar_url: Optional[str] = None
    embeds: Optional[List[Dict]] = None

class WebhookClient:
    """Client pour envoyer des messages via webhook Discord."""

    def __init__(self, webhook_url: str, rate_limit_delay: float = 0.5):
        self.webhook_url = webhook_url
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0

    def send(self, message: WebhookMessage) -> bool:
        """Envoie un message via webhook."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        payload = {"content": message.content, "username": message.username}
        if message.avatar_url:
            payload["avatar_url"] = message.avatar_url
        if message.embeds:
            payload["embeds"] = message.embeds

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            self.last_request_time = time.time()
            return response.status_code == 204
        except Exception as e:
            print(f"Erreur webhook: {e}")
            return False
