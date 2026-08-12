#requires -Version 5.1
<#
Model manifest sync tool for multi-agentic-harness.

Single source of truth is models.json (repo root, next to this script). Edit
that file, then run this script to check or apply drift across every place a
model id is hand-coded today (repo files and separately-deployed copies).

Modes (pick one; -Check is the default when no switch is given):
  -Check   Read-only. Print a drift table. Exit 0 if everything matches,
           exit 1 if any target has drift or an error.
  -Apply   Same scan as -Check, but write fixes for anything that is out of
           sync. Verifies each JSON file still parses after writing; if a
           post-write parse check fails, the original file is restored and
           an ERROR line is printed instead of leaving a broken file behind.
  -Verify  Live-probe every distinct model id in the manifest through the
           local proxy (reads C:\Users\jonny\.agent-bridge\proxy.json).
  -Doctor  Compare SHA256 of repo-vs-deployed copies for the artifacts that
           get hand-copied around (visible_agent_bridge.py,
           claude_worker_runner.py, plugin agent .md files, the
           claude-manages-codex SKILL.md). Prints IN-SYNC or STALE per file.
  -Discover  Read-only. Query the proxy's live model catalog (/v1/models)
           and compare it against what is pinned in models.json for the
           opus/sonnet/fable Claude families. Never writes. Always exits 0.
           Add -Quiet to print nothing unless an upgrade is available (used
           by the installed SessionStart hook).
  -InstallHook  Add a quiet SessionStart hook to ~\.claude\settings.json that
           runs "-Discover -Quiet" at session start. Idempotent.

-Apply can be combined with -Adopt: before applying, promote the newest
eligible opus/sonnet/fable id from the catalog into models.json (preserving
each role's window string), then run the normal full apply. grok and the
agy-* roles are never auto-adopted (their ids are hand-authored aliases in
CLIProxyAPI's config.yaml, not drop-in catalog ids).

Usage:
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -Check
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -Apply
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -Apply -Adopt
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -Verify
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -Doctor
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -Discover
  powershell -ExecutionPolicy Bypass -File sync-models.ps1 -InstallHook

Notes:
  - Targets that do not exist on this machine (a deployed copy that was
    never installed here) are reported as SKIP, not an error.
  - JSON targets (settings.json / force-direct.json) are edited with
    targeted regex replacement of only the matching key's string value.
    They are never round-tripped through ConvertTo-Json, so formatting,
    ordering, unrelated keys, and unicode escapes are preserved exactly.
  - All files this script writes are UTF-8 without a byte order mark, via
    [System.IO.File]::WriteAllText(path, text, (New-Object
    System.Text.UTF8Encoding $false)). All files this script reads are read
    with [System.IO.File]::ReadAllText, never Get-Content -Raw, so a no-BOM
    UTF-8 file (for example one containing a middle dot, U+00B7) round-trips
    correctly on PowerShell 5.1 instead of being decoded as ANSI.
#>

param(
    [switch]$Check,
    [switch]$Apply,
    [switch]$Verify,
    [switch]$Doctor,
    [switch]$Discover,
    # Only meaningful together with -Apply: promote the newest eligible
    # Claude-family model id (opus/sonnet/fable only, never grok/agy) into
    # models.json before running the normal full apply.
    [switch]$Adopt,
    # Only meaningful together with -Discover: suppress all output unless an
    # UPGRADE-AVAILABLE is found. Used by the installed SessionStart hook so
    # a normal session start is silent.
    [switch]$Quiet,
    [switch]$InstallHook,
    # Internal test seam only: dot-source this script with -LoadOnly to get
    # every function defined in the caller's scope without running the mode
    # dispatch or exiting the process. Not part of the supported CLI surface.
    [switch]$LoadOnly
)

$ErrorActionPreference = 'Stop'

if (-not ($Check -or $Apply -or $Verify -or $Doctor -or $Discover -or $InstallHook)) {
    $Check = $true
}

$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$ManifestPath = Join-Path $RepoRoot 'models.json'
$HomeDir = $HOME

$script:ExitCode = 0

# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

function New-Result {
    param(
        [string]$Status,
        [string]$Target,
        [string]$Detail = ''
    )
    return [PSCustomObject]@{ Status = $Status; Target = $Target; Detail = $Detail }
}

function Format-ResultLine {
    param($Result)
    if ($Result.Detail) {
        return ("{0,-6} {1,-58} {2}" -f $Result.Status, $Result.Target, $Result.Detail)
    }
    return ("{0,-6} {1}" -f $Result.Status, $Result.Target)
}

function Write-Summary {
    param($Results)
    # Wrap every Where-Object result in @(...): if exactly one item matches,
    # PowerShell unwraps it to a bare PSCustomObject with no .Count property
    # at all, which would silently print a blank instead of "1".
    $ok = @($Results | Where-Object { $_.Status -eq 'OK' }).Count
    $drift = @($Results | Where-Object { $_.Status -eq 'DRIFT' }).Count
    $fixed = @($Results | Where-Object { $_.Status -eq 'FIXED' }).Count
    $skip = @($Results | Where-Object { $_.Status -eq 'SKIP' }).Count
    $err = @($Results | Where-Object { $_.Status -eq 'ERROR' }).Count
    Write-Output ("Summary: {0} OK, {1} DRIFT, {2} FIXED, {3} SKIP, {4} ERROR ({5} checks total)" -f $ok, $drift, $fixed, $skip, $err, @($Results).Count)
}

function Get-FileHashSafe {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

# ---------------------------------------------------------------------------
# Manifest loading (no ConvertFrom-Json -AsHashtable; that flag is PS6+ only)
# ---------------------------------------------------------------------------

function ConvertTo-PlainHashtable {
    param($InputObject)
    $ht = @{}
    if ($null -eq $InputObject) { return $ht }
    foreach ($prop in $InputObject.psobject.Properties) {
        $val = $prop.Value
        if ($val -is [System.Management.Automation.PSCustomObject]) {
            $ht[$prop.Name] = ConvertTo-PlainHashtable $val
        } else {
            $ht[$prop.Name] = $val
        }
    }
    return $ht
}

function Get-Manifest {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Output ("ERROR: manifest not found at " + $Path)
        exit 1
    }
    $raw = [System.IO.File]::ReadAllText($Path)
    try {
        $obj = $raw | ConvertFrom-Json
    } catch {
        Write-Output ("ERROR: failed to parse models.json: " + $_.Exception.Message)
        exit 1
    }
    if (-not $obj.roles) {
        Write-Output "ERROR: models.json is missing a top-level 'roles' section"
        exit 1
    }
    if (-not $obj.bindings) {
        Write-Output "ERROR: models.json is missing a top-level 'bindings' section"
        exit 1
    }
    $rolesHt = ConvertTo-PlainHashtable $obj.roles
    $bindingsHt = ConvertTo-PlainHashtable $obj.bindings
    return [PSCustomObject]@{ Roles = $rolesHt; Bindings = $bindingsHt }
}

function Resolve-RoleFull {
    param([hashtable]$RolesHt, [string]$RoleName)
    if (-not $RolesHt.ContainsKey($RoleName)) {
        throw ("models.json has no role named '" + $RoleName + "'")
    }
    $role = $RolesHt[$RoleName]
    $id = [string]$role['id']
    $window = [string]$role['window']
    return ($id + $window)
}

function Resolve-RoleBare {
    param([hashtable]$RolesHt, [string]$RoleName)
    if (-not $RolesHt.ContainsKey($RoleName)) {
        throw ("models.json has no role named '" + $RoleName + "'")
    }
    $role = $RolesHt[$RoleName]
    $id = [string]$role['id']
    # Defensive: strip a bracket window suffix even though role ids are
    # already stored bare in the manifest, in case a future edit combines them.
    return ($id -replace '\[[^\]]*\]$', '')
}

# ---------------------------------------------------------------------------
# JSON key targeted regex sync (T1, T2, T3)
# ---------------------------------------------------------------------------

function Sync-JsonTarget {
    param(
        [string]$Label,
        [string]$Path,
        $KeyMap,
        [bool]$ApplyMode
    )
    $results = New-Object System.Collections.ArrayList
    if (-not (Test-Path -LiteralPath $Path)) {
        [void]$results.Add((New-Result 'SKIP' $Label 'path not found on this machine, skipping (not an error)'))
        return $results
    }

    $original = [System.IO.File]::ReadAllText($Path)
    $working = $original
    $changedAny = $false

    foreach ($key in $KeyMap.Keys) {
        $desired = [string]$KeyMap[$key]
        $targetLabel = $Label + ' : ' + $key

        $existsPattern = '"' + [regex]::Escape($key) + '"\s*:'
        $existsMatches = [regex]::Matches($working, $existsPattern)

        if ($existsMatches.Count -eq 0) {
            [void]$results.Add((New-Result 'SKIP' $targetLabel 'key not present in file, skipping (not an error)'))
            continue
        }
        if ($existsMatches.Count -gt 1) {
            [void]$results.Add((New-Result 'ERROR' $targetLabel ('key appears ' + $existsMatches.Count + ' times in file; ambiguous, skipped for safety')))
            continue
        }

        $stringValuePattern = '"' + [regex]::Escape($key) + '"\s*:\s*"([^"]*)"'
        $valueMatch = [regex]::Match($working, $stringValuePattern)
        if (-not $valueMatch.Success) {
            [void]$results.Add((New-Result 'ERROR' $targetLabel 'key present but its value is not a plain JSON string; skipped for safety'))
            continue
        }

        $current = $valueMatch.Groups[1].Value
        if ($current -eq $desired) {
            [void]$results.Add((New-Result 'OK' $targetLabel ''))
            continue
        }
        if (-not $ApplyMode) {
            [void]$results.Add((New-Result 'DRIFT' $targetLabel ($current + ' -> ' + $desired)))
            continue
        }

        $safeDesired = $desired -replace '\$', '$$$$'
        $replPattern = '("' + [regex]::Escape($key) + '"\s*:\s*")[^"]*(")'
        $rx = New-Object System.Text.RegularExpressions.Regex($replPattern)
        $working = $rx.Replace($working, ('${1}' + $safeDesired + '${2}'), 1)
        $changedAny = $true
        [void]$results.Add((New-Result 'FIXED' $targetLabel ($current + ' -> ' + $desired)))
    }

    if ($ApplyMode -and $changedAny) {
        [System.IO.File]::WriteAllText($Path, $working, (New-Object System.Text.UTF8Encoding($false)))
        $verifyOk = $true
        try {
            $reread = [System.IO.File]::ReadAllText($Path)
            $null = $reread | ConvertFrom-Json
        } catch {
            $verifyOk = $false
        }
        if (-not $verifyOk) {
            [System.IO.File]::WriteAllText($Path, $original, (New-Object System.Text.UTF8Encoding($false)))
            # The write was rolled back: any 'FIXED' lines already queued for
            # this target are no longer true. Downgrade them to ERROR so the
            # printed report never shows FIXED for a change that did not stick.
            for ($i = 0; $i -lt $results.Count; $i++) {
                if ($results[$i].Status -eq 'FIXED') {
                    $results[$i] = New-Result 'ERROR' $results[$i].Target ('rolled back (' + $results[$i].Detail + ')')
                }
            }
            [void]$results.Add((New-Result 'ERROR' $Label 'post-write JSON parse check failed; original file restored, no changes kept'))
        }
    }

    return $results
}

# ---------------------------------------------------------------------------
# Single-value regex sync for non-JSON text targets (T4 python literal, T5
# markdown frontmatter "model:" line). Pattern must define named groups
# <pre>, <val>, <post>.
# ---------------------------------------------------------------------------

function Sync-TextLiteralTarget {
    param(
        [string]$Label,
        [string]$Path,
        [string]$Pattern,
        [string]$Desired,
        [bool]$ApplyMode
    )
    $results = New-Object System.Collections.ArrayList
    if (-not (Test-Path -LiteralPath $Path)) {
        [void]$results.Add((New-Result 'SKIP' $Label 'path not found on this machine, skipping (not an error)'))
        return $results
    }

    $original = [System.IO.File]::ReadAllText($Path)
    $rx = New-Object System.Text.RegularExpressions.Regex($Pattern)
    $m = $rx.Match($original)
    if (-not $m.Success) {
        [void]$results.Add((New-Result 'ERROR' $Label 'expected pattern not found in file; skipped for safety'))
        return $results
    }

    $current = $m.Groups['val'].Value
    if ($current -eq $Desired) {
        [void]$results.Add((New-Result 'OK' $Label ''))
        return $results
    }
    if (-not $ApplyMode) {
        [void]$results.Add((New-Result 'DRIFT' $Label ($current + ' -> ' + $Desired)))
        return $results
    }

    $safeDesired = $Desired -replace '\$', '$$$$'
    $replacement = '${pre}' + $safeDesired + '${post}'
    $working = $rx.Replace($original, $replacement, 1)
    [System.IO.File]::WriteAllText($Path, $working, (New-Object System.Text.UTF8Encoding($false)))

    $reread = [System.IO.File]::ReadAllText($Path)
    $m2 = $rx.Match($reread)
    if ((-not $m2.Success) -or ($m2.Groups['val'].Value -ne $Desired)) {
        [System.IO.File]::WriteAllText($Path, $original, (New-Object System.Text.UTF8Encoding($false)))
        [void]$results.Add((New-Result 'ERROR' $Label 'post-write verify failed; original file restored, no changes kept'))
        return $results
    }

    [void]$results.Add((New-Result 'FIXED' $Label ($current + ' -> ' + $Desired)))
    return $results
}

# ---------------------------------------------------------------------------
# Target list for -Check / -Apply
# ---------------------------------------------------------------------------

function Invoke-ModelSync {
    param(
        [bool]$ApplyMode,
        [hashtable]$RolesHt,
        [hashtable]$BindingsHt,
        [string]$RepoRoot,
        [string]$HomeDir
    )

    # advisorModel can be pinned as a full resolved id+window, or (owner
    # decision) as a bare "tier alias" like "opus" that Claude Code resolves
    # against ANTHROPIC_DEFAULT_OPUS_MODEL itself, so it never needs editing
    # again on a model bump. models.json controls which form is desired via
    # bindings.advisor_alias_form.
    $advisorRoleName = [string]$BindingsHt['advisor']
    $advisorAliasForm = $false
    if ($BindingsHt.ContainsKey('advisor_alias_form')) {
        $advisorAliasForm = [bool]$BindingsHt['advisor_alias_form']
    }
    if ($advisorAliasForm) {
        $advisorDesired = $advisorRoleName
    } else {
        $advisorDesired = Resolve-RoleFull $RolesHt $advisorRoleName
    }

    $keyMapFull = [ordered]@{
        'ANTHROPIC_DEFAULT_OPUS_MODEL'   = Resolve-RoleFull $RolesHt 'opus'
        'ANTHROPIC_DEFAULT_SONNET_MODEL' = Resolve-RoleFull $RolesHt 'sonnet'
        'ANTHROPIC_DEFAULT_FABLE_MODEL'  = Resolve-RoleFull $RolesHt 'fable'
        'advisorModel'                   = $advisorDesired
        'ANTHROPIC_CUSTOM_MODEL_OPTION'  = Resolve-RoleBare $RolesHt ([string]$BindingsHt['custom_slot'])
    }
    $keyMapThree = [ordered]@{
        'ANTHROPIC_DEFAULT_OPUS_MODEL'   = Resolve-RoleFull $RolesHt 'opus'
        'ANTHROPIC_DEFAULT_SONNET_MODEL' = Resolve-RoleFull $RolesHt 'sonnet'
        'ANTHROPIC_DEFAULT_FABLE_MODEL'  = Resolve-RoleFull $RolesHt 'fable'
    }

    $results = New-Object System.Collections.ArrayList

    # T1
    $results.AddRange(@(Sync-JsonTarget -Label 'T1 ~\.claude\settings.json' -Path (Join-Path $HomeDir '.claude\settings.json') -KeyMap $keyMapFull -ApplyMode $ApplyMode))
    # T2 (no ANTHROPIC_CUSTOM_MODEL_OPTION key there today; that key falls
    # through to SKIP automatically, it is never injected)
    $results.AddRange(@(Sync-JsonTarget -Label 'T2 ~\.claude-clx\settings.json' -Path (Join-Path $HomeDir '.claude-clx\settings.json') -KeyMap $keyMapFull -ApplyMode $ApplyMode))
    # T3 (repo copy)
    $results.AddRange(@(Sync-JsonTarget -Label 'T3 repo launchers\force-direct.json' -Path (Join-Path $RepoRoot 'launchers\force-direct.json') -KeyMap $keyMapThree -ApplyMode $ApplyMode))
    # T6 (the `cld` launcher's deployed force-direct.json; first-class target,
    # not folded into T3, since it is a separately-deployed copy)
    $results.AddRange(@(Sync-JsonTarget -Label 'T6 ~\.claude-direct\force-direct.json (cld launcher)' -Path (Join-Path $HomeDir '.claude-direct\force-direct.json') -KeyMap $keyMapThree -ApplyMode $ApplyMode))

    # T4
    $workerDefaultBare = Resolve-RoleBare $RolesHt ([string]$BindingsHt['worker_default'])
    $t4Pattern = '(?<pre>CLAUDE_WORKER_DEFAULT_MODEL\s*=\s*os\.environ\.get\("BRIDGE_CLAUDE_WORKER_MODEL",\s*""\)\.strip\(\)\s*or\s*")(?<val>[^"]*)(?<post>")'
    $results.AddRange(@(Sync-TextLiteralTarget -Label 'T4 repo visible_agent_bridge.py' -Path (Join-Path $RepoRoot 'visible_agent_bridge.py') -Pattern $t4Pattern -Desired $workerDefaultBare -ApplyMode $ApplyMode))
    $results.AddRange(@(Sync-TextLiteralTarget -Label 'T4 deployed ~\.agent-bridge\visible_agent_bridge.py' -Path (Join-Path $HomeDir '.agent-bridge\visible_agent_bridge.py') -Pattern $t4Pattern -Desired $workerDefaultBare -ApplyMode $ApplyMode))

    # T5
    $t5Pattern = '(?m)^(?<pre>model:\s*)(?<val>\S+)(?<post>)'
    $t5Files = @(
        @{ Name = 'grok.md'; Role = 'grok' },
        @{ Name = 'agy-gemini-3-1-pro.md'; Role = 'agy-pro' },
        @{ Name = 'agy-gemini-3-6-flash.md'; Role = 'agy-flash' }
    )
    foreach ($f in $t5Files) {
        $desired = Resolve-RoleFull $RolesHt $f.Role
        $repoPath = Join-Path $RepoRoot ('plugin\agents\' + $f.Name)
        $depPath = Join-Path $HomeDir ('.claude\agents\' + $f.Name)
        $results.AddRange(@(Sync-TextLiteralTarget -Label ('T5 repo plugin\agents\' + $f.Name) -Path $repoPath -Pattern $t5Pattern -Desired $desired -ApplyMode $ApplyMode))
        $results.AddRange(@(Sync-TextLiteralTarget -Label ('T5 deployed ~\.claude\agents\' + $f.Name) -Path $depPath -Pattern $t5Pattern -Desired $desired -ApplyMode $ApplyMode))
    }

    return $results
}

# ---------------------------------------------------------------------------
# -Doctor : repo-vs-deployed file drift for hand-copied artifacts
# ---------------------------------------------------------------------------

function Compare-DoctorPair {
    param([string]$Label, [string]$RepoPath, [string]$DeployPath)
    $rh = Get-FileHashSafe $RepoPath
    $dh = Get-FileHashSafe $DeployPath
    if ((-not $rh) -and (-not $dh)) {
        return New-Result 'SKIP' $Label 'neither repo nor deployed copy found'
    }
    if (-not $rh) {
        return New-Result 'SKIP' $Label 'repo copy not found'
    }
    if (-not $dh) {
        return New-Result 'SKIP' $Label 'deployed copy not found on this machine (not an error)'
    }
    if ($rh -eq $dh) {
        return New-Result 'IN-SYNC' $Label ''
    }
    return New-Result 'STALE' $Label 'sha256 differs between repo copy and deployed copy'
}

function Invoke-Doctor {
    param([string]$RepoRoot, [string]$HomeDir)
    $results = New-Object System.Collections.ArrayList

    [void]$results.Add((Compare-DoctorPair -Label 'visible_agent_bridge.py' `
        -RepoPath (Join-Path $RepoRoot 'visible_agent_bridge.py') `
        -DeployPath (Join-Path $HomeDir '.agent-bridge\visible_agent_bridge.py')))

    [void]$results.Add((Compare-DoctorPair -Label 'claude_worker_runner.py' `
        -RepoPath (Join-Path $RepoRoot 'claude_worker_runner.py') `
        -DeployPath (Join-Path $HomeDir '.agent-bridge\claude_worker_runner.py')))

    foreach ($n in @('grok.md', 'agy-gemini-3-1-pro.md', 'agy-gemini-3-6-flash.md')) {
        [void]$results.Add((Compare-DoctorPair -Label ('plugin\agents\' + $n) `
            -RepoPath (Join-Path $RepoRoot ('plugin\agents\' + $n)) `
            -DeployPath (Join-Path $HomeDir ('.claude\agents\' + $n))))
    }

    [void]$results.Add((Compare-DoctorPair -Label 'plugin\skills\claude-manages-codex\SKILL.md' `
        -RepoPath (Join-Path $RepoRoot 'plugin\skills\claude-manages-codex\SKILL.md') `
        -DeployPath (Join-Path $HomeDir '.claude\skills\claude-manages-codex\skills\claude-manages-codex\SKILL.md')))

    return $results
}

# ---------------------------------------------------------------------------
# Shared proxy config reader (used by -Verify and -Discover)
# ---------------------------------------------------------------------------

function Get-ProxyConfig {
    param([string]$HomeDir)
    $proxyPath = Join-Path $HomeDir '.agent-bridge\proxy.json'
    if (-not (Test-Path -LiteralPath $proxyPath)) {
        return [PSCustomObject]@{ Ok = $false; BaseUrl = ''; ApiKey = ''; Path = $proxyPath; Error = 'proxy config not found at ' + $proxyPath }
    }
    try {
        $proxyRaw = [System.IO.File]::ReadAllText($proxyPath)
        $proxyObj = $proxyRaw | ConvertFrom-Json
    } catch {
        return [PSCustomObject]@{ Ok = $false; BaseUrl = ''; ApiKey = ''; Path = $proxyPath; Error = 'failed to parse proxy config: ' + $_.Exception.Message }
    }
    $baseUrl = [string]$proxyObj.base_url
    $apiKey = [string]$proxyObj.api_key
    if ((-not $baseUrl) -or (-not $apiKey)) {
        return [PSCustomObject]@{ Ok = $false; BaseUrl = ''; ApiKey = ''; Path = $proxyPath; Error = 'proxy config is missing base_url or api_key' }
    }
    return [PSCustomObject]@{ Ok = $true; BaseUrl = $baseUrl; ApiKey = $apiKey; Path = $proxyPath; Error = '' }
}

# ---------------------------------------------------------------------------
# -Verify : live-probe each distinct model id through the proxy
# ---------------------------------------------------------------------------

function Invoke-Verify {
    param([hashtable]$RolesHt)

    $proxyCfg = Get-ProxyConfig -HomeDir $HomeDir
    if (-not $proxyCfg.Ok) {
        Write-Output ("ERROR: " + $proxyCfg.Error)
        $script:ExitCode = 1
        return
    }
    $baseUrl = $proxyCfg.BaseUrl
    $apiKey = $proxyCfg.ApiKey

    $roleOrder = @('opus', 'sonnet', 'fable', 'grok', 'agy-pro', 'agy-flash')
    $idResults = @{}
    $anyFail = $false

    foreach ($roleName in $roleOrder) {
        if (-not $RolesHt.ContainsKey($roleName)) { continue }
        $bareId = Resolve-RoleBare $RolesHt $roleName
        if ($idResults.ContainsKey($bareId)) { continue }

        $status = 'FAIL'
        $echoed = ''
        $detail = ''
        try {
            $bodyObj = @{
                model = $bareId
                max_tokens = 16
                messages = @(@{ role = 'user'; content = 'ping' })
            }
            $json = $bodyObj | ConvertTo-Json -Depth 5
            $headers = @{ 'x-api-key' = $apiKey; 'anthropic-version' = '2023-06-01' }
            $uri = $baseUrl.TrimEnd('/') + '/v1/messages'
            $resp = Invoke-WebRequest -Uri $uri -Method Post -Headers $headers -ContentType 'application/json' -Body $json -UseBasicParsing -TimeoutSec 60
            $parsed = $resp.Content | ConvertFrom-Json
            $echoed = [string]$parsed.model
            $status = 'OK'
        } catch {
            $status = 'FAIL'
            $anyFail = $true
            $errMsg = $_.Exception.Message
            try {
                if ($_.Exception.Response) {
                    $stream = $_.Exception.Response.GetResponseStream()
                    $reader = New-Object System.IO.StreamReader($stream)
                    $errBody = $reader.ReadToEnd()
                    if ($errBody) {
                        $trimmed = $errBody
                        if ($trimmed.Length -gt 200) { $trimmed = $trimmed.Substring(0, 200) }
                        $errMsg = $errMsg + ' | ' + $trimmed
                    }
                }
            } catch {
                # ignore secondary failure reading the error body
            }
            $detail = $errMsg
        }
        $idResults[$bareId] = [PSCustomObject]@{ Status = $status; Echoed = $echoed; Detail = $detail }
    }

    Write-Output ("{0,-10} {1,-26} {2,-6} {3}" -f 'ROLE', 'MODEL ID', 'STATUS', 'ECHOED MODEL / ERROR')
    foreach ($roleName in $roleOrder) {
        if (-not $RolesHt.ContainsKey($roleName)) { continue }
        $bareId = Resolve-RoleBare $RolesHt $roleName
        $r = $idResults[$bareId]
        $tail = $r.Detail
        if ($r.Status -eq 'OK') { $tail = $r.Echoed }
        Write-Output ("{0,-10} {1,-26} {2,-6} {3}" -f $roleName, $bareId, $r.Status, $tail)
    }

    if ($anyFail) { $script:ExitCode = 1 }
}

# ---------------------------------------------------------------------------
# -Discover : compare the live catalog against models.json for the
# version-comparable Claude families (opus, sonnet, haiku, fable). grok and
# agy-* are informational only, never version-compared or auto-promoted:
# their ids are hand-authored aliases in CLIProxyAPI's config.yaml
# (oauth-model-alias.antigravity force-maps upstream names to
# agy-gemini-3-1-pro / agy-gemini-3-6-flash), so a newer catalog entry is not
# a drop-in id and adopting one would not even route through the alias layer.
# ---------------------------------------------------------------------------

function Test-IsDatedSnapshot {
    param([string]$Id)
    # Dated snapshots end in an 8-digit date, e.g. claude-opus-4-1-20250805.
    # These must never be promoted: naive "biggest trailing number" sorting
    # would let the date outrank a real version number like claude-opus-5,
    # and even correct tuple comparison could still be fooled by a future
    # preview snapshot of a newer major version. Excluding anything shaped
    # like a dated snapshot up front avoids both failure modes.
    return [regex]::IsMatch($Id, '-\d{8}$')
}

function Get-ClaudeFamilyVersionTuple {
    param([string]$Id, [string]$Family)
    $prefix = 'claude-' + $Family + '-'
    if (-not $Id.StartsWith($prefix)) { return $null }
    $remainder = $Id.Substring($prefix.Length)
    if (-not $remainder) { return $null }
    $parts = $remainder -split '-'
    $tuple = New-Object System.Collections.ArrayList
    foreach ($p in $parts) {
        $n = 0
        if (-not [int]::TryParse($p, [ref]$n)) {
            # A non-numeric token means this id does not cleanly fit the
            # "claude-<family>-<int>[-<int>...]" shape; do not guess.
            return $null
        }
        [void]$tuple.Add($n)
    }
    return $tuple
}

function Compare-VersionTuples {
    param($A, $B)
    # Element-wise compare; a missing trailing element counts as 0. Returns
    # 1 if A newer, -1 if A older, 0 if equal.
    $len = [Math]::Max($A.Count, $B.Count)
    for ($i = 0; $i -lt $len; $i++) {
        $av = 0
        $bv = 0
        if ($i -lt $A.Count) { $av = $A[$i] }
        if ($i -lt $B.Count) { $bv = $B[$i] }
        if ($av -gt $bv) { return 1 }
        if ($av -lt $bv) { return -1 }
    }
    return 0
}

function Get-NewestEligibleForFamily {
    param([array]$CatalogIds, [string]$Family)
    $best = $null
    $bestTuple = $null
    foreach ($id in $CatalogIds) {
        if (Test-IsDatedSnapshot $id) { continue }
        $tuple = Get-ClaudeFamilyVersionTuple -Id $id -Family $Family
        if ($null -eq $tuple) { continue }
        if ($null -eq $best) {
            $best = $id
            $bestTuple = $tuple
        } elseif ((Compare-VersionTuples $tuple $bestTuple) -gt 0) {
            $best = $id
            $bestTuple = $tuple
        }
    }
    return $best
}

function Get-FamilyUpgrade {
    param([array]$CatalogIds, [string]$Family, [string]$PinnedBareId)
    $newest = Get-NewestEligibleForFamily -CatalogIds $CatalogIds -Family $Family
    if (-not $newest) {
        return [PSCustomObject]@{ Newest = $PinnedBareId; Status = 'CURRENT' }
    }
    if ($newest -eq $PinnedBareId) {
        return [PSCustomObject]@{ Newest = $newest; Status = 'CURRENT' }
    }
    $pinnedTuple = Get-ClaudeFamilyVersionTuple -Id $PinnedBareId -Family $Family
    $newestTuple = Get-ClaudeFamilyVersionTuple -Id $newest -Family $Family
    if (($null -ne $pinnedTuple) -and ($null -ne $newestTuple) -and ((Compare-VersionTuples $newestTuple $pinnedTuple) -gt 0)) {
        return [PSCustomObject]@{ Newest = $newest; Status = 'UPGRADE-AVAILABLE' }
    }
    # Different id but not a recognized newer version (or pinned id does not
    # parse as this family's shape): do not claim an upgrade we cannot prove.
    return [PSCustomObject]@{ Newest = $PinnedBareId; Status = 'CURRENT' }
}

function Test-HookMarkerPresent {
    param([string]$Text)
    return ($Text.Contains('sync-models.ps1') -and $Text.Contains('-Discover') -and $Text.Contains('-Quiet'))
}

function Invoke-Discover {
    param([hashtable]$RolesHt, [bool]$QuietMode, [int]$TimeoutSec = 30)

    $proxyCfg = Get-ProxyConfig -HomeDir $HomeDir
    $catalogAnthropicIds = @()
    $catalogAllIds = @()
    $ok = $proxyCfg.Ok
    if ($ok) {
        try {
            $uri = $proxyCfg.BaseUrl.TrimEnd('/') + '/v1/models'
            $headers = @{ 'Authorization' = 'Bearer ' + $proxyCfg.ApiKey }
            $resp = Invoke-WebRequest -Uri $uri -Method Get -Headers $headers -UseBasicParsing -TimeoutSec $TimeoutSec
            $parsed = $resp.Content | ConvertFrom-Json
            $catalogAllIds = @($parsed.data | ForEach-Object { [string]$_.id })
            $catalogAnthropicIds = @($parsed.data | Where-Object { $_.owned_by -eq 'anthropic' } | ForEach-Object { [string]$_.id })
        } catch {
            $ok = $false
            $proxyCfg.Error = 'could not reach model catalog: ' + $_.Exception.Message
        }
    }

    $result = [PSCustomObject]@{ Ok = $ok; Rows = (New-Object System.Collections.ArrayList); AnyUpgrade = $false; Error = $proxyCfg.Error }
    if (-not $ok) {
        if (-not $QuietMode) {
            Write-Output ("ERROR: " + $result.Error + " (Discover is read-only and informational; nothing was changed.)")
        }
        return $result
    }

    $familyMap = @{ 'opus' = 'opus'; 'sonnet' = 'sonnet'; 'fable' = 'fable' }
    $roleOrder = @('opus', 'sonnet', 'fable', 'grok', 'agy-pro', 'agy-flash')

    foreach ($roleName in $roleOrder) {
        if (-not $RolesHt.ContainsKey($roleName)) { continue }
        $pinnedBare = Resolve-RoleBare $RolesHt $roleName
        if ($familyMap.ContainsKey($roleName)) {
            $u = Get-FamilyUpgrade -CatalogIds $catalogAnthropicIds -Family $familyMap[$roleName] -PinnedBareId $pinnedBare
            [void]$result.Rows.Add([PSCustomObject]@{ Role = $roleName; Pinned = $pinnedBare; Newest = $u.Newest; Status = $u.Status })
            if ($u.Status -eq 'UPGRADE-AVAILABLE') { $result.AnyUpgrade = $true }
        } else {
            $seen = $catalogAllIds -contains $pinnedBare
            if ($seen) {
                $note = 'seen in catalog, not auto-promotable (alias-mapped)'
            } else {
                $note = 'not seen in catalog (alias-mapped, informational only)'
            }
            [void]$result.Rows.Add([PSCustomObject]@{ Role = $roleName; Pinned = $pinnedBare; Newest = 'n/a'; Status = $note })
        }
    }

    return $result
}

# ---------------------------------------------------------------------------
# -InstallHook : add a quiet SessionStart hook that runs -Discover -Quiet
# ---------------------------------------------------------------------------

function Invoke-InstallHook {
    param([string]$RepoRoot, [string]$HomeDir)

    $settingsPath = Join-Path $HomeDir '.claude\settings.json'
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        Write-Output ("ERROR: " + $settingsPath + " not found; cannot install hook")
        $script:ExitCode = 1
        return
    }

    $original = [System.IO.File]::ReadAllText($settingsPath)

    if (Test-HookMarkerPresent $original) {
        Write-Output ("OK     hook already installed in " + $settingsPath + " (idempotent, no change made)")
        return
    }

    if ([regex]::IsMatch($original, '"hooks"\s*:')) {
        Write-Output ("ERROR: " + $settingsPath + " already has a 'hooks' key with different content; refusing to auto-merge an unrelated hooks block. Add the SessionStart hook by hand. No change made.")
        $script:ExitCode = 1
        return
    }

    $scriptPath = Join-Path $RepoRoot 'sync-models.ps1'
    $commandString = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '" -Discover -Quiet'
    $commandJsonLiteral = $commandString | ConvertTo-Json -Compress

    $template = @'
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "shell": "bash",
            "command": __COMMAND_JSON__,
            "timeout": 8
          }
        ]
      }
    ]
  },
'@
    $safeCommandJson = $commandJsonLiteral -replace '\$', '$$$$'
    $hooksFragment = $template -replace [regex]::Escape('__COMMAND_JSON__'), $safeCommandJson

    $firstBraceIndex = $original.IndexOf('{')
    if ($firstBraceIndex -lt 0) {
        Write-Output "ERROR: could not find an opening brace in settings.json; refusing to edit"
        $script:ExitCode = 1
        return
    }
    $insertPos = $firstBraceIndex + 1
    $working = $original.Substring(0, $insertPos) + "`n" + $hooksFragment + $original.Substring($insertPos)

    [System.IO.File]::WriteAllText($settingsPath, $working, (New-Object System.Text.UTF8Encoding($false)))

    $verifyOk = $true
    try {
        $reread = [System.IO.File]::ReadAllText($settingsPath)
        $null = $reread | ConvertFrom-Json
        if (-not (Test-HookMarkerPresent $reread)) { $verifyOk = $false }
    } catch {
        $verifyOk = $false
    }
    if (-not $verifyOk) {
        [System.IO.File]::WriteAllText($settingsPath, $original, (New-Object System.Text.UTF8Encoding($false)))
        Write-Output "ERROR: post-write verify failed after installing hook; original settings.json restored, no changes kept"
        $script:ExitCode = 1
        return
    }

    Write-Output ("FIXED  installed SessionStart hook into " + $settingsPath + " (runs: " + $commandString + ")")
}

# ---------------------------------------------------------------------------
# Mode dispatch (skipped when dot-sourced with -LoadOnly for internal tests)
# ---------------------------------------------------------------------------

if (-not $LoadOnly) {

if ($Adopt -and (-not $Apply)) {
    Write-Output "Note: -Adopt has no effect without -Apply; ignoring it for this run."
}

if ($Doctor) {
    $results = Invoke-Doctor -RepoRoot $RepoRoot -HomeDir $HomeDir
    foreach ($r in $results) { Write-Output (Format-ResultLine $r) }
    $inSync = @($results | Where-Object { $_.Status -eq 'IN-SYNC' }).Count
    $stale = @($results | Where-Object { $_.Status -eq 'STALE' }).Count
    $skip = @($results | Where-Object { $_.Status -eq 'SKIP' }).Count
    Write-Output ("Summary: {0} IN-SYNC, {1} STALE, {2} SKIP ({3} artifacts total)" -f $inSync, $stale, $skip, @($results).Count)
    if ($stale -gt 0) { $script:ExitCode = 1 }
}
elseif ($InstallHook) {
    Invoke-InstallHook -RepoRoot $RepoRoot -HomeDir $HomeDir
}
elseif ($Discover) {
    $manifest = Get-Manifest -Path $ManifestPath
    $discoverResult = Invoke-Discover -RolesHt $manifest.Roles -QuietMode ([bool]$Quiet) -TimeoutSec 30

    if ($Quiet) {
        # Quiet hook path: print nothing on the common (all-CURRENT) case.
        # Errors are already silent here (Invoke-Discover only prints its own
        # ERROR line when NOT in quiet mode), matching "never block or spam
        # session start; exit 0 silently if the proxy is unreachable".
        if ($discoverResult.Ok -and $discoverResult.AnyUpgrade) {
            foreach ($row in $discoverResult.Rows) {
                if ($row.Status -eq 'UPGRADE-AVAILABLE') {
                    Write-Output ("[sync-models] UPGRADE-AVAILABLE: " + $row.Role + " pinned=" + $row.Pinned + " newest=" + $row.Newest + " (run: sync-models.ps1 -Discover)")
                }
            }
        }
    } else {
        if ($discoverResult.Ok) {
            Write-Output ("{0,-10} {1,-26} {2,-26} {3}" -f 'ROLE', 'PINNED', 'NEWEST-ELIGIBLE', 'STATUS')
            foreach ($row in $discoverResult.Rows) {
                Write-Output ("{0,-10} {1,-26} {2,-26} {3}" -f $row.Role, $row.Pinned, $row.Newest, $row.Status)
            }
            Write-Output "To adopt: sync-models.ps1 -Apply -Adopt"
        }
    }
    # -Discover is always informational: exit 0 regardless of outcome.
    $script:ExitCode = 0
}
elseif ($Verify) {
    $manifest = Get-Manifest -Path $ManifestPath
    Invoke-Verify -RolesHt $manifest.Roles
}
elseif ($Apply) {
    if ($Adopt) {
        $preManifest = Get-Manifest -Path $ManifestPath
        $discoverResult = Invoke-Discover -RolesHt $preManifest.Roles -QuietMode $false -TimeoutSec 30
        if (-not $discoverResult.Ok) {
            Write-Output ("ERROR: -Adopt requested but the model catalog could not be reached (" + $discoverResult.Error + "); models.json was not changed.")
            $script:ExitCode = 1
        } else {
            $promotions = @($discoverResult.Rows | Where-Object { $_.Status -eq 'UPGRADE-AVAILABLE' })
            if (@($promotions).Count -eq 0) {
                Write-Output "Adopt: no eligible upgrades found for opus/sonnet/fable; models.json unchanged."
            } else {
                foreach ($p in $promotions) {
                    $rolePattern = '(?<pre>"' + [regex]::Escape($p.Role) + '"\s*:\s*\{\s*"id"\s*:\s*")(?<val>[^"]*)(?<post>")'
                    $adoptResults = Sync-TextLiteralTarget -Label ('Adopt models.json role ' + $p.Role) -Path $ManifestPath -Pattern $rolePattern -Desired $p.Newest -ApplyMode $true
                    foreach ($r in $adoptResults) {
                        if ($r.Status -eq 'FIXED') {
                            Write-Output ("Adopted: " + $p.Role + " : " + $p.Pinned + " -> " + $p.Newest)
                        } elseif ($r.Status -eq 'ERROR') {
                            Write-Output ("ERROR adopting " + $p.Role + ": " + $r.Detail)
                            $script:ExitCode = 1
                        }
                    }
                }
                try {
                    $null = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
                } catch {
                    Write-Output ("ERROR: models.json failed to parse after adoption: " + $_.Exception.Message)
                    $script:ExitCode = 1
                }
            }
        }
    }

    $manifest = Get-Manifest -Path $ManifestPath
    $results = Invoke-ModelSync -ApplyMode $true -RolesHt $manifest.Roles -BindingsHt $manifest.Bindings -RepoRoot $RepoRoot -HomeDir $HomeDir
    foreach ($r in $results) { Write-Output (Format-ResultLine $r) }
    Write-Summary $results
    $bad = @($results | Where-Object { ($_.Status -eq 'DRIFT') -or ($_.Status -eq 'ERROR') }).Count
    if ($bad -gt 0) { $script:ExitCode = 1 }
}
else {
    $manifest = Get-Manifest -Path $ManifestPath
    $results = Invoke-ModelSync -ApplyMode $false -RolesHt $manifest.Roles -BindingsHt $manifest.Bindings -RepoRoot $RepoRoot -HomeDir $HomeDir
    foreach ($r in $results) { Write-Output (Format-ResultLine $r) }
    Write-Summary $results
    $bad = @($results | Where-Object { ($_.Status -eq 'DRIFT') -or ($_.Status -eq 'ERROR') }).Count
    if ($bad -gt 0) { $script:ExitCode = 1 }
}

exit $script:ExitCode

}
