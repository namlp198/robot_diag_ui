from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from rdt.cli import load_targets  # noqa: E402
from rdt.daemon import Hub, create_app  # noqa: E402
from rdt.recorder import Recorder  # noqa: E402
from rdt.symbols import Resolved  # noqa: E402

ROOT = Path(__file__).parents[1]


@pytest.fixture
def client(tmp_path):
    hub = Hub(sessions_dir=tmp_path)
    with TestClient(create_app(hub), base_url="http://127.0.0.1:8765") as c:
        yield c


def test_status_idle(client):
    j = client.get("/api/status").json()
    assert j["running"] is False and set(j["targets"]) >= {"robot", "remote"}
    assert j["targets"]["robot"]["has_vcp"] is False


def test_rejects_foreign_host_and_origin(client):
    assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_robot_vcp_refused(client):
    r = client.post("/api/watch", json={"watches": {}, "vcp": ["robot"]})
    assert r.status_code == 400 and "log_port" in r.json()["detail"]


def test_unknown_target_and_bad_label(client):
    assert client.post("/api/watch", json={"watches": {"nope": ["x"]}}).status_code == 400
    assert client.post("/api/record/start", json={"label": "../x"}).status_code == 422


def test_sessions_listing_and_traversal(client, tmp_path):
    v = Resolved("a", 0x20000000, 4, "uint", "uint32_t")
    with Recorder(tmp_path, {"robot": {"serial": "S", "elf": "x", "paths": ["a"], "vars": [v]}}) as r:
        r.add_sample("robot", 0.0, [7])
    name = r.dir.name
    assert client.get("/api/sessions").json() == [name]
    j = client.get(f"/api/sessions/{name}", params={"target": "robot"}).json()
    assert j["columns"] == ["t_s", "a"] and j["rows"] == [[0.0, 7]]
    r = client.get("/api/sessions/..%2f..")  # may fall through to the static UI (200 HTML) but never to a session
    assert r.status_code == 404 or "application/json" not in r.headers.get("content-type", "")
    assert client.get("/api/sessions/nope").status_code == 404


def test_symbols_search(client):
    elf = (ROOT / load_targets()["robot"]["elf"]).resolve()
    if not elf.exists():
        pytest.skip("robot ELF not built")
    j = client.get("/api/symbols", params={"target": "robot", "q": "s_lora_rx"}).json()
    assert any(x["path"] == "s_lora_rx" and x["size"] > 0 for x in j)
    r = client.get("/api/resolve", params={"target": "robot", "path": "s_lora_rx.filter.stats.lost"}).json()
    assert r["size"] == 4


def test_flash_rejects_unknown_target_and_foreign_paths(client):
    assert client.post("/api/flash/plan", json={"target": "nope", "image": "x.elf"}).status_code == 404
    r = client.post("/api/flash/plan", json={"target": "remote", "image": "C:/Windows/notepad.exe"})
    assert r.status_code == 400 and "workspace" in r.json()["detail"]


def test_flash_candidates_only_from_allowed_globs(client):
    c = client.get("/api/flash/candidates").json()
    assert set(c) >= {"robot", "remote"}
    assert all("robot_att" not in f and "ATT_" not in f for f in c["robot"] + c["remote"])
