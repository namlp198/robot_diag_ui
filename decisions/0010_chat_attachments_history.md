# 0010: chat attachments and saved conversations

- Status: Accepted. Verified: unit tests with a fake SDK client, a real chat on Haiku (image + text file read correctly, saved, daemon restarted, chat opened and continued with its context, about $0.003), UI in headless Edge. Not run: the same in the installed exe, a PDF attachment against the real API.
- Date: 2026-11-12

## Decision

- **Attachments** (`rdt/attachments.py`, `ui/src/attach.js`): images (PNG, JPEG, GIF, WebP), PDF and text files (a fixed list of extensions), up to 6 per message. The UI shrinks big images (longest side 1568 px) and sends base64; the daemon recognises types by their first bytes (never by name or declared MIME), caps sizes (image 5 MB, PDF 10 MB, text 200 KB cut with a note, 25 MB total) and refuses binaries (firmware and ELF files belong in Settings). Text is wrapped in `<attached_file>` labelled as user data and the closing tag cannot be forged. Files go to Claude as image/document/text content blocks (`ClaudeSDKClient.query` with a message stream). Attach by button, paste or drop.
- **Saved conversations** (`rdt/chatstore.py`): every chat is saved under `<sessions>/chats/<id>/` (`meta.json`, `events.jsonl` = the events the UI replays, `files/` = the attachments); streaming deltas and idle are not stored. The Claude Code session id is kept: opening a chat (`POST /api/chats/<id>/open`) makes it current and the next message resumes that session; if the CLI transcript is gone, the chat continues with a fresh context and says so (the saved messages stay readable). List with search, rename, export as Markdown, delete (two-step) in the chat header; a toggle hides or shows tool calls (remembered in the browser).
- Attachment files are served back only from the chat's own folder, images inline and everything else as a download with `nosniff`; ids and file names are checked against path tricks.

## Consequences

- Chats and their files stay on this machine (`sessions/` is git-ignored; `DATA\sessions` in the installed app). Claude Code keeps its own copy of each session in the user's `~/.claude/projects`.
- Anything attached is sent to the Anthropic API like any chat message; the Settings page does not warn about it yet.
