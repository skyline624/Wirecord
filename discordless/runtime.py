"""One capture runtime with durable delivery and recovery workers."""

from datetime import datetime, timezone
import json
import logging
import threading
import time

import requests

from discordless.health import GatewayHealth
from discordless.recovery import Recovery, snowflake
from discordless.store import FileLock, Store
from discordless.transport import APIError, DiscordAPI, matches, payloads

log = logging.getLogger("wirecord")


def deliver_one(store, rule, row, api):
    try:
        response = api.send(rule, json.loads(row["payload"]))
    except APIError as error:
        store.update(row["id"], status="blocked", error="auth_" + str(error.status))
        return
    except requests.ConnectTimeout:
        store.update(
            row["id"],
            status="retry",
            due=time.time() + min(300, 2 ** min(row["attempts"], 8)),
            error="connect_timeout",
        )
        return
    except requests.RequestException:
        store.update(row["id"], status="uncertain", error="response_lost")
        return
    status = response.status_code
    if status in (200, 201):
        try:
            data = response.json()
            if str(data.get("channel_id")) != rule.destination or not data.get("id"):
                raise ValueError()
            store.update(
                row["id"],
                status="sent",
                destination_id=str(data["id"]),
                sent_at=time.time(),
                error=None,
            )
        except (ValueError, TypeError):
            store.update(row["id"], status="uncertain", error="invalid_ack")
    elif status == 429:
        try:
            delay = max(1, float(response.json().get("retry_after", 1)))
        except (ValueError, TypeError):
            delay = 5
        store.update(
            row["id"], status="retry", due=time.time() + delay + 0.3, error="http_429"
        )
    elif status >= 500 or status in (408, 409):
        store.update(row["id"], status="uncertain", error="http_" + str(status))
    else:
        store.update(row["id"], status="blocked", error="http_" + str(status))


def reconcile_uncertain(store, rules, api):
    for row in store.rows("status='uncertain'"):
        rule = rules.get(row["rule"])
        if not rule or not row.get("attempted_at"):
            continue
        cutoff = datetime.fromtimestamp(
            row["attempted_at"] - 5, timezone.utc
        ).isoformat()
        try:
            found = [
                m
                for m in api.history(rule.destination, snowflake(cutoff))
                if matches(json.loads(row["payload"]), m, rule.native)
            ]
        except APIError:
            continue
        if len(found) == 1:
            store.update(
                row["id"],
                status="sent",
                destination_id=found[0]["id"],
                sent_at=datetime.fromisoformat(found[0]["timestamp"]).timestamp(),
                error=None,
            )


class Runtime:
    def __init__(self, config, archive):
        self.config = config
        self.archive = archive
        self.store = Store(config.state_path)
        self.rules = {r.rule_id: r for r in config.forwards}
        self.health = GatewayHealth()
        self.stop = threading.Event()
        self.wakeup = threading.Event()
        self.lock = FileLock(self.store.path + ".runtime.lock")
        self.threads = []

    def start(self):
        self.lock.__enter__()
        self.store.resume()
        for c in {c for r in self.rules.values() for c in r.channels}:
            self.store.hold(c, self.config.recovery_enabled)
        self.store.set_meta("health", self.health.snapshot())
        for target in (self._maintenance, self._sender, self._recover):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.threads.append(thread)

    def close(self):
        self.stop.set()
        self.wakeup.set()
        # Inflight operations may finish; shutdown never drains or reschedules pending work.
        deadline = time.monotonic() + 23
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))
        self.health.state["error"] = "stopped"
        self.store.set_meta("health", self.health.snapshot())
        self.lock.__exit__()

    def observe(self, connection, payload):
        self.health.observe(connection, payload)
        if payload.get("t") in ("READY", "RESUMED"):
            self.wakeup.set()
        self.store.set_meta("health", self.health.snapshot())

    def capture(self, raw, channel_name=""):
        raw = dict(raw)
        raw["_channel_name"] = channel_name
        channel = str(raw.get("channel_id", ""))
        for rule in self.rules.values():
            if channel in rule.channels and raw.get("id") and raw.get("timestamp"):
                self.store.enqueue(rule, raw, payloads(rule, raw))
                self.store.set_meta("last_capture:" + channel, raw["timestamp"])

    def edit(self, update):
        if not update.get("edited_timestamp") or "content" not in update:
            return
        for rule in self.rules.values():
            if rule.native or str(update.get("channel_id")) not in rule.channels:
                continue
            original = self.store.rows(
                "rule=? AND event_key=? AND part=0 AND status=?",
                (rule.rule_id, str(update.get("id")), "sent"),
            )
            if not original:
                continue
            previous = original[0]
            raw = json.loads(previous["raw"])
            raw.update(update)
            guild = self.store.meta("destination_guild:" + rule.rule_id, "@me")
            link = f"https://discord.com/channels/{guild}/{rule.destination}/{previous['destination_id']}"
            raw["content"] = f"✏️ **Edited** — [original message]({link})\n" + str(
                update["content"]
            )
            raw["embeds"] = []
            raw["attachments"] = []
            self.store.enqueue(
                rule,
                raw,
                payloads(rule, raw),
                str(raw["id"]) + ":edit:" + str(update["edited_timestamp"]),
            )

    def _maintenance(self):
        while not self.stop.wait(5):
            self.store.set_meta("health", self.health.snapshot())

    def _sender(self):
        api = DiscordAPI(self.config)
        next_reconcile = 0
        while not self.stop.wait(0.25):
            if not self.config.delivery_enabled:
                continue
            eligible = {
                key: r
                for key, r in self.rules.items()
                if all(self.store.meta("bootstrap:" + c, False) for c in r.channels)
            }
            if not eligible:
                continue
            row = None
            try:
                if time.time() > next_reconcile:
                    reconcile_uncertain(self.store, eligible, api)
                    next_reconcile = time.time() + 300
                row = self.store.claim(eligible)
                if row:
                    deliver_one(self.store, self.rules[row["rule"]], row, api)
            except Exception as error:
                if row:
                    self.store.update(
                        row["id"],
                        status="uncertain",
                        error="worker_" + type(error).__name__,
                    )
                log.error("Delivery worker error: %s", type(error).__name__)
                self.store.set_meta("delivery_error", type(error).__name__)

    def _recover(self):
        recovery = Recovery(self.config, self.store, archive=self.archive)
        while not self.stop.is_set():
            if self.config.recovery_enabled:
                try:
                    # Before explicit initial bootstrap, keep sources held and do not
                    # advance checkpoints that would hide the historic outage.
                    for c in {c for r in self.rules.values() for c in r.channels}:
                        if self.store.meta("bootstrap:" + c, False):
                            recovery.run(c, execute=True, stop=self.stop)
                except Exception as error:
                    log.error("Recovery worker error: %s", type(error).__name__)
            self.wakeup.wait(self.config.recovery_interval)
            self.wakeup.clear()
