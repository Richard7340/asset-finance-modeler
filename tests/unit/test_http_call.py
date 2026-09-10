"""POST /call nunca tumba con 500 por la forma del resultado.

Regresion: los handlers async (puente VDR) devolvian el repr de la corrutina
y los que devuelven lista rompian la validacion dict -> 500 en HTTP
(mientras por stdio iban bien envueltos en TextContent)."""
import os

os.environ["SIM_ONLY"] = "1"

from fastapi.testclient import TestClient

from asset_finance_modeler.mcp_server import http_server
from asset_finance_modeler.mcp_server.registry import ToolSpec


async def _async_list_handler(_args: dict) -> list:
    return [{"type": "text", "text": "hola"}]


def _sync_error_handler(_args: dict) -> dict:
    return {"error": "boom", "tool": "t.sync_err"}


http_server._registry["t.async_list"] = ToolSpec(
    name="t.async_list", description="fake", input_schema={}, handler=_async_list_handler,
)
http_server._registry["t.sync_err"] = ToolSpec(
    name="t.sync_err", description="fake", input_schema={}, handler=_sync_error_handler,
)


def test_call_async_list_handler_no_500():
    with TestClient(http_server.app, raise_server_exceptions=False) as c:
        r = c.post("/call", json={"name": "t.async_list", "arguments": {}})
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert body["result"] == [{"type": "text", "text": "hola"}]


def test_call_dict_error_passthrough():
    with TestClient(http_server.app, raise_server_exceptions=False) as c:
        r = c.post("/call", json={"name": "t.sync_err", "arguments": {}})
        assert r.status_code == 200
        assert r.json()["error"] == "boom"


def test_call_unknown_tool_404():
    with TestClient(http_server.app, raise_server_exceptions=False) as c:
        r = c.post("/call", json={"name": "nope.unknown", "arguments": {}})
        assert r.status_code == 404
