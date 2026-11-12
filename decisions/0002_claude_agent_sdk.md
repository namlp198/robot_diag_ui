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

## Verified (2026-11-12, after the one-time login)

- `scripts/s3_spike.py`: in-process tool call and result (turns=2, about $0.001 on haiku), a write tool reaches `can_use_tool` and is
  denied (the model reports the refusal and does not retry), and `resume` of a session recalls the earlier tool result.
  Stream order per turn: system init, message_start/content_block_*/message_stop deltas, AssistantMessage, rate-limit event,
  UserMessage (tool result), second assistant message, ResultMessage.
- In the UI with both boards running: the question "does the LoRa link lose packets?" ran get_status, get_view_context and two
  get_series calls, drew a chart with show_chart, and answered with rates (about 20 frames/s, about 0.44 lost/s, about 2%),
  and said which variables it had not checked. One turn cost $0.056 on claude-sonnet-5-5.

## Not verified

- A denied built-in tool (for example Bash) in a real turn: the policy function is unit-tested, but with `tools=[]` the model has no
  built-in to call. Cancelling a turn with the Stop button while a tool runs.