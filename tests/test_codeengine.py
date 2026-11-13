import asyncio
import sys

import pytest

from rdt import codeengine as ce
from rdt import settings


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int a = 1;\r\nint b = 2;\r\n", encoding="utf-8", newline="")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("TOKEN=x")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")
    return tmp_path


def test_paths_cannot_leave_the_repo_or_touch_secrets_and_git(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    for bad in ("../x", str(outside), ".env", "src/../../x"):
        with pytest.raises(ce.EngineError):
            ce.resolve(repo, bad)
    with pytest.raises(ce.EngineError, match=".git"):
        ce.resolve(repo, ".git/config", write=True)
    assert ce.resolve(repo, "src/main.c").name == "main.c"


def test_list_read_search_skip_secrets_and_binaries(repo):
    assert ce.list_files(repo)["files"] == ["blob.bin", "src/main.c"]
    r = ce.read_file(repo, "src/main.c")
    assert r["total_lines"] == 2 and r["text"].startswith("1: int a")
    with pytest.raises(ce.EngineError, match="binary"):
        ce.read_file(repo, "blob.bin")
    assert ce.search(repo, r"int b", "*.c")["hits"][0]["line"] == 2
    with pytest.raises(ce.EngineError, match="regex"):
        ce.search(repo, "(")


def test_edit_needs_one_match_and_keeps_crlf(repo):
    p, old, new = ce.plan_edit(repo, "src/main.c", "int a = 1;\nint b", "int a = 5;\nint b")  # LF in the request, CRLF in the file
    assert new == "int a = 5;\r\nint b = 2;\r\n"
    ce.commit(p, new)
    assert (repo / "src" / "main.c").read_bytes() == b"int a = 5;\r\nint b = 2;\r\n"
    with pytest.raises(ce.EngineError, match="0 places"):
        ce.plan_edit(repo, "src/main.c", "nope", "x")
    with pytest.raises(ce.EngineError, match="2 places"):
        ce.plan_edit(repo, "src/main.c", "int", "long")
    assert "-int a = 1" in ce.diff("src/main.c", old, new)


def test_build_runs_only_the_configured_command(repo):
    with pytest.raises(ce.EngineError, match="no build command"):
        ce.run_build(repo, None)
    r = ce.run_build(repo, f'"{sys.executable}" -c "print(42)"')
    assert r["exit_code"] == 0 and "42" in r["output_tail"]
    assert ce.run_build(repo, f'"{sys.executable}" -c "import sys; sys.exit(3)"')["exit_code"] == 3


def test_register_firmware_checks_the_file(repo):
    (repo / "out.bin").write_bytes(b"\x01" * 8)
    assert ce.check_firmware(repo, "out.bin")["kind"] == "bin"
    with pytest.raises(ce.EngineError):
        ce.check_firmware(repo, "src/main.c")
    with pytest.raises(ce.EngineError):
        ce.check_firmware(repo, "../out.bin")


def test_approval_flow_allow_deny_timeout_and_stop(repo, monkeypatch):
    events = []
    eng = ce.Engine({"name": "robot", "path": str(repo), "board": "robot"}, events.append)

    async def scenario():
        t = asyncio.create_task(eng.ask("edit", "a.c", "diff"))
        await asyncio.sleep(0)
        ev = next(e for e in events if e["kind"] == "approval")
        assert eng.state == "waiting" and eng.answer(ev["id"], True) and await t is True
        assert not eng.answer(ev["id"], True) and eng.state == "idle"  # back to the state before asking
        t = asyncio.create_task(eng.ask("edit", "a.c", "diff"))
        await asyncio.sleep(0)
        eng.deny_all()
        assert await t is False
        monkeypatch.setattr(ce, "APPROVAL_TIMEOUT", 0.05)
        assert await eng.ask("write", "b.c", "") is False
    asyncio.run(scenario())
    assert [e["allow"] for e in events if e["kind"] == "approval_done"] == [True, False, False]


def test_state_for_tool():
    assert ce.state_for_tool("mcp__rdt__repo_build") == "building"
    assert ce.state_for_tool("mcp__rdt__get_status") == "thinking"


def test_repos_setting_is_validated(tmp_path):
    ok = {"name": "robot", "path": str(tmp_path), "board": "robot", "build_cmd": "make"}
    assert settings.validate({"repos": [ok]}).repos == [ok]
    for bad in ({**ok, "name": "bad name"}, {**ok, "build_cmd": "a\nb"}, {**ok, "x": 1}, {**ok, "board": "a b"}, {**ok, "path": ""}):
        with pytest.raises(settings.SettingsError):
            settings.validate({"repos": [bad]})
    with pytest.raises(settings.SettingsError, match="unique"):
        settings.validate({"repos": [ok, ok]})


def test_bridge_tools_confine_and_ask(repo):
    pytest.importorskip("claude_agent_sdk")
    from rdt import claude_bridge as cb
    events, regs = [], []
    eng = ce.Engine({"name": "robot", "path": str(repo), "board": "robot", "build_cmd": None}, events.append)
    tools = {t.name: t.handler for t in cb.code_tools(eng, lambda r, i: regs.append(i))}

    async def scenario():
        bad = await tools["repo_read"]({"path": "../secret"})
        assert bad["is_error"]
        task = asyncio.create_task(tools["repo_edit"]({"path": "src/main.c", "old": "int a = 1;", "new": "int a = 9;"}))
        await asyncio.sleep(0.05)
        assert b"int a = 1" in (repo / "src" / "main.c").read_bytes()        # nothing written before approval
        aid = next(e["id"] for e in events if e["kind"] == "approval")
        eng.answer(aid, False)
        assert (await task)["is_error"] and b"int a = 1" in (repo / "src" / "main.c").read_bytes()
        task = asyncio.create_task(tools["repo_edit"]({"path": "src/main.c", "old": "int a = 1;", "new": "int a = 9;"}))
        await asyncio.sleep(0.05)
        eng.answer([e["id"] for e in events if e["kind"] == "approval"][-1], True)
        assert "is_error" not in await task and b"int a = 9" in (repo / "src" / "main.c").read_bytes()
        (repo / "o.bin").write_bytes(b"\x01" * 8)
        task = asyncio.create_task(tools["repo_register_firmware"]({"path": "o.bin"}))
        await asyncio.sleep(0.05)
        assert not regs
        eng.answer([e["id"] for e in events if e["kind"] == "approval"][-1], True)
        await task
        assert regs and regs[0]["kind"] == "bin"
        assert (await tools["repo_build"]({}))["is_error"]                   # no build_cmd configured
    asyncio.run(scenario())
