import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from discordless.archive import ArchiveWriter
from discordless.config import ACCOUNT_ID, Config, ConfigError, ForwardRule
from discordless.health import GatewayHealth, healthy
from discordless.recovery import Recovery
from discordless.runtime import deliver_one, reconcile_uncertain
from discordless.store import FileLock, Store
from discordless.transport import APIError, DiscordAPI, payloads


@pytest.fixture
def setup(tmp_path):
    rule = ForwardRule(
        channels=["1"],
        webhook_url="https://discord.com/api/webhooks/123/secret",
        webhook_channel_id="2",
        rule_id="r",
        rate_limit_delay=0,
    )
    cfg = Config(
        forwards=[rule],
        state_path=str(tmp_path / "state.sqlite3"),
        traffic_archive_dir=str(tmp_path / "archive"),
    )
    store = Store(cfg.state_path)
    store.hold("1", False)
    return cfg, rule, store


def message(mid="1549031002868031569", **kwargs):
    return dict(
        id=mid,
        channel_id="1",
        timestamp="2026-09-14T12:00:00+00:00",
        author={"id": "7", "username": "somebody"},
        content="hello",
        **kwargs,
    )


def claim(store, rule, now=100):
    store.claim({rule.rule_id: rule}, now)
    return store.claim({rule.rule_id: rule}, now + 10)


def test_durable_queue_dedup_restart_and_uncertain_blocks_later(setup):
    cfg, rule, store = setup
    m = message()
    store.enqueue(rule, m, payloads(rule, m))
    store.enqueue(rule, m, payloads(rule, m))
    assert len(store.rows()) == 1
    row = claim(store, rule)
    reopened = Store(store.path)
    reopened.resume()
    assert reopened.rows()[0]["status"] == "uncertain"
    newer = message(mid=str(int(m["id"]) + 1))
    reopened.enqueue(rule, newer, payloads(rule, newer))
    assert reopened.claim({"r": rule}, 1000) is None
    reopened.update(row["id"], status="sent", destination_id="99")
    assert claim(reopened, rule, 2000)["source_id"] == newer["id"]


def test_recovery_hold_and_same_destination_order(setup):
    cfg, rule, store = setup
    m = message()
    store.enqueue(rule, m, payloads(rule, m))
    store.hold("1", True)
    assert claim(store, rule) is None
    store.hold("1", False)
    assert claim(store, rule)


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, "retry"),
        (401, "blocked"),
        (403, "blocked"),
        (404, "blocked"),
        (500, "uncertain"),
    ],
)
def test_http_delivery_outcomes(setup, status, expected):
    cfg, rule, store = setup
    m = message()
    store.enqueue(rule, m, payloads(rule, m))
    row = claim(store, rule)
    api = Mock()
    api.send.return_value = SimpleNamespace(
        status_code=status, json=lambda: {"retry_after": 1}
    )
    deliver_one(store, rule, row, api)
    assert store.rows()[0]["status"] == expected


def test_long_message_partial_failure_does_not_repeat_first_chunk(setup):
    cfg, rule, store = setup
    m = message()
    m["content"] = "a" * 3000
    store.enqueue(rule, m, payloads(rule, m))
    row = claim(store, rule)
    api = Mock()
    api.send.return_value = SimpleNamespace(
        status_code=200, json=lambda: {"id": "88", "channel_id": "2"}
    )
    deliver_one(store, rule, row, api)
    row = claim(store, rule, 200)
    assert row["part"] == 1
    api.send.side_effect = requests.ReadTimeout("url with secret")
    deliver_one(store, rule, row, api)
    assert [r["status"] for r in store.rows()] == ["sent", "uncertain"]
    assert all("secret" not in (r["error"] or "") for r in store.rows())


def test_embed_only_and_attachments_preserved_mentions_disabled(setup):
    cfg, rule, store = setup
    m = message(
        embeds=[
            {
                "type": "rich",
                "title": "A",
                "description": "B",
                "content_scan_version": 1,
            }
        ]
    )
    m["content"] = ""
    p = payloads(rule, m)
    assert p[0]["embeds"] == [{"title": "A", "description": "B"}]
    assert p[0]["allowed_mentions"] == {"parse": []}
    m["embeds"] = []
    m["attachments"] = [{"url": "https://cdn.discordapp.com/file"}]
    assert payloads(rule, m)[0]["content"] == m["attachments"][0]["url"]
    rule.forward_mode = "native"
    assert payloads(rule, m)[0]["message_reference"]["message_id"] == m["id"]


def test_gateway_health_uses_acks_not_chat_traffic():
    h = GatewayHealth()
    h.state["started_at"] = 100
    h.state["updated_at"] = 250
    h.state.update(ready=True, account=ACCOUNT_ID, ack_at=245, interval=45)
    assert healthy(h.state, 250)
    assert not healthy(dict(h.state, updated_at=400), 400)
    assert not healthy(dict(h.state, error="account_mismatch"), 250)
    assert not healthy(
        h.state, 290
    )  # stale writer, even though ACK timeout not exceeded
    assert healthy({"started_at": 200, "updated_at": 250}, 250)


def test_uncertain_requires_unique_delivery_proof(setup):
    cfg, rule, store = setup
    m = message()
    store.enqueue(rule, m, payloads(rule, m))
    row = claim(store, rule)
    store.update(row["id"], status="uncertain")
    candidate = {
        "id": "55",
        "webhook_id": "123",
        "content": "hello",
        "timestamp": "2026-09-14T13:00:00+00:00",
    }
    api = Mock()
    api.history.return_value = [candidate, dict(candidate, id="56")]
    reconcile_uncertain(store, {"r": rule}, api)
    assert store.rows()[0]["status"] == "uncertain"
    api.history.return_value = [candidate]
    reconcile_uncertain(store, {"r": rule}, api)
    assert store.rows()[0]["destination_id"] == "55"


def test_recovery_archives_before_queue_and_repeats_without_duplicates(setup):
    cfg, rule, store = setup
    api = Mock()
    api.get.return_value = {"guild_id": "3", "name": "source"}
    api.history.return_value = [message()]
    writer = ArchiveWriter(cfg.traffic_archive_dir)
    recovery = Recovery(cfg, store, api, writer)
    result = recovery.run(execute=True)
    assert result[0]["error"] is None
    assert store.rows()[0]["status"] == "pending"
    assert (writer.root / "request_index").exists()
    checkpoint = store.checkpoint("1")
    recovery.run(execute=True)
    assert len(store.rows()) == 1 and int(store.checkpoint("1")) >= int(checkpoint)


def test_failed_recovery_keeps_checkpoint_and_other_channel_proceeds(setup):
    cfg, rule, store = setup
    cfg.forwards.append(
        ForwardRule(channels=["3"], webhook_channel_id="4", rule_id="s")
    )
    store.recovered("1", "123")
    api = Mock()
    api.get.side_effect = lambda endpoint: (
        (_ for _ in ()).throw(APIError(403)) if "/1" in endpoint else {"guild_id": "8"}
    )
    api.history.return_value = []
    result = Recovery(cfg, store, api).run(execute=True)
    assert result[0]["error"] == "http_403" and result[1]["error"] is None
    assert store.checkpoint("1") == "123" and store.checkpoint("3")


def test_bootstrap_imports_ten_proven_transfers_without_posting(setup, tmp_path):
    cfg, rule, store = setup
    folder = tmp_path / "recovery_20260914"
    folder.mkdir()
    messages = [message(mid=str(1549031002868031569 + i)) for i in range(10)]
    proof = {
        m["id"]: {
            "verified": True,
            "source_channel_id": "1",
            "destination_message_id": str(90 + i),
        }
        for i, m in enumerate(messages)
    }
    (folder / "forwarded_messages.json").write_text(json.dumps(proof))
    api = Mock()
    api.get.return_value = {"guild_id": "3"}
    api.history.side_effect = lambda channel, *args: messages if channel == "1" else []
    assert (
        Recovery(cfg, store, api, root=tmp_path).run(execute=True, bootstrap=True)[0][
            "error"
        ]
        is None
    )
    assert len(store.rows()) == 10 and all(r["status"] == "sent" for r in store.rows())
    api.send.assert_not_called()


def test_stable_response_hash_rebuilds_legacy_index(tmp_path):
    root = tmp_path / "archive"
    (root / "requests").mkdir(parents=True)
    (root / "requests/old").write_bytes(b"hello")
    (root / "request_index").write_text("1 GET https://discord.com/a 1234 old\n")
    writer = ArchiveWriter(root)
    writer.response("https://discord.com/a", b"hello")
    assert len((root / "request_index").read_text().splitlines()) == 1
    writer.response("https://discord.com/a", b"new")
    assert len((root / "request_index").read_text().splitlines()[-1].split()[3]) == 64


def test_authentication_never_queries_another_account(monkeypatch):
    wrong = base64.urlsafe_b64encode(b"123").decode() + ".bad.signature"
    right = base64.urlsafe_b64encode(ACCOUNT_ID.encode()).decode() + ".fake.signature"
    monkeypatch.setattr("discordless.transport._collect_tokens", lambda: [wrong, right])
    api = DiscordAPI(Config())
    api.session = Mock()
    api.session.get.return_value = SimpleNamespace(
        status_code=200, json=lambda: {"id": ACCOUNT_ID}
    )
    api.authenticate()
    assert api.session.get.call_count == 1
    assert api.session.headers.update.call_args[0][0]["Authorization"] == right


def test_config_error_redacts_secret(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"user_token": "sensitive-token"}))
    with pytest.raises(ConfigError) as exc:
        Config.load(p)
    assert "sensitive-token" not in str(exc.value)


def test_history_paginates_to_checkpoint_and_keeps_newest_boundary():
    api = DiscordAPI(Config())
    api.get = Mock(
        side_effect=[
            [{"id": str(i)} for i in range(250, 150, -1)],
            [{"id": str(i)} for i in range(150, 50, -1)],
        ]
    )
    result = list(api.history("1", "100", "300"))
    assert len(result) == 150
    assert min(int(m["id"]) for m in result) == 101
    assert api.get.call_args_list[1].args[1]["before"] == "151"


def test_recovery_failure_mid_pagination_does_not_advance(setup):
    cfg, rule, store = setup
    store.recovered("1", "123")
    api = Mock()
    api.get.return_value = {"name": "source"}

    def partial(*args):
        yield message()
        raise APIError(500)

    api.history.side_effect = partial
    result = Recovery(cfg, store, api).run(execute=True)
    assert result[0]["error"] == "http_500"
    assert store.checkpoint("1") == "123" and store.rows() == []


def test_recovery_dryrun_does_not_create_archive_or_state(setup, tmp_path):
    cfg, rule, store = setup
    api = Mock()
    api.get.return_value = {"name": "source"}
    api.history.return_value = [message()]
    Recovery(cfg, None, api).run()
    assert not __import__("pathlib").Path(cfg.traffic_archive_dir).exists()
    api.send.assert_not_called()


def test_cli_readonly_and_confirmation_requires_matching_destination(
    setup, tmp_path, monkeypatch, capsys
):
    from discordless.__main__ import main

    cfg, rule, store = setup
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "state_path": cfg.state_path,
                "forwards": [
                    {
                        "channels": ["1"],
                        "webhook_url": rule.webhook_url,
                        "webhook_channel_id": "2",
                        "rule_id": "r",
                    }
                ],
            }
        )
    )
    assert main(["--config", str(path), "status", "--json"]) == 0
    m = message()
    store.enqueue(rule, m, payloads(rule, m))
    row = claim(store, rule)
    store.update(row["id"], status="uncertain")
    monkeypatch.setattr(
        DiscordAPI,
        "read_message",
        lambda *args: {"id": "55", "webhook_id": "123", "content": "WRONG"},
    )
    assert (
        main(
            [
                "--config",
                str(path),
                "deliveries",
                "--id",
                str(row["id"]),
                "--action",
                "confirm",
                "--destination-id",
                "55",
                "--execute",
            ]
        )
        == 2
    )
    assert store.rows()[0]["status"] == "uncertain"
    output = capsys.readouterr()
    assert "secret" not in output.out + output.err


def test_process_lock_rejects_second_runtime_owner(tmp_path):
    path = tmp_path / "runtime.lock"
    with FileLock(path):
        with pytest.raises(RuntimeError):
            with FileLock(path):
                pass


def test_empty_recovery_does_not_skip_temporarily_invisible_messages(setup):
    cfg, rule, store = setup
    store.recovered("1", "123")
    api = Mock()
    api.get.return_value = {"name": "source"}
    api.history.return_value = []
    Recovery(cfg, store, api).run(execute=True)
    assert store.checkpoint("1") == "123"
