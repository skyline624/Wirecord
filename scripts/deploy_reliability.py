"""Deploy validated source on panda with capture-only rollback on failure."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path('/root/discord/wirecord')
STAGE=Path('/root/discord/wirecord-validation-20260914')
BACKUPS=Path('/root/backups')
if os.name=='nt' or not ROOT.is_dir() or not STAGE.is_dir():
    raise SystemExit('Run only in the validated VPS environment')
cfg_path=ROOT/'config.json'
if hashlib.sha256(cfg_path.read_bytes()).hexdigest()!='38551ea7fb854b6154883369f338bef8a66464176b2e437edc1f4e9ba4b8000b':
    raise SystemExit('Production config changed since review; re-review before deployment')
backup=BACKUPS/('wirecord-deploy-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
backup.mkdir(mode=0o700)
for folder in ['discordless','scripts','vps-deployment','tests']:
    if (ROOT/folder).exists():shutil.copytree(ROOT/folder,backup/folder)
shutil.copy2(cfg_path,backup/'config.json')
for source,name in [('/usr/local/bin/wirecord-run','wirecord-run'),('/etc/systemd/system/wirecord.service','wirecord.service')]:
    shutil.copy2(source,backup/name)
rollback='''#!/usr/bin/env python3
import json,pathlib,shutil,subprocess
backup=pathlib.Path(__file__).resolve().parent
root=pathlib.Path('/root/discord/wirecord')
subprocess.run(['systemctl','stop','wirecord.service'],check=True)
subprocess.run(['systemctl','disable','--now','wirecord-backup.timer','wirecord-logrotate.timer'],check=False)
for folder in ('discordless','scripts','vps-deployment','tests'):
    if (backup/folder).exists():shutil.copytree(backup/folder,root/folder,dirs_exist_ok=True)
cfg=json.loads((backup/'config.json').read_text())
cfg['forwards']=[]
(root/'config.json').write_text(json.dumps(cfg,indent=2))
(root/'config.json').chmod(0o600)
shutil.copy2(backup/'wirecord-run','/usr/local/bin/wirecord-run')
shutil.copy2(backup/'wirecord.service','/etc/systemd/system/wirecord.service')
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','reset-failed','wirecord.service'],check=True)
subprocess.run(['systemctl','start','wirecord.service'],check=True)
print('Rolled back to capture-only mode; archive and current SQLite ledger preserved')
'''
(backup/'rollback.py').write_text(rollback)
(backup/'rollback.py').chmod(0o700)
print('DEPLOY_BACKUP',backup,flush=True)
subprocess.run(['systemctl','stop','wirecord.service'],check=True)
try:
    for folder in ['discordless','tests','vps-deployment','docs']:
        shutil.copytree(STAGE/folder,ROOT/folder,dirs_exist_ok=True)
    # Preserve each historic standalone sender before replacing it with a refusal shim.
    for name in ['replay_api_send.py','replay_missed.py','replay_missed_gateway.py','replay_missing.py','replay_recovered_20260914.py']:
        target=ROOT/'scripts'/name
        legacy=target.with_suffix('.py.legacy')
        if target.exists() and not legacy.exists():shutil.copy2(target,legacy)
        shutil.copy2(STAGE/'scripts'/name,target)
    cfg=json.loads(cfg_path.read_text())
    cfg.update(delivery_enabled=False,recovery_enabled=True,state_path='state/wirecord.sqlite3',recovery_since='2026-09-08T16:24:00Z',recovery_interval=300,backup_dir='/root/backups/wirecord-daily')
    identifiers={'1190672719415611515':('diplomates','Diplomatie / diplomates'),'1190672068870672506':('representants','Diplomatie / représentants'),
      '1427648152416161874':('aurelis','Aurelis / canal sécurisé Liberastra'),'1476502136161304698':('1cc','1CC / ambassade-liberastra'),
      '1458066665861283964':('sibylla','Sibylla Diplomacy / liberastra'),'1473018573571231856':('test','Liberastra / test'),'1504153316744233120':('recherche','Recherche → Marketplace')}
    for rule in cfg['forwards']:
        rule['rule_id'],rule['label']=identifiers[rule['channels'][0]]
    cfg_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));cfg_path.chmod(0o600)
    (ROOT/'state').mkdir(exist_ok=True,mode=0o700)
    for path in ROOT.glob('config.json.bak*'):path.chmod(0o600)
    shutil.copy2(ROOT/'vps-deployment/wirecord-run','/usr/local/bin/wirecord-run')
    Path('/usr/local/bin/wirecord-run').chmod(0o755)
    for name in ['wirecord.service','wirecord-backup.service','wirecord-backup.timer','wirecord-logrotate.service','wirecord-logrotate.timer']:
        shutil.copy2(ROOT/'vps-deployment'/name,Path('/etc/systemd/system')/name)
    shutil.copy2(ROOT/'vps-deployment/wirecord-logrotate','/etc/logrotate.d/wirecord')
    py=str(ROOT/'venv/bin/python')
    subprocess.run([py,'-m','discordless','check-config'],cwd=ROOT,check=True)
    subprocess.run([py,'-m','discordless','recover','--bootstrap','--execute'],cwd=ROOT,check=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','reset-failed','wirecord.service'],check=True)
    subprocess.run(['systemctl','start','wirecord.service'],check=True)
    print('STARTED_WITH_SENDS_DISABLED',flush=True)
except Exception:
    subprocess.run([sys.executable,str(backup/'rollback.py')],check=True)
    raise
