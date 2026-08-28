# Required settings.json env block

Verified 2026-07-19 on Claude Code 2.1.215.
These go in the `"env"` object of `~/.claude/settings.json`. There is exactly ONE
Claude Code world now: plain `claude` against `api.anthropic.com` on the normal
OAuth login. No base-URL or auth-token var, no launcher wrappers, and no
per-world config dirs to keep in sync.

```json
"env": {
  "ENABLE_TOOL_SEARCH": "true",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5[1m]",
  "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5[1m]",
  "ANTHROPIC_DEFAULT_FABLE_MODEL": "claude-fable-5[1m]",
  "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"
}
```

## What each var does and why it is required

| Var | Purpose | Failure without it |
|---|---|---|
| `ENABLE_TOOL_SEARCH` | Client-side deferred tool loading: MCP tool schemas are NOT sent per request (~14 tools on the wire instead of 500+); the model loads schemas on demand via a ToolSearch tool. | Saves ~200k tokens of per-session MCP context; without it every loaded MCP server's full schema ships on every request. |
| `ANTHROPIC_DEFAULT_{OPUS,SONNET,FABLE}_MODEL` | Makes TYPED aliases (`/model fable`, `--model opus`) resolve to the 1M `[1m]` variants. The interactive /model picker already picks 1M; typed aliases otherwise resolve to bare 200k variants. | Typed model switches silently land on 200k context. |

Note: the canonical Claude IDs carry `[1m]`, and `CLAUDE_CODE_AUTO_COMPACT_WINDOW`
is set to `1000000` to schedule autocompaction against that window.

## Related, deliberately NOT set

- `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`. Both existed only to point the
  CLI at the removed local multi-provider gateway. A base URL that is not
  `api.anthropic.com` disables Remote Control (`/rc`), and an auth token flips
  the CLI from OAuth into API-key mode. Leave both unset so plain `claude` keeps
  its full feature set.
- `CLAUDE_CONFIG_DIR`. There is one config dir, `~/.claude`. Per-world dirs
  (`~/.claude-clx`, `~/.claude-direct`, `~/.claude-ollama`) are gone, and with
  them the project-scope settings leak that made pinned `--settings` files
  necessary.
- `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. It only ever applied to model IDs that do
  NOT start with `claude-`, which existed solely because the gateway served
  non-Claude models. It does nothing for Claude models, which carry their own
  catalog windows.
