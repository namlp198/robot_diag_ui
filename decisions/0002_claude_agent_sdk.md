# 0002 Chat: Claude Agent SDK (Python) in the daemon

- Status: Accepted, partly verified (see "Not verified")
- Date: 2026-11-12
- Spike: S3 (`scripts/s3_spike.py`)

## Decision

The daemon runs Claude through `claude-agent-sdk` 0.2.180 (pinned, `scripts/toolchain.psd1`; bundled Claude Code CLI 2.1.321).
`rdt/claude_bridge.py` holds one `ClaudeSDKClient` per daemon, translates SDK messages into UI events (`/ws`, type `chat`),
and exposes tools as an in-process MCP server (`rdt/agent_tools.py`). The CLI (option B in the plan) stays the fallback.

## Profile "analysis" (only profile so far)

- `tools=[]`: no built-in tools. `setting_sources=[]`: user and project settings (including allow-lists) are not loaded.
- `can_use_tool` allows only names starting with `mcp__rdt__` and denies everything else. `allowed_tools` is empty on purpose:
  an allow-list entry would auto-approve before the callback runs (the SDK warns about this).
- No tool writes, halts, resets or flashes a board. Display tools (`show_chart`, `annotate`, `highlight_range`) only
  send UI commands. Text from boards goes to Claude wrapped as `untrusted_board_text`, control characters replaced.
- Cost cap per chat session: `RDT_CHAT_MAX_USD` (default 2.0). Model: `RDT_CHAT_MODEL` (default `claude-sonnet-5-5`).

## Findings

- The SDK starts its bundled CLI and streams structured messages (system init, assistant, result) without a terminal.
- **Login is not shared** with the Claude desktop app or another CLI: the first query returns "Not logged in". One-time
  fix by the user: `.venv\Lib\site-packages\claude_agent_sdk\_bundled\claude.exe auth login`. The daemon never handles
  credentials; the UI shows this hint when it sees the error.

## Not verified (needs the login above)

- A live turn with tool calls, the event order with streaming, `can_use_tool` denial of a non-rdt tool in a real turn,
  and `resume` of a session. `scripts/s3_spike.py` covers these; the unit tests (`tests/test_agent_tools.py`) cover
  the tools and the policy function without the network.
