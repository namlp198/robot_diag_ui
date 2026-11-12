# 0005: UI themes, bilingual UI, reference pages, read-only Programmer CLI runner

- Status: Accepted (UI verified in headless Edge; the CLI runner's real `STM32_Programmer_CLI` run not yet exercised from the UI)
- Date: 2026-11-12

## Decision

- **Themes**: dark (default) and light, both monospace "hacker / mystic" styling, chosen with `data-theme` on `<html>`, remembered in localStorage (`rdt.theme`). Colours are CSS variables; charts read `--c1..--c6` when created and are rebuilt when the theme changes. No `prefers-color-scheme` any more.
- **Language**: Vietnamese and English, remembered in `rdt.lang` (default Vietnamese). UI text lives in `ui/src/i18n.js`. Analyzer findings are produced in Vietnamese by the daemon (Claude tools see the same text); for English the UI rebuilds title, detail and next checks from the finding `id` and `evidence` (`findingText`). Daemon error messages and flash check details stay in English; board data is shown as received.
- **Reference**: `rdt/reference.py` is the single source (monitored variables, analyzer rules, pyOCD API and CLI, STM32_Programmer_CLI), bilingual, served at `GET /api/reference`, shown on the UI "Reference" page, and written to `docs/REFERENCE.en.md` and `docs/REFERENCE.vi.md` by `scripts/gen_reference.py`. Tests fail when a variable in `ui/src/panels.js` has no entry or when the generated docs are stale.
- **Programmer CLI page**: `POST /api/cube/run` runs only whitelisted read-only commands (`-l st-link`, connect info, `-r32`, `-ob displ`) with `mode=HOTPLUG` (no halt, no reset). Reads are limited to flash and SRAM, 4-byte aligned, at most 4 KiB; peripheral addresses are refused because reads can clear flags. The probe must be free (watch stopped). Writing, erasing, resetting, halting and running are not exposed; flashing stays in the gated Flash panel (decision 0003). Claude has no tool for any of this.

## Why

The tool is used daily by one person, in two languages; the commands rdt runs on the hardware were documented only in code, so the user could not see what each one means or how it differs from the unsafe ones.

## Consequences

- New UI text needs both languages; add new monitored variables to `rdt/reference.py` and rerun `scripts/gen_reference.py`.
- A `$:` block that touches a variable mutated inside a function it calls re-triggers itself in Svelte (it froze the page once in `LinkPanel`); theme rebuilds use a plain store subscription.
