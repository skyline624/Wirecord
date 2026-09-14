"""Package current source without credentials for isolated Linux validation."""
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parent.parent
output=root.parent/'wirecord-validation.tar.gz'
with tarfile.open(output,'w:gz') as archive:
    for directory in ['discordless','exporters','tests','vps-deployment','docs']:
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.add(path,arcname=path.relative_to(root).as_posix())
    for name in ['pyproject.toml','requirements.txt','exporter.py','readme.md']:
        archive.add(root/name,arcname=name)
    for name in ['replay_api_send.py','replay_missed.py','replay_missed_gateway.py','replay_missing.py','replay_recovered_20260914.py','retire_legacy_replay.py']:
        archive.add(root/'scripts'/name,arcname='scripts/'+name)
print(output)
