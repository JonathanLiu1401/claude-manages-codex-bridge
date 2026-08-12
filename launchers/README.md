# Launchers

Windows `.cmd` launchers for the three Claude Code "worlds" plus the grok
main-model profile. Deploy to a PATH dir (e.g. `%USERPROFILE%\.local\bin`).

| Launcher | World | Endpoint | Models | Remote Control |
|---|---|---|---|---|
| `claude` (plain) | `~/.claude` | CLIProxyAPI (via settings env) | all proxy models | no (gateway) |
| `clg.cmd` | `~/.claude` | CLIProxyAPI | starts on grok-4.6 (500k window) | no |
| `clx.cmd` | `~/.claude-clx` | CLIProxyAPI (API-key mode) | all proxy models | no |
| `cld.cmd` | `~/.claude-direct` | api.anthropic.com (forced) | Claude models only | **yes** |

Notes:
- `cld.cmd` force-pins the base URL via `--settings force-direct.json` because
  project-scope settings (`~/.claude/settings.json` when cwd is under the home
  dir) would otherwise leak the proxy env into the "direct" world and silently
  kill Remote Control.
- `clx.cmd` reads the per-machine loopback API key from
  `%USERPROFILE%\CLIProxyAPI\proxy-key.txt` at launch — never hardcode it.
- `cld.cmd` also self-heals the shared-session-store junction
  (`projects` -> `~/.claude/projects`) once no cld session holds the folder.
- Grok context sizing comes from `CLAUDE_CODE_MAX_CONTEXT_TOKENS=500000` in
  the settings env (see main README) — `clg.cmd` just starts on bare
  `grok-4.6` and inherits it.
