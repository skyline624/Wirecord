"""Transactional delivery journal shared by capture, recovery and administration."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time


class FileLock:
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if self.path.stat().st_size == 0:
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            self.file = None
            raise RuntimeError("Operation already running") from None
        return self

    def __exit__(self, *args):
        if self.file:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()
            self.file = None


class Store:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Unsupported state schema")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS channels(channel TEXT PRIMARY KEY,checkpoint TEXT,
                    recovered_at REAL,error TEXT,hold INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS deliveries(
                    id INTEGER PRIMARY KEY,rule TEXT NOT NULL,channel TEXT NOT NULL,destination TEXT NOT NULL,
                    source_id TEXT NOT NULL,event_key TEXT NOT NULL,part INTEGER NOT NULL,
                    source_timestamp TEXT NOT NULL,raw TEXT NOT NULL,payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
                    due REAL NOT NULL DEFAULT 0,attempted_at REAL,created_at REAL NOT NULL,
                    sent_at REAL,destination_id TEXT,error TEXT,
                    UNIQUE(rule,event_key,part));
                CREATE INDEX IF NOT EXISTS delivery_state ON deliveries(status,destination,source_id);
                PRAGMA user_version=1;
            """)
        Path(self.path).chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def set_meta(self, key, value):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES(?,?)", (key, json.dumps(value))
            )

    def meta(self, key, default=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key=?", (key,)
            ).fetchone()
            return json.loads(row[0]) if row else default

    def hold(self, channel, held=True, error=None):
        with self.connect() as db:
            db.execute(
                "INSERT INTO channels(channel,hold,error) VALUES(?,?,?) ON CONFLICT(channel) DO UPDATE SET hold=excluded.hold,error=excluded.error",
                (channel, int(held), error),
            )

    def checkpoint(self, channel):
        with self.connect() as db:
            row = db.execute(
                "SELECT checkpoint FROM channels WHERE channel=?", (channel,)
            ).fetchone()
            return row[0] if row else None

    def recovered(self, channel, checkpoint):
        with self.connect() as db:
            db.execute(
                "INSERT INTO channels(channel,checkpoint,recovered_at,hold) VALUES(?,?,?,0) ON CONFLICT(channel) DO UPDATE SET checkpoint=excluded.checkpoint,recovered_at=excluded.recovered_at,error=NULL,hold=0",
                (channel, checkpoint, time.time()),
            )

    def enqueue(self, rule, raw, payloads, event_key=None):
        key = event_key or str(raw["id"])
        with self.connect() as db:
            for part, payload in enumerate(payloads):
                db.execute(
                    """INSERT OR IGNORE INTO deliveries(rule,channel,destination,source_id,event_key,part,source_timestamp,raw,payload,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        rule.rule_id,
                        str(raw["channel_id"]),
                        rule.destination,
                        str(raw["id"]),
                        key,
                        part,
                        raw["timestamp"],
                        json.dumps(raw),
                        json.dumps(payload),
                        time.time(),
                    ),
                )

    def rows(self, where="1", params=()):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM deliveries WHERE "
                    + where
                    + " ORDER BY CAST(source_id AS INTEGER),event_key,part",
                    params,
                )
            ]

    def update(self, delivery_id, **fields):
        allowed = {
            "status",
            "error",
            "due",
            "sent_at",
            "destination_id",
            "attempted_at",
        }
        if not fields or not set(fields) <= allowed:
            raise ValueError("Invalid delivery update")
        with self.connect() as db:
            db.execute(
                "UPDATE deliveries SET "
                + ",".join(k + "=?" for k in fields)
                + " WHERE id=?",
                (*fields.values(), delivery_id),
            )

    def resume(self):
        with self.connect() as db:
            db.execute(
                "UPDATE deliveries SET status='uncertain',error='process_interrupted' WHERE status='inflight'"
            )

    def claim(self, rules, now=None):
        import random

        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # A held source pauses its whole destination, including newer live events.
            held = {
                r[0] for r in db.execute("SELECT channel FROM channels WHERE hold=1")
            }
            blocked_dest = {
                r.destination for r in rules.values() if held.intersection(r.channels)
            }
            blocked_rule = {
                r[0]
                for r in db.execute(
                    "SELECT DISTINCT rule FROM deliveries WHERE status='blocked'"
                )
            }
            candidates = db.execute(
                "SELECT * FROM deliveries WHERE status!='sent' ORDER BY CAST(source_id AS INTEGER),event_key,part"
            ).fetchall()
            seen_dest = set()
            for row in candidates:
                rule = rules.get(row["rule"])
                dest = row["destination"]
                if not rule or dest in seen_dest or dest in blocked_dest:
                    continue
                seen_dest.add(dest)
                if row["rule"] in blocked_rule or row["status"] not in (
                    "pending",
                    "retry",
                ):
                    continue
                if row["due"] == 0:
                    lo, hi = rule.delay_range
                    delay = random.uniform(
                        max(lo, 1 if rule.native else 0.5),
                        max(hi, 1 if rule.native else 0.5),
                    )
                    db.execute(
                        "UPDATE deliveries SET due=? WHERE id=?",
                        (now + delay, row["id"]),
                    )
                    continue
                if row["due"] > now:
                    continue
                db.execute(
                    "UPDATE deliveries SET status='inflight',attempts=attempts+1,attempted_at=? WHERE id=?",
                    (now, row["id"]),
                )
                result = dict(row)
                result.update(
                    status="inflight", attempts=row["attempts"] + 1, attempted_at=now
                )
                return result
        return None
