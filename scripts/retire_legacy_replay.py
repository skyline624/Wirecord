"""Retain dated sender sources, replacing their launchers with safe CLI guidance."""
from pathlib import Path

root=Path(__file__).resolve().parent
names=['replay_api_send.py','replay_missed.py','replay_missed_gateway.py','replay_missing.py','replay_recovered_20260914.py']
for name in names:
    path=root/name
    if path.exists() and not path.with_suffix('.py.legacy').exists():
        path.replace(path.with_suffix('.py.legacy'))
    path.write_text('''#!/usr/bin/env python3
"""Retired: delivery is now owned exclusively by the persistent runtime."""
raise SystemExit("Legacy sender disabled. Use python -m discordless recover (dry-run), then --execute to archive and queue monitored messages.")
''',encoding='utf-8',newline='\n')
