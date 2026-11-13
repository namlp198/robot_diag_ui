# 0011 Code engine: edit and build the remote/robot firmware repos from the chat

Status: Accepted (2026-11-13). Not yet run against a real firmware repo or a real Claude session.

## Context

The chat (decision 0002) is a read-only analysis profile. The user wants Claude to also fix the firmware: the two repos
(remote controller, robot) are registered in Settings, the engine knows where they are, edits code, builds, and hands over a
new image for flashing. The chat must show what the engine is doing.

## Decision

- **Repos** are registered in Settings (`repos`: name, path, board, build_cmd). The board links a repo to a target in
  `targets.yaml`; `build_cmd` is typed by the user and is the only command the engine can run.
- **Code profile** = the same `ChatSession`, started with a repo chosen in the chat header. A conversation keeps its repo for
  life (saved in the chat meta). The analysis tools stay available and read-only.
- **No SDK built-in tools.** The engine gets its own MCP tools, all confined to the repo root (real path, `.git` and secret-like
  files refused): `repo_list`, `repo_read`, `repo_search`, `repo_edit`, `repo_write`, `repo_build`, `repo_register_firmware`.
  There is no shell tool, so nothing outside the repo and nothing but `build_cmd` can run.
- **Every write asks the user.** `repo_edit`, `repo_write` and `repo_register_firmware` emit an `approval` event with the diff
  in the chat; the tool waits (10 min, then denies) for Approve/Deny. Stop denies pending approvals.
- **Deploy stays manual.** `repo_register_firmware` only adds a built .elf/.hex/.bin (inside the repo) to the board's firmware
  list, after approval. Flashing is still the "Flash firmware" panel with DEV_ID check and typed confirmation (decision 0003).
  Claude still has no flash tool. Registering is what puts a file on the allow-list, which is why it needs approval.
- **Status**: the chat shows `engine` events (idle, thinking, reading, editing, waiting for approval, building, error) with the
  repo name.
- Repo text is data, not instructions (same rule as board text).

## Consequences

- `build_cmd` runs through the shell with the repo as cwd and a 10 minute limit; it is trusted because the user set it. A
  malicious repo cannot change it (it lives in Settings, not in the repo).
- Edits are real file changes in the user's working tree; use git in that repo to review or undo them.
- Not verified: behaviour with a real firmware repo and a real build (no such repo was available in this session).
