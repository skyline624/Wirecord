"""Verified, bounded snapshots of Wirecord's append-only archive and SQLite state."""

from __future__ import annotations

import argparse
from contextlib import closing
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile
import time


class BackupError(Exception):
    pass


def _complete_lines(path: Path) -> bytes:
    data = path.read_bytes()
    return data[: data.rfind(b"\n") + 1]


def _safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return (
        bool(name)
        and not p.is_absolute()
        and ".." not in p.parts
        and "\\" not in name
        and ":" not in name
    )


def verify_backup(path: Path) -> dict:
    """Validate every byte without extracting files or trusting archive paths."""
    observed = {}
    manifest = None
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if (
                not member.isfile()
                or not _safe_name(member.name)
                or member.name in observed
            ):
                raise BackupError("Invalid or duplicate archive member")
            stream = archive.extractfile(member)
            if member.name == "manifest.json":
                if manifest is not None or member.size > 32 * 1024 * 1024:
                    raise BackupError("Invalid manifest")
                manifest = json.load(stream)
                continue
            digest = hashlib.sha256()
            size = 0
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            observed[member.name] = {"sha256": digest.hexdigest(), "size": size}
    if manifest is None or manifest.get("files") != observed:
        raise BackupError("Backup checksum or file list mismatch")
    return manifest


def restore_backup(path: Path, destination: Path) -> dict:
    manifest = verify_backup(path)
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise BackupError("Restore directory must be empty")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            target = destination / member.name
            if not target.resolve().is_relative_to(destination):
                raise BackupError("Unsafe restore path")
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open("xb") as out:
                shutil.copyfileobj(archive.extractfile(member), out)
            target.chmod(0o600)
    return manifest


def _retention(directory: Path) -> None:
    """Keep latest snapshot on each of 7 days and each of 4 ISO weeks."""
    groups = []
    for p in sorted(
        directory.glob("wirecord-????????T??????*-utc.tar.gz"), reverse=True
    ):
        try:
            stamp = dt.datetime.strptime(p.name[9:24], "%Y%m%dT%H%M%S")
        except ValueError:
            continue
        groups.append((p, stamp))
    daily, weekly, keep = set(), set(), set()
    for p, stamp in groups:
        day, week = stamp.date(), stamp.isocalendar()[:2]
        if day not in daily and len(daily) < 7:
            daily.add(day)
            keep.add(p)
        if week not in weekly and len(weekly) < 4:
            weekly.add(week)
            keep.add(p)
    for p, _ in groups:
        if p not in keep:
            if p.resolve().parent != directory.resolve() or p.is_symlink():
                raise BackupError("Unsafe retention path")
            p.unlink()


def create_backup(config_path: Path, output_dir: Path | None = None) -> Path:
    config_path = config_path.resolve()
    root = config_path.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))

    def resolve(value):
        p = Path(value)
        return p if p.is_absolute() else root / p

    archive_root = resolve(config.get("traffic_archive_dir", "traffic_archive"))
    state_path = resolve(config.get("state_path", "state/wirecord.sqlite3"))
    output_dir = (output_dir or resolve(config.get("backup_dir", "backups"))).resolve()
    if output_dir == archive_root.resolve() or output_dir.is_relative_to(
        archive_root.resolve()
    ):
        raise BackupError("Backup directory must be outside the traffic archive")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if shutil.disk_usage(output_dir).free < 128 * 1024 * 1024:
        raise BackupError("Insufficient free disk space")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = (
        output_dir / f"wirecord-{stamp}-{time.time_ns() % 1000000000:09d}-utc.tar.gz"
    )
    temporary = target.with_suffix(".part")
    files = {}
    manifest = {
        "format_version": 1,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": files,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="wirecord-backup-") as scratch:
            database = Path(scratch) / "wirecord.sqlite3"
            if state_path.exists():
                # State is sampled before the archive: every committed delivery must
                # already have an archived source; extra later archive records are fine.
                with closing(
                    sqlite3.connect(
                        state_path.resolve().as_uri() + "?mode=ro", uri=True
                    )
                ) as source:
                    with closing(sqlite3.connect(database)) as dest:
                        source.backup(dest)
                        if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise BackupError("Invalid SQLite backup")
            indices = {
                name: _complete_lines(archive_root / name)
                for name in ("request_index", "gateway_index")
                if (archive_root / name).exists()
            }
            with temporary.open("xb") as raw:
                temporary.chmod(0o600)
                with tarfile.open(fileobj=raw, mode="w:gz") as tar:

                    def add(name, path=None, data=None, length=None):
                        if not _safe_name(name) or name in files:
                            raise BackupError("Invalid snapshot member")
                        if data is not None:
                            stream = io.BytesIO(data)
                            size = len(data)
                        else:
                            if path.is_symlink():
                                raise BackupError("Unexpected source symlink")
                            stream = path.open("rb")
                            size = path.stat().st_size if length is None else length
                        digest = hashlib.sha256()

                        class Reader:
                            def read(self, amount=-1):
                                chunk = stream.read(amount)
                                digest.update(chunk)
                                return chunk

                        info = tarfile.TarInfo(name)
                        info.size = size
                        info.mode = 0o600
                        try:
                            tar.addfile(info, Reader())
                        finally:
                            stream.close()
                        files[name] = {"sha256": digest.hexdigest(), "size": size}

                    add("config.json", path=config_path)
                    if database.exists():
                        add("state/wirecord.sqlite3", path=database)
                    for name, data in indices.items():
                        add("traffic_archive/" + name, data=data)
                    # Copy only immutable responses referenced by the sampled index.
                    names = set()
                    for row in indices.get("request_index", b"").decode().splitlines():
                        fields = row.split(maxsplit=4)
                        if (
                            len(fields) != 5
                            or not _safe_name(fields[4])
                            or "/" in fields[4]
                        ):
                            raise BackupError("Malformed request index")
                        names.add(fields[4])
                    for name in sorted(names):
                        add(
                            "traffic_archive/requests/" + name,
                            path=archive_root / "requests" / name,
                        )
                    gateways = {
                        row.split()[-1]
                        for row in indices.get("gateway_index", b"")
                        .decode()
                        .splitlines()
                    }
                    for gateway in sorted(gateways):
                        if not gateway.isdigit():
                            raise BackupError("Malformed gateway index")
                        data_path = archive_root / "gateways" / (gateway + "_data")
                        timeline_path = (
                            archive_root / "gateways" / (gateway + "_timeline")
                        )
                        timeline = _complete_lines(timeline_path)
                        available = data_path.stat().st_size
                        retained, length = [], 0
                        for row in timeline.splitlines(keepends=True):
                            fields = row.split()
                            if len(fields) != 2:
                                raise BackupError("Malformed gateway timeline")
                            size = int(fields[1])
                            if size < 0:
                                raise BackupError("Invalid gateway length")
                            if length + size > available:
                                break
                            retained.append(row)
                            length += size
                        add(
                            "traffic_archive/gateways/" + gateway + "_data",
                            path=data_path,
                            length=length,
                        )
                        add(
                            "traffic_archive/gateways/" + gateway + "_timeline",
                            data=b"".join(retained),
                        )
                    # Include the actual code needed to interpret this data, not venv/logs.
                    for folder in (
                        "discordless",
                        "exporters",
                        "vps-deployment",
                        "scripts",
                    ):
                        for path in sorted((root / folder).rglob("*")):
                            if (
                                path.is_file()
                                and "__pycache__" not in path.parts
                                and not path.name.startswith(".")
                                and not path.name.endswith(".legacy")
                            ):
                                add(
                                    "project/" + path.relative_to(root).as_posix(),
                                    path=path,
                                )
                    for filename in (
                        "pyproject.toml",
                        "requirements.txt",
                        "exporter.py",
                    ):
                        path = root / filename
                        if path.exists():
                            add("project/" + filename, path=path)
                    for location in (
                        "/usr/local/bin/wirecord-run",
                        "/etc/systemd/system/wirecord.service",
                        "/etc/systemd/system/wirecord-backup.service",
                        "/etc/systemd/system/wirecord-backup.timer",
                        "/etc/systemd/system/wirecord-logrotate.service",
                        "/etc/systemd/system/wirecord-logrotate.timer",
                        "/etc/logrotate.d/wirecord",
                    ):
                        path = Path(location)
                        if os.name != "nt" and path.is_file():
                            add("system/" + location.lstrip("/"), path=path)
                    data = json.dumps(manifest, sort_keys=True).encode()
                    info = tarfile.TarInfo("manifest.json")
                    info.size = len(data)
                    info.mode = 0o600
                    tar.addfile(info, io.BytesIO(data))
                raw.flush()
                os.fsync(raw.fileno())
            verify_backup(temporary)
            temporary.replace(target)
        _retention(output_dir)
        return target
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create or verify a Wirecord backup")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument(
        "--restore", type=Path, help="Empty restore directory; requires --verify"
    )
    args = parser.parse_args(argv)
    try:
        if args.restore and not args.verify:
            parser.error("--restore requires --verify")
        if args.verify:
            manifest = (
                restore_backup(args.verify, args.restore)
                if args.restore
                else verify_backup(args.verify)
            )
            print(
                json.dumps(
                    {
                        "verified_files": len(manifest["files"]),
                        "restored": bool(args.restore),
                    }
                )
            )
        else:
            path = create_backup(Path(args.config), args.output_dir)
            print(json.dumps({"backup": str(path)}))
        return 0
    except Exception as error:
        # Exceptions from JSON, SQLite and archive paths must not expose config content.
        print("Backup failed: " + type(error).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
