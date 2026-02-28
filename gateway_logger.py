#!/usr/bin/env python3
"""Logger de messages Discord Gateway."""

import json
import os
import sys
import time
import subprocess
import signal
import hashlib
from datetime import datetime

ARCHIVE_DIR = "traffic_archive"
GATEWAYS_DIR = os.path.join(ARCHIVE_DIR, "gateways")
LOGS_DIR = "logs/messages"

running = True
seen_message_keys = set()
log_files = {}
last_log_date = None
PERSISTENCE_FILE = "logs/.seen_keys.json"

def load_seen_ids():
    if os.path.exists(PERSISTENCE_FILE):
        try:
            with open(PERSISTENCE_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('keys', []))
        except:
            pass
    return set()

def save_seen_ids():
    try:
        keys_list = list(seen_message_keys)[-3000:] if len(seen_message_keys) > 3000 else list(seen_message_keys)
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump({'keys': keys_list, 'last_saved': datetime.now().isoformat()}, f)
    except Exception as e:
        pass

def ensure_dirs():
    os.makedirs(LOGS_DIR, exist_ok=True)

def get_log_filename(channel_id=None):
    today = datetime.now().strftime("%Y%m%d")
    if channel_id:
        return os.path.join(LOGS_DIR, f"channel_{channel_id}_{today}.log")
    return os.path.join(LOGS_DIR, f"all_messages_{today}.log")

def get_current_date():
    return datetime.now().strftime("%Y%m%d")

def rotate_logs_if_needed():
    global last_log_date, log_files
    current_date = get_current_date()
    if last_log_date != current_date:
        for f in log_files.values():
            try:
                f.close()
            except:
                pass
        log_files = {}
        last_log_date = current_date

def get_log_file(channel_id=None):
    global log_files
    key = channel_id or "all"
    if key not in log_files or log_files[key].closed:
        filepath = get_log_filename(channel_id)
        log_files[key] = open(filepath, 'a', encoding='utf-8', buffering=1)
    return log_files[key]

def write_log(message_data, target_channels=None):
    rotate_logs_if_needed()
    timestamp = message_data['timestamp']
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        formatted_time = timestamp
    channel_id = message_data['channel_id']
    channel_short = channel_id[-8:] if len(channel_id) > 8 else channel_id
    log_line = f"[{formatted_time}] [#{channel_short}] @{message_data['username']}: {message_data['content']}\n"
    log_file = get_log_file(None)
    log_file.write(log_line)
    log_file.flush()
    if target_channels and channel_id in target_channels:
        specific_log = get_log_file(channel_id)
        specific_log.write(log_line)
        specific_log.flush()

def scan_gateway_files():
    if not os.path.exists(GATEWAYS_DIR):
        return []
    data_files = []
    for f in os.listdir(GATEWAYS_DIR):
        if f.endswith('_data'):
            data_files.append(os.path.join(GATEWAYS_DIR, f))
    return sorted(data_files)

def convert_payload(payload):
    if isinstance(payload, bytes):
        try:
            return payload.decode('utf-8')
        except:
            return str(payload)
    elif isinstance(payload, list):
        return [convert_payload(x) for x in payload]
    elif isinstance(payload, dict):
        return {convert_payload(k): convert_payload(v) for k, v in payload.items()}
    return payload

def process_payload(payload, target_channels):
    global seen_message_keys
    if not isinstance(payload, dict):
        return None
    msg_type = payload.get('t')
    if msg_type != 'MESSAGE_CREATE':
        return None
    data = payload.get('d', {})
    if not isinstance(data, dict):
        return None
    
    # Créer une clé unique basée sur le contenu pour déduplication
    timestamp = str(data.get('timestamp', ''))
    author = str(data.get('author', {}).get('username', 'unknown'))
    content = str(data.get('content', ''))
    channel_id = str(data.get('channel_id', ''))
    
    # Clé de déduplication basée sur le contenu (pas l'ID Discord)
    content_hash = hashlib.md5(f"{timestamp}:{author}:{content}".encode()).hexdigest()[:16]
    message_key = f"{channel_id}:{content_hash}"
    
    if not message_key or message_key in seen_message_keys:
        return None
    
    seen_message_keys.add(message_key)
    if len(seen_message_keys) > 10000:
        seen_message_keys.clear()
    
    return {
        'id': str(data.get('id', '')),
        'channel_id': channel_id,
        'username': author,
        'content': content,
        'timestamp': timestamp
    }

def parse_file(filepath, target_channels):
    try:
        import erlpack
        result = subprocess.run(['zstdcat', filepath], capture_output=True, timeout=30)
        data = result.stdout
        offset = 0
        count = 0
        while offset < len(data) - 5:
            if data[offset] == 0x83:
                try:
                    payload = erlpack.unpack(data[offset:offset+500000])
                    p = convert_payload(payload)
                    msg = process_payload(p, target_channels)
                    if msg:
                        write_log(msg, target_channels)
                        count += 1
                    offset += 100
                except:
                    offset += 1
            else:
                offset += 1
        return count
    except Exception as e:
        return 0

def signal_handler(sig, frame):
    global running
    running = False

def main():
    global running, last_log_date, seen_message_keys
    seen_message_keys = load_seen_ids()
    loaded_count = len(seen_message_keys)
    target_channels = set(sys.argv[1:]) if len(sys.argv) > 1 else set()
    ensure_dirs()
    last_log_date = get_current_date()
    signal.signal(signal.SIGINT, signal_handler)
    print("Logger demarre...")
    if loaded_count > 0:
        print(f"Clés chargées: {loaded_count}")
    if target_channels:
        print(f"Canaux: {target_channels}")
    message_count = 0
    processed = {}
    save_counter = 0
    while running:
        files = scan_gateway_files()
        activity = False
        for filepath in files:
            try:
                size = os.path.getsize(filepath)
                if filepath not in processed or processed[filepath] != size:
                    old = processed.get(filepath, 0)
                    processed[filepath] = size
                    if old == 0:
                        print(f"Nouveau: {os.path.basename(filepath)}")
                    added = parse_file(filepath, target_channels)
                    if added > 0:
                        print(f"  +{added} messages")
                        message_count += added
                        activity = True
                        save_counter += added
                        if save_counter >= 100:
                            save_seen_ids()
                            save_counter = 0
            except:
                continue
        if not activity:
            time.sleep(2)
        else:
            time.sleep(0.5)
    for f in log_files.values():
        try:
            f.close()
        except:
            pass
    save_seen_ids()
    print(f"Logger arrete. {message_count} messages.")

if __name__ == "__main__":
    main()
