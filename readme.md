# Wirecord

Intercept and archive Discord traffic through a [mitmproxy](https://mitmproxy.org/) addon, with optional real-time message forwarding to Discord webhooks.

## What it does

Wirecord sits between your Discord client and Discord's servers as a transparent proxy. It:

- **Archives all traffic** — REST API responses and Gateway WebSocket data are saved in raw format to `traffic_archive/`.
- **Forwards messages** — Messages from configured channels are relayed to Discord webhooks in real time, with the original author's username, avatar, and channel name.
- **Exports archives** — Saved traffic can be exported to DiscordChatExporter-compatible JSON or HTML.

## Quick start

### Requirements

- Python 3.10+
- [mitmproxy](https://mitmproxy.org/)

### Install

```bash
git clone https://github.com/Roachbones/discordless
cd discordless
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Install [mitmproxy's CA certificate](https://docs.mitmproxy.org/stable/concepts-certificates/#quick-setup) on every device you want to archive.

### Configure

```bash
cp config.example.json config.json
```

Edit `config.json` with your settings:

```json
{
  "proxy_port": 8080,
  "traffic_archive_dir": "traffic_archive",
  "forwards": [
    {
      "channels": ["SOURCE_CHANNEL_ID"],
      "webhook_url": "https://discord.com/api/webhooks/ID/TOKEN",
      "webhook_channel_id": "",
      "webhook_username": "Interceptor",
      "rate_limit_delay": 0.5
    }
  ]
}
```

| Field | Description |
|---|---|
| `channels` | Source channel IDs to intercept |
| `webhook_url` | Discord webhook URL for the destination |
| `webhook_channel_id` | Thread/forum channel ID (leave empty for regular text channels) |
| `webhook_username` | Fallback display name (overridden by original author name) |
| `rate_limit_delay` | Minimum seconds between webhook requests |

You can define multiple forwarding rules to relay different channels to different webhooks.

### Run

```bash
scripts/start.sh    # Start proxy + Discord
scripts/stop.sh     # Stop both
```

Or run the proxy manually:

```bash
mitmdump -s discordless/addon.py --listen-port=8080 \
  --allow-hosts '^(((.+\.)?discord\.com)|((.+\.)?discordapp\.com)|((.+\.)?discord\.net)|((.+\.)?discordapp\.net)|((.+\.)?discord\.gg))(?::\d+)?$'
```

Then start Discord with the proxy:

```bash
discord --proxy-server=localhost:8080
```

### Docker

```bash
docker compose up --build
```

## Forwarded messages

When forwarding is enabled, messages from monitored channels appear in the destination with:

- The original author's **username** and **avatar**
- The source **channel name** next to the author
- **Attachments** (images, files) as clickable URLs
- **Custom emojis** are forwarded as-is in the text (they will only render if the webhook's server has access to the same emojis)

## Exporting archives

Export saved traffic from `traffic_archive/` to readable formats:

```bash
python3 exporter.py dcejson-exporter    # DiscordChatExporter-compatible JSON
python3 exporter.py html-exporter       # HTML
python3 exporter.py htmeml-exporter     # Memory-efficient paginated HTML
python3 exporter.py <name> -h           # See all options
```

JSON exports are compatible with [DiscordChatExporter-frontend](https://github.com/slatinsky/DiscordChatExporter-frontend) and [chat-analytics](https://github.com/mlomb/chat-analytics).

## Architecture

```
Discord client
    |  (proxy)
mitmproxy + discordless/addon.py
    |-- REST responses  --> traffic_archive/requests/
    |-- Gateway chunks  --> traffic_archive/gateways/
    '-- MESSAGE_CREATE  --> WebhookForwarder --> Discord webhook
```

### Core package: `discordless/`

| File | Role |
|---|---|
| `addon.py` | mitmproxy addon — intercepts, archives, and forwards |
| `config.py` | Loads `config.json` into typed dataclasses |
| `models.py` | `DiscordMessage` — immutable message representation |
| `decoder.py` | `GatewayDecoder` — stateful zlib/zstd + JSON/ETF decoder per WebSocket connection |
| `webhook.py` | `WebhookForwarder` — POST to Discord webhooks with rate limiting |

### Export pipeline: `exporters/`

| Exporter | Output |
|---|---|
| `dcejson/` | DiscordChatExporter-compatible JSON |
| `html/` | Classical HTML chatlog |
| `htmeml/` | Memory-efficient paginated HTML |

### Key technical details

- Gateway data is archived as **raw compressed binary** — exporters can replay and decode it later
- `GatewayDecoder` maintains a **stateful decompressor** per connection (Discord's `zstd-stream` is a continuous stream, not independent frames)
- Message deduplication uses an in-memory set keyed by MD5 of timestamp + author + content
- The proxy only intercepts Discord domains — other traffic passes through untouched

## Testing

```bash
PYTHONPATH=. venv/bin/python -m pytest                          # All tests
PYTHONPATH=. venv/bin/python -m pytest tests/unit/test_config.py  # One file
PYTHONPATH=. venv/bin/python -m pytest -k "test_name"             # By name
```

### Testing with recorded traffic

```bash
# Record
mitmproxy -w discord_dump.flow --set stream_large_bodies=100k \
  --allow-hosts '<discord regex>'

# Replay
mitmdump -s discordless/addon.py --rfile discord_dump.flow
```

## Limitations

- **iOS WebSocket traffic** ignores HTTP proxy settings, so Gateway data from iOS devices is not captured. REST traffic still works.
- **Custom emojis** from other servers won't render in forwarded messages (Discord limitation).
- **Multiple Discord accounts** through the same proxy instance are not supported — all traffic is treated as one account.

## License

MIT
