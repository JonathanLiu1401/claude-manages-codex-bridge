# Model updates: hand-edited again

`sync-models.ps1` is gone, along with the local gateway it was built around.
`-Discover` and `-Verify` worked by reading the gateway's `/v1/models` catalog and
probing `POST /v1/messages`, and most of what it kept in sync (the `clx` world's
settings, the `cld` launcher config, the native `grok` / `agy-*` agent files) no
longer exists either. What is left is small enough to edit by hand.

## models.json

Still the manifest of record, but nothing consumes it automatically now. `id` is the
wire id; `window` is the client-side context suffix (`[1m]` for a 1M window, empty
for none).

```json
{
  "roles": {
    "opus":   { "id": "claude-opus-5", "window": "[1m]" }
  },
  "bindings": { "worker_default": "opus", "advisor": "opus",
                "advisor_alias_form": true }
}
```

- **`advisor_alias_form: true`** means `advisorModel` is written as the literal tier alias
  (`"opus"`) rather than a resolved id. The alias auto-follows
  `ANTHROPIC_DEFAULT_OPUS_MODEL`, so `advisorModel` never needs touching on a model bump.
- The file still carries `grok`, `agy-pro`, and `agy-flash` roles plus a `custom_slot`
  binding. Those were gateway-served models and the picker slot that held one of them.
  They are dead entries; ignore them.

## Where to edit on a model bump

| # | Target | Why it matters |
|---|---|---|
| T1 | `~\.claude\settings.json` | tier slots (`ANTHROPIC_DEFAULT_*_MODEL`), advisor |
| T4 | `visible_agent_bridge.py` (repo + `~\.agent-bridge\`) | `start_claude_worker` default model |

Targets that exist in two places must be changed in both.

## Repo-vs-deployed drift

`install-windows.ps1` **copies** files to their live locations rather than linking them, so
editing the repo does not change what actually runs until you re-install. That drift is
invisible and has real consequences: it once left `~\.agent-bridge\visible_agent_bridge.py`
pinned to a superseded model while the repo looked correct. Compare both sides by hash
after a bump.

Copies are deliberate, not a bug to "fix" with junctions: a junction into a git worktree
means `git checkout` silently mutates the live runtime mid-session.
