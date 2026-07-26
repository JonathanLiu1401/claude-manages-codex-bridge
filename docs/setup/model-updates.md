# Model updates: one manifest, one command

Adding or upgrading a model used to mean hand-editing ~6 functional locations spread
across the repo AND three separately-deployed copies, buried in ~200 prose mentions of
model ids. That is what `models.json` + `sync-models.ps1` replace.

## The normal flow

```powershell
# 1. see if anything newer is being served
.\sync-models.ps1 -Discover

# 2. edit models.json (or let -Adopt do it), then push it everywhere
.\sync-models.ps1 -Apply

# 3. prove the pinned models actually answer
.\sync-models.ps1 -Verify
```

## models.json

Single source of truth. `id` is the wire id; `window` is the client-side context suffix
(`[1m]` for a 1M window, empty for none).

```json
{
  "roles": {
    "opus":   { "id": "claude-opus-5", "window": "[1m]" },
    "grok":   { "id": "grok-4.5",      "window": "" }
  },
  "bindings": { "worker_default": "opus", "advisor": "opus",
                "custom_slot": "grok", "advisor_alias_form": true }
}
```

- **grok stays bare on purpose.** Its real window is ~500k; a `[1m]` pin would let a
  session grow past what the upstream accepts and fail there instead of autocompacting.
- **`advisor_alias_form: true`** means `advisorModel` is written as the literal tier alias
  (`"opus"`) rather than a resolved id. The alias auto-follows
  `ANTHROPIC_DEFAULT_OPUS_MODEL`, so `advisorModel` never needs touching on a model bump.

## Modes

| Mode | Writes? | What it does |
|---|---|---|
| `-Check` (default) | no | Drift table across every target. Exit 1 if any drift, else 0. |
| `-Apply` | yes | Fixes the drift. Add `-Adopt` to also promote newer models into models.json first. |
| `-Discover` | no | Diffs the live `/v1/models` catalog against what is pinned. |
| `-Verify` | no | Live `POST /v1/messages` probe per distinct model. Exit 1 on any failure. |
| `-Doctor` | no | SHA256 repo-vs-deployed comparison for the copied artifacts. |
| `-InstallHook` | yes | Installs the quiet SessionStart discovery hook. Idempotent. |

## Targets it manages

| # | Target | Why it matters |
|---|---|---|
| T1 | `~\.claude\settings.json` | tier slots, advisor, custom picker slot |
| T2 | `~\.claude-clx\settings.json` | the `clx` proxy world |
| T3 | repo `launchers\force-direct.json` | source of the `cld` launcher config |
| T6 | `~\.claude-direct\force-direct.json` | **deployed** `cld` config - drifts independently |
| T4 | `visible_agent_bridge.py` (repo + `~\.agent-bridge\`) | `start_claude_worker` default model |
| T5 | `plugin\agents\*.md` (repo + `~\.claude\agents\`) | native subagent `model:` pins |

Targets that exist in two places are checked in both. Missing deployed paths are reported
as SKIP, not an error.

## Why -Doctor exists

`install-windows.ps1` **copies** files to their live locations rather than linking them, so
editing the repo does not change what actually runs until you re-install. That drift is
invisible and has real consequences: it once left `~\.agent-bridge\visible_agent_bridge.py`
pinned to a superseded model while the repo looked correct. `-Doctor` hashes both sides and
reports STALE.

Copies are deliberate, not a bug to "fix" with junctions: a junction into a git worktree
means `git checkout` silently mutates the live runtime mid-session.

## Discovery rules (why it will not just grab the newest string)

- **Dated snapshots are excluded from promotion.** The catalog mixes `claude-opus-5` with
  `claude-opus-4-1-20250805`. Sorting naively ranks the dated snapshot higher because
  `20250805` is a large number. Ids matching a trailing `-\d{8}` are skipped, and versions
  are compared as int tuples: `opus-4-8` -> `(4,8)`, `opus-5` -> `(5,0)`.
- **Only Claude families are version-compared** (opus / sonnet / haiku / fable).
- **grok and agy are informational only.** The `agy-*` ids are hand-authored aliases in
  `config.yaml` (`oauth-model-alias.antigravity` + `force-mapping`). A newer catalog entry
  is not a drop-in upgrade: adopting it blindly writes an id the alias layer does not route,
  and `config.yaml` needs a proxy restart regardless. Repoint those by hand - see
  `agy-antigravity.md`.
- **Discovery proposes, it never silently adopts.** The gateway serves models you may not
  be entitled to, plus previews and image/video models. Promotion happens only on explicit
  `-Apply -Adopt`.

## SessionStart hook

`-InstallHook` adds a SessionStart hook that runs `-Discover -Quiet`. It prints nothing
when everything is current, emits one line when an upgrade exists, has a short timeout, and
exits 0 silently if the proxy is unreachable - a hook that talks every session gets ignored.

## Safety properties

- JSON targets are edited by targeted value replacement, never a `ConvertTo-Json`
  round-trip (which would reformat live user config and can mangle unicode escapes).
- Every written file is re-parsed afterwards; on a parse failure the original is restored
  from memory and an error is reported.
- Files are written UTF-8 **without BOM** (PowerShell 5.1 reads a BOM-less file as ANSI;
  a BOM plus non-ASCII punctuation is how config files get corrupted here).
