# Legacy / on-request worker backends (migrated from ~/CLAUDE.md 2026-07-19; native-first 2026-07-20)

**Default spawn path is NOT here.** Default is native Claude Agent-tool subagents
with a built-in `subagent_type` (`general-purpose`, `Explore`, `Plan`, `claude`).
See SKILL.md "Mandatory Spawn Path" and ~/CLAUDE.md. This file is only the
per-backend mechanics for explicit-request / legacy visible-window paths.

- **cursor-agent CLI** (explicit harness request, preferred visible path):
  `cursor-agent -p --output-format stream-json --trust --approve-mcps --sandbox disabled
  --workspace <cwd> --model cursor-grok-4.6-xhigh-fast`; tools
  `start_visible_cursor_worker` / `start_visible_haiku_composed_cursor_worker` /
  `start_visible_first_mate_cursor_pool` / `steer_visible_cursor_run`. Resume is
  `--resume <session_id>`. Read-only maps to `--mode plan`.
- **grok-4.6 xhigh via grok CLI** (legacy path, kept for grok-CLI-only extras):
  `grok --prompt-file ... --output-format streaming-json -m grok-4.6 --reasoning-effort xhigh`; tools
  `start_visible_grok_worker` / `start_visible_haiku_composed_grok_worker` /
  `start_visible_first_mate_grok_pool` / `steer_visible_grok_run`. Use when you
  want **Parallel Competition Mode** (`competition_agents`, default 16 in-turn
  competitors) and the **Mandatory Parallel Work-Checker** gate - those
  injections are grok-CLI-only. Grok 4.6 xhigh fully supersedes grok 4.5.
  xhigh is available in both grok Build CLI and cursor-agent CLI
  (`cursor-grok-4.6-xhigh-fast` with Cursor Max Mode on — Grok 4.6 Extra High Fast · MAX). `~/.grok/config.toml`
  already sets `default = "grok-4.6"` and `default_reasoning_effort = "xhigh"`.
- **Antigravity / Gemini 3.7 Flash (High)** (on request): Google `agy` CLI,
  plain-text `agy -p "..." --model "Gemini 3.7 Flash (High)"
  --dangerously-skip-permissions`; tools `start_visible_agy_worker` etc. Strong
  at coding proficiency, front-end design, and fast multi-turn coding-agent
  tasks. Effort is encoded in the model name; output is plain text, resume/steer
  best-effort via `--continue`; its Google OAuth login can go stale and demand
  interactive re-auth.
- **Codex** - **DISABLED until further notice** (owner 2026-07-15: ChatGPT login
  revoked). Do not route to Codex. `start_visible_codex_worker` /
  `_haiku_composed_codex_worker` / `_first_mate_codex_pool` /
  `steer_visible_codex_run` (model gpt-5.6-sol) remain in the code for a
  possible future revival only.
