"""Subprocess-based test: launches the MCP server, sends a JSONRPC
tools/list request, verifies response. Lightweight — does not cover full surface
(that's `test_mcp_smoke.py`). This test exists to prove the server actually starts
and the registry is reachable over stdio."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_mcp_server_starts_and_lists_tools(tmp_path):
    env = os.environ.copy()
    repo_root = Path(__file__).parent.parent.parent
    env["PYTHONPATH"] = str(repo_root / "src")
    env["ASSET_FINANCE_DB_PATH"] = str(tmp_path / "stdio.db")

    proc = subprocess.Popen(
        [sys.executable, "-m", "asset_finance_modeler.mcp_server.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )

    try:
        # Initialize
        initialize_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }) + "\n"
        proc.stdin.write(initialize_req)
        proc.stdin.flush()
        init_resp_line = proc.stdout.readline()
        init_resp = json.loads(init_resp_line)
        assert init_resp.get("id") == 1
        assert "result" in init_resp

        # Send initialized notification
        notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        proc.stdin.write(notif)
        proc.stdin.flush()

        # tools/list
        tools_req = json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        }) + "\n"
        proc.stdin.write(tools_req)
        proc.stdin.flush()
        tools_resp_line = proc.stdout.readline()
        tools_resp = json.loads(tools_resp_line)
        assert tools_resp.get("id") == 2
        tools = tools_resp["result"]["tools"]
        names = {t["name"] for t in tools}
        # Must contain at least these:
        assert "finance.simulate.list_models" in names
        assert "finance.simulate.run" in names
        assert "finance.simulate.compare" in names
        assert "finance.track.import_real_data" in names

    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
