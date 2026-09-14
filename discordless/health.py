"""Gateway liveness independent from user-message traffic."""

import os
import time
from discordless.config import ACCOUNT_ID


class GatewayHealth:
    def __init__(self):
        self.state = {
            "started_at": time.time(),
            "updated_at": time.time(),
            "pid": os.getpid(),
            "connection": None,
            "interval": 45,
            "ready": False,
            "account": None,
            "ack_at": None,
            "error": None,
        }

    def observe(self, connection, payload):
        now = time.time()
        if payload.get("op") == 10:
            self.state.update(
                connection=str(connection),
                connected_at=now,
                ready=False,
                ack_at=None,
                interval=float(payload.get("d", {}).get("heartbeat_interval", 45000))
                / 1000,
                error=None,
            )
        if str(connection) != self.state["connection"]:
            return
        if payload.get("op") == 11:
            self.state["ack_at"] = now
        if payload.get("t") == "READY":
            account = str(payload.get("d", {}).get("user", {}).get("id", ""))
            self.state.update(
                account=account,
                ready=account == ACCOUNT_ID,
                error=None if account == ACCOUNT_ID else "account_mismatch",
            )
        elif payload.get("t") == "RESUMED":
            self.state["ready"] = self.state["account"] == ACCOUNT_ID
        self.state["updated_at"] = now

    def disconnected(self, connection):
        if str(connection) == self.state["connection"]:
            self.state["ready"] = False

    def snapshot(self):
        return dict(self.state, updated_at=time.time())


def healthy(state, now=None):
    now = time.time() if now is None else now
    if not state:
        return False
    if state.get("error"):
        return False
    if now - state.get("updated_at", 0) > 30:
        return False
    if now - state.get("started_at", 0) < 120:
        return True
    if not state.get("ready") or state.get("account") != ACCOUNT_ID:
        return False
    reference = state.get("ack_at") or state.get("connected_at", state["started_at"])
    return now - reference <= 3 * state.get("interval", 45)
