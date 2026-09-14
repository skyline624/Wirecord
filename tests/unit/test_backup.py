import datetime as dt
import io
import json
import sqlite3
import tarfile

import pytest

from discordless.backup import (
    BackupError,
    _retention,
    create_backup,
    restore_backup,
    verify_backup,
)


def project(tmp_path):
    root = tmp_path / "project"
    archive = root / "traffic_archive"
    (archive / "requests").mkdir(parents=True)
    (archive / "gateways").mkdir()
    (archive / "requests" / "sample").write_bytes(b'{"id":"123"}')
    (archive / "request_index").write_text(
        "1 GET https://discord.com/api/v9/channels/1/messages oldhash sample\n"
    )
    (archive / "gateway_index").write_text("1 wss://gateway.discord.gg 1\n")
    (archive / "gateways/1_data").write_bytes(b"abcdefUNFLUSHED")
    (archive / "gateways/1_timeline").write_bytes(b"1 3\n2 3\n3 200\n4")
    (root / "state").mkdir()
    with sqlite3.connect(root / "state/wirecord.sqlite3") as db:
        db.execute("create table test(id integer primary key, status text)")
        db.execute("insert into test values(1,'pending')")
    config = root / "config.json"
    config.write_text(json.dumps({"state_path": "state/wirecord.sqlite3"}))
    return config


def test_snapshot_restore_preserves_database_and_valid_gateway_prefix(tmp_path):
    config = project(tmp_path)
    path = create_backup(config)
    manifest = verify_backup(path)
    assert "state/wirecord.sqlite3" in manifest["files"]
    restored = tmp_path / "restore"
    restore_backup(path, restored)
    assert (restored / "traffic_archive/gateways/1_data").read_bytes() == b"abcdef"
    assert (
        restored / "traffic_archive/gateways/1_timeline"
    ).read_bytes() == b"1 3\n2 3\n"
    with sqlite3.connect(restored / "state/wirecord.sqlite3") as db:
        assert db.execute("select status from test").fetchone()[0] == "pending"
    with pytest.raises(BackupError):
        restore_backup(path, restored)


def test_bad_checksum_and_traversal_are_rejected(tmp_path):
    for member_name in ("../escaped", "valid"):
        path = tmp_path / "bad.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            data = b"bad"
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            manifest = b'{"files":{}}'
            info = tarfile.TarInfo("manifest.json")
            info.size = len(manifest)
            tar.addfile(info, io.BytesIO(manifest))
        with pytest.raises(BackupError):
            verify_backup(path)
    assert not (tmp_path.parent / "escaped").exists()


def test_backup_failure_keeps_existing_snapshots(tmp_path):
    config = project(tmp_path)
    good = create_backup(config)
    (config.parent / "traffic_archive/requests/sample").unlink()
    with pytest.raises(FileNotFoundError):
        create_backup(config)
    assert good.exists()
    assert not list(good.parent.glob("*.part"))


def test_retention_keeps_seven_distinct_days_and_four_weeks(tmp_path):
    latest = dt.datetime(2026, 9, 14, 4)
    for days in range(50):
        date = latest - dt.timedelta(days=days)
        for duplicate in range(2):
            (
                tmp_path / f"wirecord-{date:%Y%m%dT%H%M%S}-{duplicate:09d}-utc.tar.gz"
            ).write_bytes(b"x")
    _retention(tmp_path)
    retained = sorted(tmp_path.glob("*.tar.gz"), reverse=True)
    dates = [dt.datetime.strptime(p.name[9:24], "%Y%m%dT%H%M%S") for p in retained]
    assert len(dates) == len(set(dates))
    assert all(latest - dt.timedelta(days=days) in dates for days in range(7))
    assert len({d.isocalendar()[:2] for d in dates}) == 4


def test_backup_output_cannot_be_inside_archive(tmp_path):
    config = project(tmp_path)
    with pytest.raises(BackupError):
        create_backup(config, config.parent / "traffic_archive/backups")
