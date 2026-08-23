#requires -Version 5.1
<#
GPT Quant V9.2
Phase 3.7.2.6.1 V5
PostgREST Canonical Audit Table Resolution Fix

Fixes PGRST205 caused by the verifier still resolving:
  paper_post_recovery_activation_master_cycle_reconstruction_audit

instead of the canonical:
  paper_post_recovery_activation_master_cycle_reconstruction_audit_v92

This deployment:
- overwrites the Phase 37261 V3 verifier with a deterministic canonical verifier
- patches the reconstruction script's audit table literal to canonical _v92
- adds explicit runtime diagnostics
- does NOT alter historical rows
- does NOT enable broker/live-money capability
- requires no Supabase SQL
#>

param(
    [switch]$AutoGit
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 110) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 110) -ForegroundColor DarkCyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "PHASE37261_V5_FATAL: $Text" -ForegroundColor Red
    exit 1
}

function WriteUtf8([string]$Path, [string]$Text) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

Section "Phase 3.7.2.6.1 V5 — PostgREST Canonical Audit Table Resolution Fix"

try {
    $repo = (& git rev-parse --show-toplevel 2>$null).Trim()
} catch {
    $repo = ""
}

if ([string]::IsNullOrWhiteSpace($repo)) {
    Fail "Run this deployment from inside the GPT repository."
}

Set-Location $repo
Write-Host "Repository: $repo" -ForegroundColor Green

$automationDir = Join-Path $repo "automation\v92"
if (-not (Test-Path $automationDir)) {
    Fail "Missing automation\v92 directory."
}

$verifyPath = Join-Path $automationDir "paper_trading_phase37261_v3_reconstruction_audit_schema_recovery_verify.py"
$reconPath  = Join-Path $automationDir "paper_trading_phase37261_post_recovery_activation_master_cycle_canonical_state_reconstruction.py"

if (-not (Test-Path $reconPath)) {
    Fail "Missing Phase 3.7.2.6.1 reconstruction script: $reconPath"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase37261-v5-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

if (Test-Path $verifyPath) {
    Copy-Item $verifyPath (Join-Path $backup ([IO.Path]::GetFileName($verifyPath))) -Force
}
Copy-Item $reconPath (Join-Path $backup ([IO.Path]::GetFileName($reconPath))) -Force

Section "1/4 — Overwrite verifier with deterministic canonical PostgREST resolver"

$verifier = @'
#!/usr/bin/env python3
"""
GPT Quant V9.2
Phase 3.7.2.6.1 V5
PostgREST Canonical Audit Table Resolution Verification

Safety:
- read-only verification
- no historical rewrite
- no broker API
- no order submission
- no real-money trading
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CONTRACT = "PHASE37261_V5_POSTGREST_CANONICAL_AUDIT_TABLE_RESOLUTION_FIX"
CANONICAL_AUDIT_TABLE = (
    "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
)
LEGACY_AUDIT_TABLE = (
    "paper_post_recovery_activation_master_cycle_reconstruction_audit"
)

BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
HISTORICAL_REWRITE_ALLOWED = False


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    supabase_url = required_env("SUPABASE_URL").rstrip("/")
    service_key = required_env("SUPABASE_SERVICE_ROLE_KEY")

    # IMPORTANT:
    # The URL is built ONLY from CANONICAL_AUDIT_TABLE.
    # No legacy alias, fallback, inference, or alternate resolver is permitted.
    query = urllib.parse.urlencode({
        "select": "*",
        "limit": "1",
    })
    request_url = (
        f"{supabase_url}/rest/v1/{CANONICAL_AUDIT_TABLE}?{query}"
    )

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Accept": "application/json",
    }

    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V5")
    print("")
    print("## PostgREST Canonical Audit Table Resolution")
    print("")
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Verification Date: `{datetime.now(timezone.utc).date().isoformat()}`")
    print(f"- Resolved Audit Table: `{CANONICAL_AUDIT_TABLE}`")
    print(f"- Legacy Audit Table Allowed: **NO**")
    print(
        "- PostgREST Request Target: "
        f"`/rest/v1/{CANONICAL_AUDIT_TABLE}`"
    )
    print("- Verification Mode: **READ_ONLY**")
    print("- Historical Rewrite Allowed: **NO**")
    print("")

    if CANONICAL_AUDIT_TABLE == LEGACY_AUDIT_TABLE:
        raise RuntimeError("Canonical table unexpectedly equals legacy table.")

    req = urllib.request.Request(
        request_url,
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = response.getcode()

        if status < 200 or status >= 300:
            raise RuntimeError(f"Unexpected PostgREST HTTP status: {status}")

        try:
            rows = json.loads(body or "[]")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"PostgREST returned non-JSON response: {body[:500]}"
            ) from exc

        if not isinstance(rows, list):
            raise RuntimeError(
                "PostgREST canonical audit response was not a JSON array."
            )

        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **PASS**")
        print(f"- HTTP Status: **{status}**")
        print(f"- Canonical Rows Sampled: **{len(rows)}**")
        print("- Canonical Resolver: **LOCKED_TO_V92**")
        print("- PGRST205: **NOT_PRESENT**")
        print("")
        print("## Safety Boundary")
        print("")
        print("- Broker API Used: **NO**")
        print("- Broker Credentials Used: **NO**")
        print("- Broker Order Submission: **DISABLED**")
        print("- Real-money Trading: **DISABLED**")
        print("- Live-money Release Authorized: **NO**")
        return 0

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **FAIL**")
        print(f"- HTTP Status: **{exc.code}**")
        print(f"- Resolved Audit Table: `{CANONICAL_AUDIT_TABLE}`")
        print(
            "- Actual Request Target: "
            f"`/rest/v1/{CANONICAL_AUDIT_TABLE}`"
        )
        print("")
        print("```json")
        print(body[:4000])
        print("```")
        raise RuntimeError(
            "Canonical _v92 audit table is not visible through PostgREST: "
            f"HTTP {exc.code}: {body}"
        ) from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print(f"PHASE37261_V5_FATAL: {exc}", file=sys.stderr)
        raise
'@

WriteUtf8 $verifyPath $verifier
Write-Host "Verifier overwritten: $verifyPath" -ForegroundColor Green

Section "2/4 — Normalize reconstruction script to canonical _v92 audit table"

$recon = Get-Content -LiteralPath $reconPath -Raw

$legacyQuoted = '"paper_post_recovery_activation_master_cycle_reconstruction_audit"'
$canonicalQuoted = '"paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"'

$recon = $recon.Replace($legacyQuoted, $canonicalQuoted)

# Collapse accidental duplicate canonical candidate entries created by earlier replacements.
$duplicate = @'
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
'@
$single = @'
            "paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
'@
while ($recon.Contains($duplicate)) {
    $recon = $recon.Replace($duplicate, $single)
}

WriteUtf8 $reconPath $recon
Write-Host "Reconstruction audit resolver normalized." -ForegroundColor Green

Section "3/4 — Validate exact active resolution"

$verifyFinal = Get-Content -LiteralPath $verifyPath -Raw
$reconFinal = Get-Content -LiteralPath $reconPath -Raw

$required = @(
    'CANONICAL_AUDIT_TABLE = (',
    '"paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"',
    'PostgREST Schema Visibility: **PASS**',
    'Canonical Resolver: **LOCKED_TO_V92**',
    'BROKER_ORDER_SUBMISSION_ENABLED = False',
    'REAL_MONEY_TRADING_ENABLED = False'
)

foreach ($token in $required) {
    if (-not $verifyFinal.Contains($token)) {
        Fail "Verifier validation token missing: $token"
    }
}

# Detect exact legacy literal in reconstruction code.
$legacyRegex = '"paper_post_recovery_activation_master_cycle_reconstruction_audit"'
if ($reconFinal -match $legacyRegex) {
    Fail "Legacy non-_v92 audit table literal remains in reconstruction script."
}

if (-not $reconFinal.Contains(
    '"paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"'
)) {
    Fail "Canonical _v92 audit table missing from reconstruction script."
}

$python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} else {
    Fail "Python is not available in PATH."
}

if ($python -eq "py") {
    & py -3 -m py_compile $verifyPath
    if ($LASTEXITCODE -ne 0) { Fail "Verifier Python compile failed." }

    & py -3 -m py_compile $reconPath
    if ($LASTEXITCODE -ne 0) { Fail "Reconstruction Python compile failed." }
} else {
    & python -m py_compile $verifyPath
    if ($LASTEXITCODE -ne 0) { Fail "Verifier Python compile failed." }

    & python -m py_compile $reconPath
    if ($LASTEXITCODE -ne 0) { Fail "Reconstruction Python compile failed." }
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Canonical table resolution: LOCKED_TO_V92" -ForegroundColor Green
Write-Host "Legacy active table literal: ABSENT" -ForegroundColor Green
Write-Host "Paper-only safety boundary: PRESERVED" -ForegroundColor Green

Section "4/4 — Git status"

& git status --short

if ($AutoGit) {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne "main") {
        Fail "AutoGit requires branch main. Current branch: $branch"
    }

    & git add -- $verifyPath $reconPath
    if ($LASTEXITCODE -ne 0) { Fail "git add failed." }

    $staged = (& git diff --cached --name-only)
    if (-not [string]::IsNullOrWhiteSpace(($staged -join "`n"))) {
        & git commit -m "Fix Phase 37261 PostgREST canonical audit resolution"
        if ($LASTEXITCODE -ne 0) { Fail "git commit failed." }

        & git push origin main
        if ($LASTEXITCODE -ne 0) { Fail "git push failed." }

        Write-Host "Commit + Push: PASS" -ForegroundColor Green
    } else {
        Write-Host "No new staged changes." -ForegroundColor Yellow
    }
}

Section "PHASE37261 V5 DEPLOYMENT COMPLETE"

Write-Host "Canonical audit table:" -ForegroundColor Cyan
Write-Host "  paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
Write-Host ""
Write-Host "Expected next GitHub verifier output:" -ForegroundColor Yellow
Write-Host "  Resolved Audit Table: paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
Write-Host "  PostgREST Request Target: /rest/v1/paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
Write-Host "  PostgREST Schema Visibility: PASS"
Write-Host "  Canonical Resolver: LOCKED_TO_V92"
Write-Host ""
Write-Host "No Supabase SQL is required." -ForegroundColor Green
Write-Host "Backup: $backup" -ForegroundColor DarkGray
