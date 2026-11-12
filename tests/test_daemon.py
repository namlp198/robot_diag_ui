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


def test_settings_roundtrip_and_validation(client, tmp_path):
    j = client.get("/api/settings").json()
    assert "claude-sonnet-5-5" in j["models"] and "high" in j["efforts"] and j["core_registers"]
    r = client.put("/api/settings", json={"model": "claude-opus-5-5", "effort": "high"})
    assert r.status_code == 200 and r.json()["settings"]["effort"] == "high"
    assert client.put("/api/settings", json={"effort": "ultra"}).status_code == 400
    assert (tmp_path / "settings.json").exists()


def test_chat_info_does_not_need_a_conversation(client):
    j = client.get("/api/chat/info").json()
    assert "sdk" in j and "settings" in j and j["busy"] is False


def test_expr_endpoint_checks_regions_without_a_probe(client):
    r = client.put("/api/expr", json={"target": "robot", "items": [
        {"id": "a", "text": "0x20000000", "type": "u32"}, {"id": "b", "text": "0x40011004"}, {"id": "c", "text": "0xE000ED28"}]})
    items = {i["id"]: i for i in r.json()["items"]}
    assert items["a"]["address"] == 0x20000000 and "peripheral" in items["b"]["error"] and items["c"]["address"] == 0xE000ED28
    client.put("/api/settings", json={"allow_peripheral_reads": True})
    r = client.get("/api/expr").json()
    assert [i["id"] for i in r["items"]["robot"]] == ["a", "b", "c"]   # re-checked against the new policy
    assert client.put("/api/expr", json={"target": "nope", "items": []}).status_code == 404


def test_frames_endpoint_and_session_frames(client, tmp_path):
    from rdt import rcl
    body = bytes([0x10, 0x01, 0x34, 0x12, 5, 7]) + bytes([8, 128, 128, 255, 255, 255, 255])
    f = rcl.SOF + body + rcl.crc16(body).to_bytes(2, "little")
    v = Resolved("s_lora_rx.parser.buf", 0x20000000, 58, "array", "uint8_t")
    with Recorder(tmp_path, {"robot": {"serial": "S", "elf": "x", "paths": ["s_lora_rx.parser.buf"], "vars": [v]}}) as r:
        r.add_sample("robot", 0.5, [f.ljust(58, b"\0").hex()])   # the sampler stores bytes variables as hex
    j = client.get(f"/api/sessions/{r.dir.name}/frames").json()
    assert [(x["source"], x["seq"], x["type_name"]) for x in j["frames"]] == [("robot_rx", 5, "CONTROL")]
    assert client.get("/api/frames").json()["frames"] == []


def test_live_frames_are_published_as_websocket_frame_messages(tmp_path):
    """Regression: a frame's own `type` field must not replace the message type ("frame") the UI dispatches on."""
    from rdt import rcl
    hub = Hub(sessions_dir=tmp_path)
    sent = []
    hub._publish = sent.append
    body = bytes([0x10, 0x01, 0x34, 0x12, 5, 7]) + bytes([8, 128, 128, 255, 255, 255, 255])
    f = rcl.SOF + body + rcl.crc16(body).to_bytes(2, "little")
    hub.columns = {"remote": ["s_tx.out.frame", "s_tx.out.frame_len"]}
    hub.ring = {"remote": __import__("collections").deque()}
    hub.capture = rcl.FrameCapture(hub.columns)
    hub.on_sample("remote", 1.0, [f.ljust(58, b"\0").hex(), len(f)])
    msgs = [m for m in sent if m["type"] == "frame"]
    assert len(msgs) == 1 and msgs[0]["source"] == "remote_tx" and msgs[0]["seq"] == 5 and msgs[0]["type_name"] == "CONTROL"
    assert [m["type"] for m in sent] == ["sample", "frame"]


def test_can_frames_message_type_and_session_file(tmp_path):
    """The WebSocket message type must stay "can" (a frame field called `type` once hid a message)."""
    hub = Hub(sessions_dir=tmp_path)
    sent = []
    hub._publish = sent.append
    f = {"dir": "tx", "id": 0x601, "ext": False, "rtr": False, "fd": False, "brs": False, "dlc": 2, "data": "4041", "ts": None, "label": "x"}
    v = Resolved("a", 0x20000000, 4, "uint", "uint32_t")
    from rdt.recorder import Recorder
    with Recorder(tmp_path, {"robot": {"serial": "S", "elf": "x", "paths": ["a"], "vars": [v]}}) as r:
        hub.recorder = r
        hub.on_can("robot", 1.5, [f], {"polls": 1, "tx_frames": 1})
        hub.recorder = None
    assert sent[0]["type"] == "can" and sent[0]["frames"][0]["id"] == 0x601 and sent[0]["frames"][0]["target"] == "robot"
    from rdt.recorder import open_session
    assert open_session(r.dir).can("robot")[0]["id"] == 0x601
    assert hub.can[-1]["t"] == 1.5


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
