"""Configured sender pools in the durable runtime; every HTTP call is simulated."""
import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from discordless.config import ACCOUNT_ID, Config, ConfigError, ForwardRule
from discordless.health import GatewayHealth, healthy
from discordless.runtime import deliver_one, reconcile_uncertain
from discordless.store import Store
from discordless.transport import APIError, DiscordAPI, matches, payloads

SECOND = "239408830583275520"
OTHER = "123456789012345678"


def token(uid):
    return base64.urlsafe_b64encode(uid.encode()).decode() + ".fake.signature"


def response(status, data=None):
    return SimpleNamespace(status_code=status, json=lambda: data or {})


@pytest.fixture
def native(tmp_path, monkeypatch):
    rule = ForwardRule(channels=["1"], dest_channel_id="2", forward_mode="native",
                       user_ids=[ACCOUNT_ID, SECOND], rule_id="pool", rate_limit_delay=1)
    config = Config(forwards=[rule], state_path=str(tmp_path / "journal.sqlite3"))
    api = DiscordAPI(config)
    calls = []
    monkeypatch.setattr("discordless.transport._collect_tokens",
                        lambda: [token(OTHER), token(SECOND), token(ACCOUNT_ID)])

    def get(session, url, **kwargs):
        uid = base64.urlsafe_b64decode(session.headers["Authorization"].split(".")[0] + "===").decode()
        assert uid in (ACCOUNT_ID, SECOND)
        calls.append(("GET", uid, url))
        return response(200, {"id": uid})

    def post(session, url, **kwargs):
        uid = base64.urlsafe_b64decode(session.headers["Authorization"].split(".")[0] + "===").decode()
        calls.append(("POST", uid, url))
        return response(200, {"id": "77", "channel_id": "2", "author": {"id": uid}})

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "post", post)
    return config, rule, api, calls


def test_config_restores_both_rule_accounts_and_allows_secondary_reader(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"user_id": SECOND, "forward_mode": "native", "forwards": [
        {"channels": ["1"], "dest_channel_id": "2", "user_ids": [ACCOUNT_ID, SECOND]}
    ]}))
    cfg = Config.load(path)
    assert cfg.user_id == SECOND
    assert cfg.forwards[0].poster_ids() == [ACCOUNT_ID, SECOND]
    assert cfg.account_ids == frozenset((ACCOUNT_ID, SECOND))


@pytest.mark.parametrize("value", ["garbage", "123", "../../path"])
def test_malformed_account_ids_are_still_refused(tmp_path, value):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"forward_mode": "native", "forwards": [
        {"channels": ["1"], "dest_channel_id": "2", "user_ids": [value]}
    ]}))
    with pytest.raises(ConfigError):
        Config.load(path)


def test_each_send_draws_from_its_pool_and_keeps_credentials_separate(native, monkeypatch):
    cfg, rule, api, calls = native
    draws = iter([SECOND, ACCOUNT_ID, SECOND, SECOND])
    pools = []

    def choose(pool):
        pools.append(list(pool))
        chosen = next(draws)
        assert chosen in pool
        return chosen

    monkeypatch.setattr("discordless.transport.random.choice", choose)
    for _ in range(4):
        assert api.send(rule, {}).status_code == 200
    assert [uid for method, uid, _ in calls if method == "POST"] == [SECOND, ACCOUNT_ID, SECOND, SECOND]
    assert pools == [[ACCOUNT_ID, SECOND]] * 4
    assert api.session.headers["Authorization"] == token(ACCOUNT_ID)
    assert api._sessions[SECOND].headers["Authorization"] == token(SECOND)
    assert [uid for method, uid, _ in calls if method == "GET"] == [SECOND, ACCOUNT_ID]


def test_another_rules_accounts_are_not_used_as_fallback(native, monkeypatch):
    cfg, rule, api, calls = native
    rule.user_ids = [SECOND]
    monkeypatch.setattr("discordless.transport.random.choice", lambda pool: pool[0])
    api.send(rule, {})
    assert {uid for _, uid, _ in calls} == {SECOND}


def test_unconfigured_store_account_is_never_authenticated(native):
    cfg, rule, api, calls = native
    with pytest.raises(APIError):
        api.authenticate(OTHER)
    assert calls == []


def test_invalid_account_does_not_disable_the_other_sender(native, monkeypatch):
    cfg, rule, api, calls = native
    monkeypatch.setattr("discordless.transport.random.choice", lambda pool: pool[0])
    original = requests.Session.post

    def rejected(session, url, **kwargs):
        if session.headers["Authorization"] == token(ACCOUNT_ID):
            calls.append(("REJECTED", ACCOUNT_ID, url))
            return response(401)
        return original(session, url, **kwargs)

    monkeypatch.setattr(requests.Session, "post", rejected)
    assert api.send(rule, {}).status_code == 200
    assert api.send(rule, {}).status_code == 200
    assert api._disabled_accounts == {ACCOUNT_ID}
    assert [uid for method, uid, _ in calls if method == "POST"] == [SECOND, SECOND]
    assert sum(method == "REJECTED" for method, _, _ in calls) == 1


@pytest.mark.parametrize("outcome", [500, 429, "timeout"])
def test_ambiguous_or_rate_limited_post_is_never_repeated_with_another_account(native, monkeypatch, outcome):
    cfg, rule, api, calls = native
    monkeypatch.setattr("discordless.transport.random.choice", lambda pool: pool[0])
    posted = []

    def post(session, url, **kwargs):
        posted.append(session.headers["Authorization"])
        if outcome == "timeout":
            raise requests.ReadTimeout()
        return response(outcome)

    monkeypatch.setattr(requests.Session, "post", post)
    if outcome == "timeout":
        with pytest.raises(requests.ReadTimeout):
            api.send(rule, {})
    else:
        assert api.send(rule, {}).status_code == outcome
    assert posted == [token(ACCOUNT_ID)]


def test_destination_can_be_read_with_secondary_account_when_reader_lacks_access(native, monkeypatch):
    cfg, rule, api, calls = native
    original = requests.Session.get

    def get(session, url, **kwargs):
        if url.endswith("/users/@me"):
            return original(session, url, **kwargs)
        uid = ACCOUNT_ID if session.headers["Authorization"] == token(ACCOUNT_ID) else SECOND
        calls.append(("HISTORY", uid, url))
        return response(403) if uid == ACCOUNT_ID else response(200, [{"id": "77"}])

    monkeypatch.setattr(requests.Session, "get", get)
    assert api.read_message("2", "77", account_ids=rule.user_ids) == {"id": "77"}
    assert [uid for method, uid, _ in calls if method == "HISTORY"] == [ACCOUNT_ID, SECOND]


@pytest.mark.parametrize("uid", [ACCOUNT_ID, SECOND])
def test_gateway_accepts_each_configured_capture_account(uid):
    health = GatewayHealth([ACCOUNT_ID, SECOND])
    health.observe("1", {"op": 10, "d": {"heartbeat_interval": 45000}})
    health.observe("1", {"t": "READY", "d": {"user": {"id": uid}}})
    health.observe("1", {"op": 11})
    now = health.state["updated_at"]
    health.state["started_at"] = now - 140
    assert healthy(health.state, now)
    health.observe("1", {"t": "READY", "d": {"user": {"id": OTHER}}})
    assert not healthy(health.state)


@pytest.mark.parametrize("author,expected", [(ACCOUNT_ID, True), (SECOND, True), (OTHER, False)])
def test_native_confirmation_requires_an_author_in_the_rule_pool(author, expected):
    payload = {"message_reference": {"type": 1, "message_id": "50"}}
    candidate = {"message_reference": payload["message_reference"], "author": {"id": author}}
    assert matches(payload, candidate, native=True, account_ids=[ACCOUNT_ID, SECOND]) is expected
    assert not matches(payload, candidate, native=True, account_ids=[])


def test_uncertain_secondary_transfer_is_confirmed_without_resending(native):
    cfg, rule, api, calls = native
    store = Store(cfg.state_path)
    raw = {"id": "50", "channel_id": "1", "timestamp": "2026-10-01T12:00:00+00:00", "content": "test"}
    store.enqueue(rule, raw, payloads(rule, raw))
    row = store.rows()[0]
    store.update(row["id"], status="uncertain", attempted_at=100)
    candidate = {"id": "77", "timestamp": "2026-10-01T12:01:00+00:00", "author": {"id": SECOND},
                 "message_reference": {"type": 1, "message_id": "50"}}
    api.history = Mock(return_value=[candidate])
    reconcile_uncertain(store, {rule.rule_id: rule}, api)
    assert store.rows()[0]["status"] == "sent"
    assert store.rows()[0]["destination_id"] == "77"
    assert calls == []
    assert api.history.call_args.kwargs["account_ids"] == [ACCOUNT_ID, SECOND]


def test_temporary_authentication_failure_retries_the_durable_delivery(native):
    cfg, rule, api, calls = native
    store = Store(cfg.state_path)
    raw = {"id": "50", "channel_id": "1", "timestamp": "2026-10-01T12:00:00+00:00", "content": "test"}
    store.enqueue(rule, raw, payloads(rule, raw))
    api.send = Mock(side_effect=APIError(0))
    deliver_one(store, rule, store.rows()[0], api)
    assert store.rows()[0]["status"] == "retry"
    assert store.rows()[0]["error"] == "auth_0"


def test_cli_confirmation_accepts_secondary_account_proof_within_the_rule_pool(native, monkeypatch):
    from discordless.__main__ import main
    from pathlib import Path

    cfg, rule, api, calls = native
    store = Store(cfg.state_path)
    raw = {"id": "50", "channel_id": "1", "timestamp": "2026-10-01T12:00:00+00:00", "content": "test"}
    store.enqueue(rule, raw, payloads(rule, raw))
    row = store.rows()[0]
    store.update(row["id"], status="uncertain")
    path = Path(cfg.state_path).parent / "config.json"
    path.write_text(json.dumps({"state_path": cfg.state_path, "forwards": [
        {"channels": ["1"], "dest_channel_id": "2", "forward_mode": "native", "rule_id": "pool",
         "user_ids": [ACCOUNT_ID, SECOND]}
    ]}))

    def proof(self, channel, mid, account_ids=None):
        assert account_ids == [ACCOUNT_ID, SECOND]
        return {"id": mid, "timestamp": "2026-10-01T12:01:00+00:00", "author": {"id": SECOND},
                "message_reference": {"type": 1, "message_id": "50"}}

    monkeypatch.setattr(DiscordAPI, "read_message", proof)
    assert main(["--config", str(path), "deliveries", "--id", str(row["id"]), "--action", "confirm",
                 "--destination-id", "77", "--execute"]) == 0
    assert store.rows()[0]["status"] == "sent"
    assert calls == []
