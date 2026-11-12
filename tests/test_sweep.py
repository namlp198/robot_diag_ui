from rdt.analyzers import REMOTE, ROBOT, Data
from rdt.sweep import PATHS, REMOTE_PATHS, boundaries_from_log, compute, to_csv


def robot_series(n=600, hz=10.0, loss_after=300):
    t = [i / hz for i in range(n)]
    acc = [i * 2 for i in range(n)]                       # 20 frames/s accepted
    lost = [max(0, (i - loss_after)) // 5 for i in range(n)]  # one loss every 0.5 s in the second half
    return t, {PATHS["accepted"]: acc, PATHS["lost"]: lost, PATHS["control"]: acc[:], PATHS["crc"]: [0] * n}


def test_log_boundaries_and_loss_per_step():
    t, cols = robot_series()
    logs = {REMOTE: [(0.0, "[sweep] step 0 gap 100 ms sent 0"), (30.0, "[sweep] step 1 gap 50 ms sent 300"),
                     (59.9, "[sweep] done sent 900"), (5.0, "[lora] unrelated")]}
    res = compute(Data({ROBOT: (t, cols)}, logs))
    r0, r1 = res["rows"]
    assert res["source"] == "vcp" and r0["gap_ms"] == 100 and r1["gap_ms"] == 50
    assert r0["lost"] == 0 and r0["loss_pct"] == 0 and r0["sent"] == 300 and r1["sent"] == 600
    assert r1["lost"] > 0 and 0 < r1["loss_pct"] < 10


def test_restart_jump_is_removed_from_step():
    t, cols = robot_series(loss_after=10_000)
    for j in range(100, len(t)):
        cols[PATHS["lost"]][j] += 255
    logs = {REMOTE: [(0.0, "[sweep] step 0 gap 100 ms sent 0"), (59.9, "[sweep] done sent 600")]}
    r = compute(Data({ROBOT: (t, cols)}, logs))["rows"][0]
    assert r["lost"] == 0 and r["restarts_removed"] == 1


def test_falls_back_to_sweep_step_variable():
    t, cols = robot_series()
    n = len(t)
    remote = {REMOTE_PATHS["step"]: [0] * 300 + [1] * (n - 300), REMOTE_PATHS["gap"]: [100] * 300 + [50] * (n - 300),
              REMOTE_PATHS["sent"]: list(range(n))}
    res = compute(Data({ROBOT: (t, cols), REMOTE: (t, remote)}))
    assert res["source"] == "variable" and [r["gap_ms"] for r in res["rows"]] == [100, 50]
    assert res["rows"][0]["sent"] == 300 and res["rows"][1]["lost"] > 0


def test_clear_errors_when_nothing_to_compute():
    t, cols = robot_series()
    assert "no sweep found" in compute(Data({ROBOT: (t, cols)}))["error"]
    assert "not recorded" in compute(Data({ROBOT: (t, {})}))["error"]


def test_regex_and_csv():
    assert [b.gap_ms for b in boundaries_from_log([(1, "[sweep] step 3 gap 30 ms sent 1001")])] == [30]
    assert to_csv([{"a": 1, "b": 2}]).splitlines() == ["a,b", "1,2"]
