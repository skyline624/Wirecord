"""Append-only, exporter-compatible REST records with stable hashes."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from discordless.store import FileLock


@contextmanager
def archive_lock(root):
    lock = FileLock(Path(root) / ".writer.lock")
    deadline = time.monotonic() + 30
    while True:
        try:
            lock.__enter__()
            break
        except RuntimeError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.02)
    try:
        yield
    finally:
        lock.__exit__()


class ArchiveWriter:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / "requests").mkdir(parents=True, exist_ok=True)
        (self.root / "gateways").mkdir(exist_ok=True)
        self.seen = set()
        index = self.root / "request_index"
        if index.exists():
            for row in index.read_text().splitlines():
                fields = row.split(maxsplit=4)
                if len(fields) != 5:
                    continue
                _, _, url, digest, name = fields
                if len(digest) != 64:
                    source = self.root / "requests" / name
                    if not source.is_file():
                        continue
                    digest = hashlib.sha256(source.read_bytes()).hexdigest()
                self.seen.add((url, digest))

    def response(self, url, data, method="GET", timestamp=None):
        digest = hashlib.sha256(data).hexdigest()
        if (url, digest) in self.seen:
            return
        filename = "sha256_" + uuid.uuid4().hex
        destination = self.root / "requests" / filename
        temporary = destination.with_suffix(".tmp")
        with archive_lock(self.root):
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(destination)
            with (self.root / "request_index").open("a", encoding="utf-8") as index:
                index.write(
                    f"{timestamp or time.time()} {method} {url} {digest} {filename}\n"
                )
                index.flush()
                os.fsync(index.fileno())
        self.seen.add((url, digest))

    def messages(self, channel, messages):
        if messages:
            self.response(
                f"https://discord.com/api/v9/channels/{channel}/messages?limit=100",
                json.dumps(messages, ensure_ascii=False).encode(),
            )
