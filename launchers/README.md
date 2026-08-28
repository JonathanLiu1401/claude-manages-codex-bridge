# Launchers

There are no launcher wrappers any more. The three Claude Code "worlds"
(`clx`, `cld`, `clg`) and the local multi-provider gateway they pointed at were
removed, so plain `claude` is the only entry point: it talks straight to
`api.anthropic.com` with the normal OAuth login, out of `~/.claude`.

Notes:
- Nothing here needs deploying to a PATH dir any more.
- Do NOT set `ANTHROPIC_BASE_URL` or `ANTHROPIC_AUTH_TOKEN`. A non-Anthropic
  base URL is what used to disable Remote Control, `/autocompact`, and
  auto-dream; plain `claude` keeps all three working.
- There are no per-world config dirs (`~/.claude-clx`, `~/.claude-direct`,
  `~/.claude-ollama`) and no `CLAUDE_CONFIG_DIR` juggling. One config dir:
  `~/.claude`.
- To start on a specific model, use the `/model` picker or `claude --model <id>`
  instead of a wrapper script.
- `force-direct.json` and `proxy.json.example` used to live here. They were the
  "direct world" base-URL pin and the gateway config template respectively, and
  both have been deleted along with everything else in this list.
