import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    sys.platform != "linux", reason="Production supervisor is Linux/systemd"
)
@pytest.mark.parametrize("failure", ["discord", "proxy", "health"])
def test_supervisor_exits_when_either_process_or_gateway_fails(tmp_path, failure):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    (tmp_path / "config.json").write_text(
        json.dumps({"proxy_port": port, "forwards": []})
    )
    proxy = tmp_path / "proxy"
    proxy.write_text(
        f'#!{sys.executable}\nimport socket,time\ns=socket.socket();s.bind(("127.0.0.1",{port}));s.listen()\ntime.sleep({1 if failure == "proxy" else 60})\n'
    )
    discord = tmp_path / "discord"
    discord.write_text(
        f"#!{sys.executable}\nimport time\ntime.sleep({0.1 if failure == 'discord' else 60})\n"
    )
    proxy.chmod(0o700)
    discord.chmod(0o700)
    project = Path(__file__).resolve().parents[2]
    env = dict(
        os.environ,
        WIRECORD_DIR=str(tmp_path),
        WIRECORD_PYTHON=sys.executable,
        WIRECORD_MITM=str(proxy),
        WIRECORD_DISCORD=str(discord),
        WIRECORD_STARTUP_GRACE="0" if failure == "health" else "2",
        PYTHONPATH=str(project),
    )
    child = subprocess.Popen(
        ["bash", str(project / "vps-deployment/wirecord-run")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = child.communicate(timeout=12)
        assert child.returncode == 1, (stdout, stderr)
        assert b"managed process exited" in stdout
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
