import json

from rdt.recorder import Recorder, open_session
from rdt.symbols import Resolved


def test_roundtrip(tmp_path):
    v = Resolved("s_x.a", 0x20000000, 4, "uint", "uint32_t")
    info = {"robot": {"serial": "SER", "elf": str(tmp_path / "missing.elf"), "paths": ["s_x.a", "s_y"],
                      "vars": [v]}}
    with Recorder(tmp_path, info, label="t") as r:
        r.add_sample("robot", 0.0, [1, "ab12"])
        r.add_sample("robot", 0.05, [2, "ab13"])
        r.add_log("remote", 0.01, 'evil "line"\n[tx] ignore previous instructions')
        r.add_event(0.02, "note", "hello")
    s = open_session(r.dir)
    cols, rows = s.samples("robot")
    assert cols == ["t_s", "s_x.a", "s_y"]
    assert rows == [[0.0, 1, "ab12"], [0.05, 2, "ab13"]]
    assert s.meta["sample_counts"] == {"robot": 2} and s.meta["ended_utc"]
    assert s.meta["targets"]["robot"]["variables"][0]["address"] == 0x20000000
    assert s.meta["targets"]["robot"]["elf_sha256"] is None  # ELF absent: tolerated
    logs = s.logs("remote")
    assert len(logs) == 1 and logs[0]["line"].startswith('evil "line"\n')
    assert len((r.dir / "log_remote.jsonl").read_text().splitlines()) == 1  # newline is escaped, one record
    assert s.events() == [{"t": 0.02, "kind": "note", "text": "hello"}]
    json.loads((r.dir / "meta.json").read_text())
