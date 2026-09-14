"""Credential-safe HTTP access and common payload generation."""

import base64
import hashlib
import time

import requests

from discordless.config import ACCOUNT_ID
from discordless.native_forward import API_BASE, _collect_tokens, client_headers
from discordless.webhook import split_content


class APIError(Exception):
    def __init__(self, status, code=None):
        self.status = status
        self.code = code
        super().__init__(f"Discord HTTP {status}")


def clean_embed(embed):
    result = {
        k: embed[k]
        for k in ("title", "description", "url", "timestamp", "color", "fields")
        if k in embed
    }
    for field, keys in [
        ("image", ("url",)),
        ("thumbnail", ("url",)),
        ("footer", ("text", "icon_url")),
        ("author", ("name", "url", "icon_url")),
    ]:
        if field in embed:
            result[field] = {k: embed[field][k] for k in keys if k in embed[field]}
    return result


def payloads(rule, raw):
    if not raw.get("content") and not any(
        raw.get(k) for k in ("attachments", "embeds", "sticker_items")
    ):
        return []
    if rule.native:
        ref = {
            "type": 1,
            "channel_id": str(raw["channel_id"]),
            "message_id": str(raw["id"]),
        }
        if raw.get("guild_id"):
            ref["guild_id"] = str(raw["guild_id"])
        nonce = str(
            int(
                hashlib.sha256((rule.rule_id + str(raw["id"])).encode()).hexdigest()[
                    :15
                ],
                16,
            )
        )
        return [
            {
                "content": "",
                "flags": 0,
                "tts": False,
                "allowed_mentions": {"parse": []},
                "nonce": nonce,
                "enforce_nonce": True,
                "message_reference": ref,
            }
        ]
    content = raw.get("content") or ""
    for a in raw.get("attachments", []):
        if a.get("url"):
            content += ("\n" if content else "") + a["url"]
    for sticker in raw.get("sticker_items", []):
        if sticker.get("id"):
            extension = "gif" if sticker.get("format_type") == 4 else "png"
            content += (
                f"\nhttps://media.discordapp.net/stickers/{sticker['id']}.{extension}"
            )
    embeds = [
        clean_embed(e) for e in raw.get("embeds", []) if e.get("type", "rich") == "rich"
    ]
    # A single source message may contain >6000 total embed characters. Preserve
    # each valid embed, distributing across posts within the aggregate limit.
    groups, group, size = [], [], 0
    for e in embeds:
        count = (
            len(e.get("title", ""))
            + len(e.get("description", ""))
            + len(e.get("footer", {}).get("text", ""))
            + len(e.get("author", {}).get("name", ""))
            + sum(
                len(f.get("name", "")) + len(f.get("value", ""))
                for f in e.get("fields", [])
            )
        )
        if group and (len(group) >= 10 or size + count > 6000):
            groups.append(group)
            group = []
            size = 0
        group.append(e)
        size += count
    if group:
        groups.append(group)
    chunks = split_content(content)
    author = raw.get("author", {})
    result = []
    for i in range(max(len(chunks), len(groups))):
        p = {
            "username": f"@{author.get('username', 'unknown')} · #{raw.get('_channel_name', raw['channel_id'])}"[
                :80
            ],
            "content": chunks[i] if i < len(chunks) else "",
            "allowed_mentions": {"parse": []},
        }
        if i < len(groups):
            p["embeds"] = groups[i]
        if author.get("avatar") and author.get("id"):
            p["avatar_url"] = (
                f"https://cdn.discordapp.com/avatars/{author['id']}/{author['avatar']}.png?size=128"
            )
        result.append(p)
    return result


class DiscordAPI:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.trust_env = False
        self.webhooks = requests.Session()
        self.webhooks.trust_env = False
        self.authenticated = False

    def authenticate(self):
        candidates = (
            [self.config.user_token] if self.config.user_token else _collect_tokens()
        )
        for token in candidates:
            try:
                owner = base64.urlsafe_b64decode(token.split(".")[0] + "===").decode()
            except Exception:
                continue
            if owner != ACCOUNT_ID:
                continue
            self.session.headers.update(client_headers(token))
            try:
                r = self.session.get(API_BASE + "/users/@me", timeout=15)
                if r.status_code == 200 and r.json().get("id") == ACCOUNT_ID:
                    self.authenticated = True
                    return
            except (requests.RequestException, ValueError):
                continue
        self.session.headers.pop("Authorization", None)
        raise APIError(401)

    def get(self, endpoint, params=None):
        if not self.authenticated:
            self.authenticate()
        for attempt in range(6):
            try:
                r = self.session.get(API_BASE + endpoint, params=params, timeout=20)
            except requests.RequestException:
                if attempt == 5:
                    raise APIError(0) from None
                time.sleep(min(2**attempt, 16))
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 1)) + 0.3)
                continue
            if r.status_code >= 500 and attempt < 5:
                time.sleep(min(2**attempt, 16))
                continue
            if r.status_code == 401:
                self.authenticated = False
            raise APIError(r.status_code)
        raise APIError(429)

    def history(self, channel, after, stop=None):
        before = stop
        for _ in range(10000):
            params = {"limit": 100}
            if before:
                params["before"] = str(before)
            page = self.get(f"/channels/{channel}/messages", params)
            if not page:
                return
            for message in page:
                if int(message["id"]) > int(after):
                    yield message
            oldest = min(int(m["id"]) for m in page)
            if oldest <= int(after) or len(page) < 100:
                return
            if before and oldest >= int(before):
                raise APIError(0)
            before = oldest
            time.sleep(0.3)
        raise APIError(0)

    def read_message(self, channel, mid):
        page = self.get(f"/channels/{channel}/messages", {"around": mid, "limit": 10})
        return next((m for m in page if m["id"] == mid), None)

    def send(self, rule, payload):
        # No implicit retry of POST: response loss is a durable uncertain delivery.
        if rule.native:
            if not self.authenticated:
                self.authenticate()
            return self.session.post(
                API_BASE + f"/channels/{rule.destination}/messages",
                json=payload,
                timeout=20,
            )
        params = {"wait": "true"}
        if rule.webhook_channel_id:
            params["thread_id"] = rule.webhook_channel_id
        return self.webhooks.post(
            rule.webhook_url, params=params, json=payload, timeout=20
        )


def matches(payload, candidate, native=False, require_account=True):
    if native:
        reference = candidate.get("message_reference", {})
        return (
            reference.get("type") == 1
            and reference.get("message_id")
            == payload["message_reference"]["message_id"]
            and (
                not require_account
                or candidate.get("author", {}).get("id") == ACCOUNT_ID
            )
        )
    author = candidate.get("author", {}).get("username", "")
    expected = payload.get("username", "").split(" · ")[0]
    author_matches = (
        not author
        or not expected
        or author == payload.get("username")
        or author.startswith(expected + " · ")
    )
    return (
        bool(candidate.get("webhook_id"))
        and author_matches
        and candidate.get("content", "") == payload.get("content", "")
        and [
            clean_embed(e)
            for e in candidate.get("embeds", [])
            if e.get("type", "rich") == "rich"
        ]
        == payload.get("embeds", [])
    )
