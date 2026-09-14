"""Monitored-only recovery, historical reconciliation and durable checkpoints."""

from datetime import datetime
import json
from pathlib import Path
import re
import time

from discordless.archive import ArchiveWriter
from discordless.store import FileLock
from discordless.transport import APIError, DiscordAPI, matches, payloads


def snowflake(timestamp):
    return str(
        int(
            (
                datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
                * 1000
                - 1420070400000
            )
        )
        << 22
    )


def import_proofs(root):
    proofs = {}
    ledger = Path(root) / "recovery_20260914/forwarded_messages.json"
    if ledger.exists():
        for mid, record in json.loads(ledger.read_text()).items():
            if record.get("verified"):
                proofs[(str(record["source_channel_id"]), str(mid))] = str(
                    record["destination_message_id"]
                )
    for path in (Path(root) / "scripts").glob(".replay_sent_*.txt"):
        channel = path.stem.removeprefix(".replay_sent_")
        for mid in path.read_text().splitlines():
            if mid.isdigit():
                proofs.setdefault((channel, mid), "historical-success")
    # Only exact success logs, never 'queued' or arbitrary identifiers.
    log = Path(root) / "logs/mitmdump.log"
    if log.exists():
        with log.open(errors="replace") as stream:
            for line in stream:
                match = re.search(r"forwarded (\d+) → webhook msg (\d+)", line)
                if match:
                    proofs[("", match[1])] = match[2]
    return proofs


class Recovery:
    def __init__(self, config, store, api=None, archive=None, root=None):
        self.config = config
        self.store = store
        self.api = api or DiscordAPI(config)
        self.archive = archive
        self.root = Path(root or ".")

    def run(self, channel=None, execute=False, bootstrap=False, stop=None):
        channels = sorted({c for r in self.config.forwards for c in r.channels})
        if channel:
            if channel not in channels:
                raise ValueError("Channel is not monitored")
            channels = [channel]
        if execute:
            with FileLock(self.store.path + ".recovery.lock"):
                return self._run(channels, True, bootstrap, stop)
        return self._run(channels, False, bootstrap, stop)

    def _run(self, channels, execute, bootstrap, stop):
        results = []
        proofs = import_proofs(self.root) if bootstrap else {}
        start = snowflake(self.config.recovery_since)
        for channel in channels:
            if stop and stop.is_set():
                break
            if execute:
                self.store.hold(channel)
            rules = [r for r in self.config.forwards if channel in r.channels]
            after = (self.store.checkpoint(channel) if self.store else None) or start
            if bootstrap:
                after = start
            cutoff = str((int(time.time() * 1000) - 1420070400000) << 22)
            count = 0
            try:
                info = self.api.get(f"/channels/{channel}")
                # Capture an upper boundary; recent live messages wait behind held recovery.
                messages = list(self.api.history(channel, after, cutoff))
                messages.sort(key=lambda m: int(m["id"]))
                destinations = {}
                if bootstrap:
                    for rule in rules:
                        destinations[rule.rule_id] = list(
                            self.api.history(rule.destination, start)
                        )
                        destination_info = self.api.get(f"/channels/{rule.destination}")
                        if execute:
                            self.store.set_meta(
                                "destination_guild:" + rule.rule_id,
                                destination_info.get("guild_id", "@me"),
                            )
                if execute:
                    if self.archive is None:
                        self.archive = ArchiveWriter(self.config.traffic_archive_dir)
                    for offset in range(0, len(messages), 100):
                        self.archive.messages(channel, messages[offset : offset + 100])
                for message in messages:
                    message["channel_id"] = channel
                    message["guild_id"] = info.get("guild_id", "")
                    message["_channel_name"] = info.get("name", channel)
                    for rule in rules:
                        parts = payloads(rule, message)
                        if not execute:
                            continue
                        self.store.enqueue(rule, message, parts)
                        if bootstrap:
                            rows = self.store.rows(
                                "rule=? AND event_key=?",
                                (rule.rule_id, str(message["id"])),
                            )
                            proof = proofs.get(
                                (channel, str(message["id"]))
                            ) or proofs.get(("", str(message["id"])))
                            for row in rows:
                                if row["status"] == "sent":
                                    continue
                                candidates = [
                                    d
                                    for d in destinations[rule.rule_id]
                                    if int(d["id"]) > int(message["id"])
                                    and matches(
                                        json.loads(row["payload"]),
                                        d,
                                        rule.native,
                                        require_account=False,
                                    )
                                ]
                                if proof and row["part"] == 0:
                                    acknowledged = next(
                                        (
                                            d
                                            for d in destinations[rule.rule_id]
                                            if d["id"] == proof
                                        ),
                                        None,
                                    )
                                    self.store.update(
                                        row["id"],
                                        status="sent",
                                        destination_id=proof,
                                        error=None,
                                        sent_at=datetime.fromisoformat(
                                            acknowledged["timestamp"]
                                        ).timestamp()
                                        if acknowledged
                                        else None,
                                    )
                                elif len(candidates) == 1:
                                    self.store.update(
                                        row["id"],
                                        status="sent",
                                        destination_id=candidates[0]["id"],
                                        error=None,
                                        sent_at=datetime.fromisoformat(
                                            candidates[0]["timestamp"]
                                        ).timestamp(),
                                    )
                                elif len(candidates) > 1:
                                    self.store.update(
                                        row["id"],
                                        status="uncertain",
                                        error="historical_match_ambiguous",
                                    )
                    count += 1
                if execute:
                    # Advance only through messages actually returned, not wall-clock
                    # time: a briefly delayed API result must remain recoverable.
                    recovered_id = max([int(after)] + [int(m["id"]) for m in messages])
                    self.store.recovered(channel, str(recovered_id))
                    if bootstrap:
                        self.store.set_meta("bootstrap:" + channel, True)
                results.append({"channel": channel, "recovered": count, "error": None})
            except APIError as error:
                if execute:
                    self.store.hold(channel, True, "http_" + str(error.status))
                results.append(
                    {
                        "channel": channel,
                        "recovered": count,
                        "error": "http_" + str(error.status),
                    }
                )
            except Exception as error:
                if execute:
                    self.store.hold(channel, True, type(error).__name__)
                results.append(
                    {
                        "channel": channel,
                        "recovered": count,
                        "error": type(error).__name__,
                    }
                )
        return results
