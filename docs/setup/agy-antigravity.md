# Antigravity (agy) native subagents

Verified 2026-07-19 on Claude Code 2.1.215 + CLIProxyAPI 7.2.91 (Windows).

Two Google Antigravity **Gemini** models wired as **native Claude Code subagents** (Agent tool,
`subagent_type: agy-*`) served through the local CLIProxyAPI gateway - the non-terminal
alternative to the legacy `start_visible_agy_worker`. Each draws the Antigravity
account's **separate** quota, never the owner's real Claude/Anthropic subscription.

| subagent_type | client model id (pinned `[1m]`) | Antigravity upstream id | display |
|---|---|---|---|
| `agy-gemini-3-1-pro` | `agy-gemini-3-1-pro` | `gemini-pro-agent` | Gemini 3.1 Pro (High) |
| `agy-gemini-3-5-flash` | `agy-gemini-3-5-flash` | `gemini-3.6-flash-high` | Gemini 3.6 Flash (High) |

> **2026-07-27:** 3.6 Flash supersedes 3.5, so the flash alias was repointed to
> `gemini-3.6-flash-high`. The client-visible alias deliberately stays
> `agy-gemini-3-5-flash` so the subagent type and ~50 doc references keep working
> (renaming it would touch 21 files). See the exact-catalog-id gotcha in section 3.

> "High" tier = the `-agent` upstream id, **not** `*-high` (those aren't in the live
> catalog). GPT-OSS 120B (`gpt-oss-120b-medium`) **and the Claude 4.6 models** (Opus/Sonnet 4.6 Thinking) are served by the channel but left
> **unwired** by choice: they share the Claude/GPT quota bucket, whose 5-hour limit exhausts fast (observed 0% while the Gemini bucket had ~96% free). Only the two Gemini subagents are wired.

## 1. Authenticate the Antigravity channel (one-time)

```
cd C:\Users\jonny\CLIProxyAPI
.\cli-proxy-api.exe -antigravity-login      # OAuth browser flow, callback :51121
```

Writes `~/.cli-proxy-api/antigravity-<email>.json`. Use the Google account that has
Antigravity access - **separate** from the Claude/xAI OAuth accounts so it draws its own
quota. Auth files **hot-reload** (fsnotify on the auth dir); no restart needed for login.

## 2. Add the model aliases to `config.yaml`

Append to `C:\Users\jonny\CLIProxyAPI\config.yaml` (back it up first). `fork` omitted =
rename, so the upstream id is replaced by a unique `agy-` client id; `force-mapping: true`
echoes the alias back in the response `model` field. The two Antigravity **Claude** 4.6
models (Opus/Sonnet) are EXCLUDED, not aliased - their quota bucket exhausts almost instantly
(dropped 2026-07-19); excluding `claude-sonnet-4-6` also returns that bare id to anthropic-only
(so there is no cross-provider collision).

```yaml
oauth-model-alias:
  antigravity:
    - name: "gemini-pro-agent"
      alias: "agy-gemini-3-1-pro"
      display-name: "Antigravity Gemini 3.1 Pro (High)"
      force-mapping: true
    - name: "gemini-3-flash-agent"
      alias: "agy-gemini-3-5-flash"
      display-name: "Antigravity Gemini 3.5 Flash (High)"
      force-mapping: true

# Exclude the Antigravity Claude 4.6 models (quota bucket exhausts instantly).
oauth-excluded-models:
  antigravity:
    - "claude-opus-4-6-thinking"
    - "claude-sonnet-4-6"
```

## 3. RESTART the proxy - config does NOT hot-reload on Windows

Auth files hot-reload, but **editing `config.yaml` does not** apply on Windows: an
atomic-save (write-temp-then-rename) replaces the file's inode, so the fsnotify watch on
the config file keeps watching the old, deleted inode. You must restart the running
process (it is the machine's shared gateway - verify it comes back before relying on it):

```powershell
$p = Get-Process cli-proxy-api -ErrorAction SilentlyContinue
if ($p) { Stop-Process -Id $p.Id -Force }
Start-Sleep 2
Start-ScheduledTask -TaskName 'CLIProxyAPI'   # relaunches with -config config.yaml
# then poll http://127.0.0.1:8317/v1/models until it returns 200
```

### Alias `name:` must be an EXACT catalog id (2026-07-27 gotcha)

When repointing an alias to a newer model, `name:` has to match an id that literally
appears in `GET /v1/models`. It is NOT the id the response echoes back.

Concrete failure: repointing 3.5 Flash to Gemini 3.6, `name: "gemini-3.6-flash"` (the
value echoed in responses) silently failed to bind - `agy-gemini-3-5-flash` disappeared
from the catalog entirely and every request 502'd. The correct catalog id was
`gemini-3.6-flash-high`. Symptom to watch for: after a restart the alias is missing from
`/v1/models` and the previously-consumed upstream id reappears (force-mapping released it).

Also note Antigravity publishes agent-mode upstreams only for some tiers
(`gemini-3-flash-agent`, `gemini-pro-agent`); there is no 3.6 agent-mode name. Repointing
to a standard-mode id therefore drops agent mode - re-verify tool calling afterwards
(`POST /v1/messages` with a `tools` array should return `stop_reason: tool_use`).

## 4. Verify

```
GET http://127.0.0.1:8317/v1/models
```
- Both aliases appear once each with `owned_by: antigravity`; their upstream ids are gone
  (consumed by `force-mapping`). If an alias is MISSING and its upstream id is back, the
  alias failed to bind - see the exact-catalog-id gotcha above.
- `claude-sonnet-4-6` is now `owned_by: anthropic` only (collision split); `claude-opus-5`,
  `claude-sonnet-5`, `grok-4.6` still present.
- Probe the real subagent path (`POST /v1/messages`, `model: <alias>`, tiny `max_tokens`):
  expect 200 with the response `model` echoing the alias (force-mapping working). Because
  each `-agy` alias is defined **only** under `oauth-model-alias.antigravity`, no other
  channel can serve it - antigravity routing is guaranteed by construction (don't rely on
  the merged-list `owned_by` label, which reflects merge priority not exclusivity).

## 5. Context windows

All four subagents pin `<id>[1m]` → ~1M client window. The agy Claude 4.6 models were
verified to accept a 250k-token prompt over `/v1/messages` (not capped at 200k; native
1M); Gemini is natively 1,048,576. If subagent model resolution strips `[1m]`
(anthropics/claude-code#45169) the fallback is always safe (under-budget, never
overflow): claude- ids fall to Claude Code's ~200k catalog default, agy- ids to the
global `CLAUDE_CODE_MAX_CONTEXT_TOKENS` (500k, shared with grok).

## 6. Quota buckets and routing

Antigravity meters in **two shared buckets, not per-model**: {Claude Opus + Sonnet +
GPT-OSS} share one weekly + 5-hour limit; {Gemini Flash + Pro} share another. A
quota-fallback ladder must **hop buckets** - dropping opus→sonnet buys nothing when both
are capped. Opus can burn Google One AI credits after free-tier exhaustion
(`quota-exceeded.antigravity-credits: true`); Gemini rides free quota.

Routing: **grok-4.6 routes first**; **Claude Sonnet subagents are the fallback**; **Codex is DISABLED**;
use the **agy (Gemini) ladder on grok-exhaustion or explicit request** (owner: grok-4.6 > agy Gemini). Only the Gemini subagents are wired - the Claude/GPT bucket's limits are too low.
Capability order gemini-3.1-pro > gemini-3.5-flash,
with the owner's rule of thumb: gemini-3.5-flash = speedy ops, gemini-3.1-pro =
slower/harder (Flash actually edges Pro on agentic-coding throughput benchmarks).

## 7. Reload note

New agent files don't appear in an already-running interactive session until
`/reload-plugins` (or a restart). Fresh `claude -p` invocations and harness workers pick
them up automatically. The agent `.md` files live in `~/.claude/agents/agy-*.md`
(junction-shared into `~/.claude-clx`); `install-windows.ps1` deploys them from
`plugin/agents/`.

## Minimum version / the malformed-HTTP-200 fix

This doc requires CLIProxyAPI **v7.2.90 or newer** (we run **v7.2.91**). The earlier intermittent agy-Gemini failure (`API Error: API returned an empty or malformed response (HTTP 200)`) was CLIProxyAPI bug [GH#4431](https://github.com/router-for-me/CLIProxyAPI/issues/4431): Antigravity->Gemini sometimes returned HTTP 200 with an empty candidate (`parts:[{"text":""}]`, `finishReason STOP`), and the proxy's Claude-format translator then emitted a truncated/invalid stream (`message_start` with empty content, then no `message_stop`). Upstream 200 meant request-retry never fired. Fixed by commit `cd98e9d7`, first shipped in v7.2.90; local upgrade 7.2.88 -> 7.2.91 on 2026-07-19 dropped the malformed-200 rate on `agy-gemini-3-1-pro` from ~37% to 0 across 57 calls. Residual (separate, lower severity): an occasional upstream hang (request sits the full timeout), likely latency or quota-bucket strain; it is retryable and must not be conflated with the fixed bug.

## Memory capture (claude-mem)

Native agy subagents fire NO `claude-mem` hooks - they are covered only by the parent Claude Code session's memory capture. By contrast, headless `claude_worker` runs execute under `~/.claude-clx` (claude-mem enabled) and their hooks fire natively. The legacy visible-window agy CLI worker also fires no hooks.
