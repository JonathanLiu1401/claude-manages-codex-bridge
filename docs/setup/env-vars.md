# Required settings.json env block (proxy-backed worlds)

Verified 2026-07-19 on Claude Code 2.1.215 against CLIProxyAPI 7.2.91.
These go in the `"env"` object of `settings.json` in each **proxy-backed**
world (`~/.claude` for the merged plain world, `~/.claude-clx` for clx).
The direct world (`~/.claude-direct`) gets the same block minus the proxy
base URL — shipped as `launchers/force-direct.json`, passed via `--settings`
by `cld.cmd`.

```json
"env": {
  "ANTHROPIC_BASE_URL": "http://127.0.0.1:8317",
  "ENABLE_TOOL_SEARCH": "true",
  "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5[1m]",
  "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5[1m]",
  "ANTHROPIC_DEFAULT_FABLE_MODEL": "claude-fable-5[1m]",
  "CLAUDE_CODE_MAX_CONTEXT_TOKENS": "500000",
  "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "1000000"
}
```

## What each var does and why it is required

| Var | Purpose | Failure without it |
|---|---|---|
| `ANTHROPIC_BASE_URL` | Routes the session through the local CLIProxyAPI gateway in **OAuth mode** (no auth-token var — the CLI sends its rotating claude.ai OAuth bearer; the proxy must run `api-keys: []` allow-all, loopback-only). | No multi-provider models. Note: settings-env wins over process env, so a "direct" escape hatch needs its own config dir + `--settings` pin, not an env override. |
| `ENABLE_TOOL_SEARCH` | Client-side deferred tool loading: MCP tool schemas are NOT sent per request (~14 tools on the wire instead of 500+); the model loads schemas on demand via a ToolSearch tool. | grok-4.6 hard-rejects any request with >350 tool definitions (`Maximum tools limit reached`). Also saves ~200k tokens of per-session MCP context. |
| `ANTHROPIC_DEFAULT_{OPUS,SONNET,FABLE}_MODEL` | Makes TYPED aliases (`/model fable`, `--model opus`) resolve to the 1M `[1m]` variants. The interactive /model picker already picks 1M; typed aliases otherwise resolve to bare 200k variants. | Typed model switches silently land on 200k context. There is NO `ANTHROPIC_DEFAULT_GROK_MODEL` — the CLI ignores it. |
| `CLAUDE_CODE_MAX_CONTEXT_TOKENS` | Sets the client-side context window for model IDs that do NOT start with `claude-` (checked after the `[1m]`/native-1M paths). Gives grok-4.6 its real ~500k window — main model, subagents, and workflow agents alike — with percentage-based autocompaction scheduled against it. Claude models keep their own catalog windows. | Unknown model IDs are budgeted at 200k (client blocks prompts past it). **Undocumented internal of the 2.1.21x builds — re-verify after every Claude Code update** (`/context` in a grok session should show ~500k). Caveat: applies to ALL non-Claude model IDs in the process; fine when grok is the only non-Claude model in play. |

Note: bare model aliases like `grok-4.6` without `[1m]` re-trigger the 350-tool blocker and must be avoided as the main model; canonical Claude IDs carry `[1m]`.

## Related, deliberately NOT set

- `ANTHROPIC_AUTH_TOKEN` in the plain world — would flip the CLI to API-key
  mode and kill Remote Control everywhere. Only `clx.cmd` sets it (isolated
  world, reads the per-machine key from `proxy-key.txt` at launch).
- `[1m]` suffix on grok in agent frontmatter — subagent model resolution can
  strip it (anthropics/claude-code#45169), and a 1M assumption would overshoot
  grok's real ceiling with no compaction safety.

## Why no automatic alternative exists (researched + refuted 2026-07-19)

- Gateway model discovery (`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`) adds fetched
  models to the `/model` picker but **filters to IDs matching `/^(claude|anthropic)/i`**
  and carries NO context-length metadata (the `/v1/models` protocol has no window field).
  So it surfaces `claude-*`/`anthropic-*` gateway models only — grok and `agy-gemini-*`
  are dropped — and it cannot fix grok's window (that is `CLAUDE_CODE_MAX_CONTEXT_TOKENS`'s
  job). The filter lives in the fetch/build fn that writes the cache; the cache *reader*
  `a$r()` then maps that already-filtered set (see "Model selector / picker configuration").
- `ANTHROPIC_DEFAULT_*_SUPPORTED_CAPABILITIES` /
  `ANTHROPIC_CUSTOM_MODEL_OPTION_SUPPORTED_CAPABILITIES` know only 8
  capability strings (thinking/effort/temperature families) — nothing
  window-related — and are inert behind `ANTHROPIC_BASE_URL`.
- The Anthropic-compat `/v1/models` protocol has no context-length field.
- Ollama's `ollama launch claude` hit the same wall: it ships a hardcoded
  per-model table exported as `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (threshold
  only — their unknown models still meter at 200k).

## Server-side feature-gating fallout

Since Claude Code v2.1.196, Remote Control is disabled whenever the resolved
`ANTHROPIC_BASE_URL` is not `api.anthropic.com`. RC and proxy models are
mutually exclusive per session: use `cld.cmd` (direct world) for RC sessions.
Beware the project-scope leak: with cwd under the home dir, the CLI loads
`~/.claude/settings.json` as PROJECT-scope settings even under a different
`CLAUDE_CONFIG_DIR` — `cld.cmd` defeats this with `--settings
force-direct.json` (highest precedence).
Additionally, `/autocompact` and auto-dream (the `/memory` toggle) are also gated — these are account-level GrowthBook flags, not local bugs. Remote Control specifically requires a DIRECT `api.anthropic.com` base URL, so it is blocked in proxy-backed sessions; `cld.cmd` is the direct-Anthropic escape hatch that restores `/rc`.

## Model selector / `/model` picker configuration

Verified against the 2.1.215 `claude.exe` bundle in the plain **proxy + OAuth** world.

**Hard ceiling: the picker holds exactly ONE non-Claude model.** The two mechanisms that would
*append arbitrary models* to the picker are BOTH dead behind the proxy:

- **Gateway discovery** (`CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=true`) never even fetches: its
  bootstrap runs `if(!ANTHROPIC_AUTH_TOKEN && !Hte()) return`, and `Hte()` returns the static API key
  from `DM()` — **null in pure-OAuth mode** — so it aborts before calling `/v1/models` (the cache
  `~/.claude/cache/gateway-models.json` is never written). Even if it ran, it filters results to
  `/^(claude|anthropic)/i`, dropping grok and `agy-*`. It would only work in API-key mode (e.g.
  `clx`, which sets `ANTHROPIC_AUTH_TOKEN`), and even then shows claude-prefixed ids only. The other
  gates all pass here (`vn()==="firstParty"`; `$d()` false = base URL is a custom gateway; `ta()`
  false = no `DO_NOT_TRACK`/`DISABLE_TELEMETRY`/`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`) — the auth
  guard is the blocker. Harmless left on; it just no-ops.
- **Server bootstrap** `additional_model_options` (from `/api/claude_cli/bootstrap`) — the proxy
  doesn't serve that endpoint (same reason `/rc` and `/autocompact` are gone in this world).

So the picker is built ONLY from static, env-defined entries (no fetch, no auth):

1. **Tier slots** — `ANTHROPIC_DEFAULT_{OPUS,SONNET,FABLE,HAIKU}_MODEL` (+ `_NAME`/`_DESCRIPTION`/
   `_SUPPORTED_CAPABILITIES`). These accept **only real Claude models**; a non-Claude id is silently
   rejected and the slot falls back to its default. **VERIFIED**: `ANTHROPIC_DEFAULT_HAIKU_MODEL=
   agy-gemini-3-1-pro[1m]` still rendered "Haiku 4.5", not Gemini. (This is why the Opus slot can be
   `claude-opus-5[1m]` but no tier slot can hold grok/gemini.)
2. **One custom slot** — `ANTHROPIC_CUSTOM_MODEL_OPTION` (+ `_NAME`/`_DESCRIPTION`/
   `_SUPPORTED_CAPABILITIES`). Accepts **any** model, no validation. **VERIFIED**: `grok-4.6`
   rendered as a picker row. Singular — there is no `_2`.
3. `availableModels`+`enforceAvailableModels` only TRIM the built list; `modelOverrides` remaps a
   claude id. Neither can ADD a non-Claude model.

**Net: exactly one non-Claude model can be a picker row — the custom slot. grok OR gemini, not
both.** The other is reached via typed `/model <id>` or a launcher (`clg` for grok).

**Window — the `[1m]` rule for non-Claude MAIN models:** a non-Claude id used as the main model
(the custom slot, the `model` pin, or typed `/model`) needs the `[1m]` suffix for its 1M window; bare,
it inherits the 500k global `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. **VERIFIED**: bare `agy-gemini-3-6-flash`
showed 500k in `/context`; `agy-gemini-3-6-flash[1m]` → 1M. So pin/select Gemini as
`agy-gemini-3-6-flash[1m]`, and use the suffix when typing (`/model agy-gemini-3-6-flash[1m]`).
**Grok stays BARE** — its real window is ~500k, so `[1m]` would over-budget it. (The agy Gemini
subagents already bake `[1m]` into their frontmatter.)

**Current setup (2026-08-12):** custom slot = `grok-4.6` ("Grok 4.6 xhigh", ~500k); Gemini 3.6 Flash via
`/model agy-gemini-3-6-flash[1m]` or the `model` pin at 1M; Opus/Sonnet slots = real Claude (1M),
Fable = real Claude (**protected** — usage credits), Haiku = default. Env is read at bootstrap → a
FULL session restart applies changes (`/reload-plugins` does not).
