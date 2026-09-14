"""Wirecord operator CLI: safe inspection by default, explicit queue changes."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import time
from zoneinfo import ZoneInfo

from discordless.config import Config, ConfigError
from discordless.health import healthy
from discordless.recovery import Recovery
from discordless.store import Store
from discordless.transport import APIError, DiscordAPI, matches


def load_config(path):
    config = Config.load(path)
    root = Path(path).resolve().parent
    for name in ("state_path", "traffic_archive_dir"):
        p = Path(getattr(config, name))
        if not p.is_absolute():
            setattr(config, name, str(root / p))
    return config


def inspect_state(config):
    path = Path(config.state_path)
    if not path.exists():
        return {"health": None, "channels": [], "deliveries": []}
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        health = connection.execute(
            "SELECT value FROM metadata WHERE key='health'"
        ).fetchone()
        return {
            "health": json.loads(health[0]) if health else None,
            "channels": [dict(r) for r in connection.execute("SELECT * FROM channels")],
            "deliveries": [
                dict(r)
                for r in connection.execute(
                    "SELECT rule,channel,source_id,status,source_timestamp,sent_at,error FROM deliveries"
                )
            ],
            "metadata": {
                r["key"]: json.loads(r["value"])
                for r in connection.execute("SELECT * FROM metadata")
            },
        }
    finally:
        connection.close()


def state_report(config):
    state = inspect_state(config)
    routes = []
    for r in config.forwards:
        deliveries = [d for d in state["deliveries"] if d["rule"] == r.rule_id]
        counts = {
            s: sum(d["status"] == s for d in deliveries)
            for s in ("pending", "inflight", "sent", "retry", "blocked", "uncertain")
        }
        channels = [c for c in state["channels"] if c["channel"] in r.channels]
        pending = [d for d in deliveries if d["status"] != "sent"]
        oldest = min((d["source_timestamp"] for d in pending), default=None)
        routes.append(
            {
                "rule_id": r.rule_id,
                "label": r.label,
                "sources": r.channels,
                "destination": r.destination,
                "counts": counts,
                "channels": channels,
                "last_received": max(
                    (
                        state.get("metadata", {}).get("last_capture:" + c, "")
                        for c in r.channels
                    ),
                    default="",
                ),
                "last_recovered": max(
                    (c["recovered_at"] or 0 for c in channels), default=0
                ),
                "last_delivered": max(
                    (d["sent_at"] or 0 for d in deliveries), default=0
                ),
                "lag_seconds": max(
                    0, time.time() - datetime.fromisoformat(oldest).timestamp()
                )
                if oldest
                else 0,
            }
        )
    return {
        "healthy": healthy(state["health"]),
        "health": state["health"],
        "delivery_enabled": config.delivery_enabled,
        "rules": routes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m discordless")
    parser.add_argument("--config", default="config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-config")
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    sub.add_parser("health")
    recover = sub.add_parser("recover")
    recover.add_argument("--channel")
    recover.add_argument("--execute", action="store_true")
    recover.add_argument("--bootstrap", action="store_true")
    deliveries = sub.add_parser("deliveries")
    deliveries.add_argument(
        "--status",
        choices=["pending", "inflight", "sent", "retry", "blocked", "uncertain"],
    )
    deliveries.add_argument("--id", type=int)
    deliveries.add_argument("--action", choices=["retry", "confirm"])
    deliveries.add_argument("--destination-id")
    deliveries.add_argument("--execute", action="store_true")
    sub.add_parser("backup", add_help=False)
    args, extra = parser.parse_known_args(argv)
    try:
        if args.command == "backup":
            from discordless.backup import main as backup_main

            return backup_main(["--config", args.config] + extra)
        if extra:
            parser.error("Unexpected arguments")
        config = load_config(args.config)
        if args.command == "check-config":
            print(
                json.dumps(
                    {
                        "valid": True,
                        "rules": len(config.forwards),
                        "account": config.user_id,
                    }
                )
            )
            return 0
        if args.command in ("status", "health"):
            report = state_report(config)
            if args.command == "health":
                return 0 if report["healthy"] else 2
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
                return 0
            zone = ZoneInfo("Europe/Paris")

            def date(value):
                return (
                    datetime.fromtimestamp(value, zone).strftime("%d/%m/%Y %H:%M:%S")
                    if value
                    else "-"
                )

            print(
                "Capture: "
                + ("OK" if report["healthy"] else "DEGRADED")
                + " | Compte: "
                + config.user_id
                + " | Envois: "
                + str(config.delivery_enabled)
            )
            for rule in report["rules"]:
                print(
                    rule["label"]
                    + " | "
                    + json.dumps(rule["counts"])
                    + " | dernier transfert: "
                    + date(rule["last_delivered"])
                    + " | récupération: "
                    + date(rule["last_recovered"])
                )
                for channel in rule["channels"]:
                    if channel["error"]:
                        print("  " + channel["channel"] + " : " + channel["error"])
            return 0
        if args.command == "recover":
            if args.execute:
                store = Store(config.state_path)
            elif Path(config.state_path).exists():
                # Read-only view has only checkpoint; dry-run must not create DB/schema/locks.
                checkpoints = {
                    c["channel"]: c["checkpoint"]
                    for c in inspect_state(config)["channels"]
                }

                class View:
                    def checkpoint(self, channel):
                        return checkpoints.get(channel)

                store = View()
            else:
                store = None
            result = Recovery(
                config, store, root=Path(args.config).resolve().parent
            ).run(args.channel, args.execute, args.bootstrap)
            print(json.dumps(result))
            return 2 if any(r["error"] for r in result) else 0
        if args.command == "deliveries":
            if args.action and (not args.id or not args.execute):
                parser.error("Resolution requires --id and --execute")
            if not args.action:
                if not Path(config.state_path).exists():
                    print("[]")
                    return 0
                connection = sqlite3.connect(
                    Path(config.state_path).resolve().as_uri() + "?mode=ro", uri=True
                )
                connection.row_factory = sqlite3.Row
                try:
                    query = "SELECT id,rule,channel,source_id,part,status,attempts,error,destination_id FROM deliveries"
                    params = []
                    if args.status:
                        query += " WHERE status=?"
                        params = [args.status]
                    print(
                        json.dumps(
                            [
                                dict(r)
                                for r in connection.execute(
                                    query + " ORDER BY id", params
                                )
                            ]
                        )
                    )
                finally:
                    connection.close()
                return 0
            store = Store(config.state_path)
            row = store.rows("id=?", (args.id,))
            if not row or row[0]["status"] not in ("blocked", "uncertain"):
                raise ValueError("Only blocked/uncertain deliveries can be resolved")
            row = row[0]
            if args.action == "retry":
                store.update(args.id, status="retry", due=0, error=None)
            else:
                if not args.destination_id:
                    raise ValueError("Confirmation requires destination ID")
                rule = next(r for r in config.forwards if r.rule_id == row["rule"])
                candidate = DiscordAPI(config).read_message(
                    rule.destination, args.destination_id
                )
                if not candidate or not matches(
                    json.loads(row["payload"]), candidate, rule.native
                ):
                    raise ValueError("Destination message does not match")
                store.update(
                    args.id,
                    status="sent",
                    destination_id=args.destination_id,
                    sent_at=datetime.fromisoformat(candidate["timestamp"]).timestamp(),
                    error=None,
                )
            print(json.dumps({"id": args.id, "action": args.action}))
            return 0
    except (ConfigError, APIError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception as error:
        print("Operation failed: " + type(error).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
