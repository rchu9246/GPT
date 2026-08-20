#requires -Version 5.1
<#
PHASE3721_PRODUCTION_PAPER_DAILY_OBSERVATION_AUTOMATION_SCHEDULE_INTEGRATION_FIX_DEPLOY.ps1

GPT Quant V9.2
Phase 3.7.2.1 — Production Paper Daily Observation Automation Schedule Integration Fix

Purpose
-------
Make the Production Paper observation chain truly unattended in GitHub Actions.

This package does NOT add trading capability.
It only integrates deterministic weekday schedules for:
  Phase 3.6.8  Daily Autonomous Operations Controller
  Phase 3.6.9  Daily Evidence + Lifecycle Governance
  Phase 3.7.0  Observation + Validation
  Phase 3.7.1  Daily Health + Acceptance Readiness
  Phase 3.7.2  Acceptance Promotion Controller

Schedule policy (Asia/Taipei)
-----------------------------
  20:45  Phase 3.6.8
  21:00  Phase 3.6.9
  21:15  Phase 3.7.0
  21:30  Phase 3.7.1
  21:45  Phase 3.7.2

Equivalent UTC cron:
  12:45, 13:00, 13:15, 13:30, 13:45 UTC, Mon-Fri

Safety
------
  PAPER ONLY
  Broker API: NO
  Broker credentials: NO
  Broker order submission: DISABLED
  Real-money trading: DISABLED
  Live-money release: NO
  Fail-closed: ENABLED

Created/overwritten
-------------------
  .github/workflows/gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml
  .github/workflows/gpt-quant-v92-paper-trading-phase369-production-paper-autonomous-daily-evidence-lifecycle-governance-engine.yml
  .github/workflows/gpt-quant-v92-paper-trading-phase370-production-paper-autonomous-operations-observation-validation.yml
  .github/workflows/gpt-quant-v92-paper-trading-phase371-production-paper-observation-daily-health-acceptance-readiness-monitor.yml
  .github/workflows/gpt-quant-v92-paper-trading-phase372-production-paper-observation-daily-automation-acceptance-promotion-controller.yml
#>

param(
    [switch]$AutoGit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 118) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Text" -ForegroundColor Red
    exit 1
}

function Read-Text([string]$Path) {
    if (-not (Test-Path $Path)) {
        Fail "Required workflow missing: $Path"
    }
    return Get-Content -LiteralPath $Path -Raw
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $enc)
}

function Replace-OnBlock([string]$Content, [string]$Cron, [string]$Comment) {
    $pattern = '(?ms)^on:\s*\r?\n(?:(?:[ \t]+.*\r?\n)|(?:\r?\n))*?(?=^[A-Za-z0-9_\-]+:|\z)'
    $replacement = @"
on:
  workflow_dispatch:

  schedule:
    # $Comment
    - cron: "$Cron"

"@
    if ([regex]::IsMatch($Content, $pattern)) {
        return [regex]::Replace($Content, $pattern, $replacement, 1)
    }

    # Fallback: insert after name if no canonical on block is found.
    $namePattern = '(?m)^(name:.*\r?\n)'
    if ([regex]::IsMatch($Content, $namePattern)) {
        return [regex]::Replace($Content, $namePattern, "`$1`r`n$replacement", 1)
    }

    Fail "Unable to locate workflow trigger block."
}

function Ensure-InputsPreserved([string]$Original, [string]$Updated) {
    # If workflow_dispatch inputs existed, preserve them by rebuilding an on block with them.
    $dispatchPattern = '(?ms)^on:\s*\r?\n[ \t]+workflow_dispatch:\s*\r?\n(?<body>(?:(?:[ \t]{4,}.*\r?\n)|\r?\n)*)'
    $m = [regex]::Match($Original, $dispatchPattern)
    if (-not $m.Success) {
        return $Updated
    }

    $body = $m.Groups["body"].Value
    if ([string]::IsNullOrWhiteSpace($body)) {
        return $Updated
    }

    $onPattern = '(?ms)^on:\s*\r?\n(?:(?:[ \t]+.*\r?\n)|(?:\r?\n))*?(?=^[A-Za-z0-9_\-]+:|\z)'
    $cronMatch = [regex]::Match($Updated, '(?m)^[ \t]+- cron:\s*"([^"]+)"')
    if (-not $cronMatch.Success) {
        return $Updated
    }
    $cron = $cronMatch.Groups[1].Value
    $commentMatch = [regex]::Match($Updated, '(?m)^[ \t]+# (.+)$')
    $comment = if ($commentMatch.Success) { $commentMatch.Groups[1].Value } else { "Scheduled weekday execution" }

    $replacement = "on:`r`n  workflow_dispatch:`r`n" + $body + "`r`n  schedule:`r`n    # $comment`r`n    - cron: `"$cron`"`r`n`r`n"
    return [regex]::Replace($Updated, $onPattern, $replacement, 1)
}

Section "GPT Quant V9.2 — Phase 3.7.2.1 Daily Observation Schedule Integration Fix"

$repo = $null
try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = $null
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this package from inside the GPT Git repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$targets = @(
    @{
        Phase = "3.6.8"
        Path = ".github/workflows/gpt-quant-v92-paper-trading-phase368-production-paper-daily-autonomous-operations-controller.yml"
        Cron = "45 12 * * 1-5"
        Comment = "20:45 Asia/Taipei, weekdays. Start daily autonomous paper controller."
    },
    @{
        Phase = "3.6.9"
        Path = ".github/workflows/gpt-quant-v92-paper-trading-phase369-production-paper-autonomous-daily-evidence-lifecycle-governance-engine.yml"
        Cron = "0 13 * * 1-5"
        Comment = "21:00 Asia/Taipei, weekdays. Runs after Phase 3.6.8."
    },
    @{
        Phase = "3.7.0"
        Path = ".github/workflows/gpt-quant-v92-paper-trading-phase370-production-paper-autonomous-operations-observation-validation.yml"
        Cron = "15 13 * * 1-5"
        Comment = "21:15 Asia/Taipei, weekdays. Runs after Phase 3.6.9."
    },
    @{
        Phase = "3.7.1"
        Path = ".github/workflows/gpt-quant-v92-paper-trading-phase371-production-paper-observation-daily-health-acceptance-readiness-monitor.yml"
        Cron = "30 13 * * 1-5"
        Comment = "21:30 Asia/Taipei, weekdays. Runs after Phase 3.7.0."
    },
    @{
        Phase = "3.7.2"
        Path = ".github/workflows/gpt-quant-v92-paper-trading-phase372-production-paper-observation-daily-automation-acceptance-promotion-controller.yml"
        Cron = "45 13 * * 1-5"
        Comment = "21:45 Asia/Taipei, weekdays. Runs after Phase 3.7.1."
    }
)

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repo ".phase3721-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

Section "Patching workflow schedules"

foreach ($target in $targets) {
    $path = Join-Path $repo $target.Path
    $original = Read-Text $path

    Copy-Item $path (Join-Path $backupRoot ([IO.Path]::GetFileName($path))) -Force

    $updated = Replace-OnBlock -Content $original -Cron $target.Cron -Comment $target.Comment
    $updated = Ensure-InputsPreserved -Original $original -Updated $updated

    Write-Utf8NoBom $path $updated
    Write-Host ("Phase {0} schedule patched: {1}" -f $target.Phase, $target.Cron) -ForegroundColor Green
}

Section "Validation"

foreach ($target in $targets) {
    $path = Join-Path $repo $target.Path
    $text = Get-Content -LiteralPath $path -Raw

    if (-not $text.Contains("workflow_dispatch")) {
        Fail "Phase $($target.Phase) lost workflow_dispatch."
    }

    if (-not $text.Contains("schedule:")) {
        Fail "Phase $($target.Phase) missing schedule."
    }

    if (-not $text.Contains("cron: `"$($target.Cron)`"")) {
        Fail "Phase $($target.Phase) cron mismatch."
    }
}

$combined = ($targets | ForEach-Object {
    Get-Content -LiteralPath (Join-Path $repo $_.Path) -Raw
}) -join "`n"

foreach ($forbidden in @(
    "broker_order_submission_enabled: true",
    "real_money_trading_enabled: true",
    "live_money_release_authorized: true"
)) {
    if ($combined.ToLowerInvariant().Contains($forbidden)) {
        Fail "Forbidden live capability detected: $forbidden"
    }
}

Write-Host "Workflow schedule presence scan: PASS" -ForegroundColor Green
Write-Host "Weekday sequencing scan: PASS" -ForegroundColor Green
Write-Host "Manual workflow_dispatch preservation scan: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green

Section "Schedule map"

Write-Host "Asia/Taipei weekday schedule:" -ForegroundColor Cyan
Write-Host "  20:45  Phase 3.6.8"
Write-Host "  21:00  Phase 3.6.9"
Write-Host "  21:15  Phase 3.7.0"
Write-Host "  21:30  Phase 3.7.1"
Write-Host "  21:45  Phase 3.7.2"
Write-Host ""
Write-Host "GitHub cron is UTC:" -ForegroundColor DarkGray
Write-Host "  12:45, 13:00, 13:15, 13:30, 13:45 UTC"

Section "Git status"
& git status --short

if ($AutoGit) {
    Section "Optional AutoGit"

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires current branch main; current=$branch"
    }

    foreach ($target in $targets) {
        & git add -- (Join-Path $repo $target.Path)
        if ($LASTEXITCODE -ne 0) {
            Fail "git add failed for Phase $($target.Phase)"
        }
    }

    $pending = (& git diff --cached --name-only)
    if ([string]::IsNullOrWhiteSpace(($pending -join "`n"))) {
        Write-Host "No staged Phase 3.7.2.1 schedule changes to commit." -ForegroundColor Yellow
    } else {
        & git commit -m "Fix Phase 3.7.2.1 daily observation automation schedules"
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed"
        }

        & git push origin main
        if ($LASTEXITCODE -ne 0) {
            Fail "git push origin main failed"
        }

        Write-Host "AutoGit commit + push: PASS" -ForegroundColor Green
    }
}

Section "DEPLOY COMPLETE"

Write-Host "Patched workflows:" -ForegroundColor Green
foreach ($target in $targets) {
    Write-Host ("  Phase {0}: {1}" -f $target.Phase, $target.Path)
}

Write-Host ""
Write-Host "Expected behavior after Push:" -ForegroundColor Cyan
Write-Host "  - No PC needs to remain powered on."
Write-Host "  - GitHub Actions runs the chain in the cloud on weekdays."
Write-Host "  - Phase 3.7.2 should show scheduled runs without manually pressing Run workflow."
Write-Host "  - Observation days accumulate only from actual daily evidence."
Write-Host ""
Write-Host "Important:" -ForegroundColor Yellow
Write-Host "  GitHub scheduled workflows can start a few minutes later than the exact cron time."
Write-Host "  Keep the main branch workflow files enabled."
Write-Host "  GitHub may disable scheduled workflows after long repository inactivity."
Write-Host ""
Write-Host "Safety:" -ForegroundColor Yellow
Write-Host "  PAPER ONLY"
Write-Host "  Broker API: NO"
Write-Host "  Broker credentials: NO"
Write-Host "  Broker order submission: DISABLED"
Write-Host "  Real-money trading: DISABLED"
Write-Host "  Live-money release: NO"
Write-Host "  Fail-closed: ENABLED"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Commit and Push these 5 workflow changes."
Write-Host "  2) Open each GitHub Action page and confirm it no longer says only workflow_dispatch."
Write-Host "  3) Phase 3.7.2 should show a schedule trigger in its workflow file."
Write-Host "  4) After confirmation, you may shut down the PC."
Write-Host "  5) On the next weekday, verify the first unattended chain run."
Write-Host ""
Write-Host "Backup: $backupRoot" -ForegroundColor DarkGray
