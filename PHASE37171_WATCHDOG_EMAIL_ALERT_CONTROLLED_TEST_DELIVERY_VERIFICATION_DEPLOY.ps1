$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "PHASE37171 - Watchdog Email Alert Controlled Test + Delivery Verification" -ForegroundColor Cyan
Write-Host "Mode: CONTROLLED TEST EMAIL ONLY / READ-ONLY SAFETY" -ForegroundColor Green
Write-Host "Safety: NO qualification mutation / NO production schedule mutation / NO broker / NO real-money" -ForegroundColor Green

$repo = (Get-Location).Path
$pyRel = "automation/v92/paper_trading_phase37171_watchdog_email_alert_controlled_test_delivery_verification.py"
$ymlRel = ".github/workflows/gpt-quant-v92-paper-trading-phase37171-watchdog-email-alert-controlled-test-delivery-verification.yml"
$pyPath = Join-Path $repo $pyRel
$ymlPath = Join-Path $repo $ymlRel

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $repo ".phase37171-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

foreach ($p in @($pyPath, $ymlPath)) {
    if (Test-Path $p) {
        Copy-Item $p (Join-Path $backup (Split-Path $p -Leaf)) -Force
    }
}

$pyText = @'
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

CONTRACT = "PHASE37171_WATCHDOG_EMAIL_ALERT_CONTROLLED_TEST_DELIVERY_VERIFICATION"

# Permanent safety contract.
CONTROLLED_TEST_ONLY = True
WATCHDOG_READ_ONLY = True
QUALIFICATION_MUTATION_ALLOWED = False
SYNTHETIC_QUALIFICATION_ALLOWED = False
MANUAL_COUNTER_INCREMENT_ALLOWED = False
PRODUCTION_SCHEDULE_MUTATION_ALLOWED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False

ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "").strip()
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))

ART_DIR = Path("artifacts/phase37171")
RESULT_PATH = ART_DIR / "phase37171_result.json"
SUMMARY_PATH = ART_DIR / "phase37171_summary.md"

def validate_secrets():
    missing = []
    if not ALERT_EMAIL_TO:
        missing.append("ALERT_EMAIL_TO")
    if not SMTP_USERNAME:
        missing.append("SMTP_USERNAME")
    if not SMTP_APP_PASSWORD:
        missing.append("SMTP_APP_PASSWORD")
    return missing

def send_controlled_test_email():
    now = datetime.now(timezone.utc)
    msg = EmailMessage()
    msg["Subject"] = "[GPT Quant TEST] Phase 3.7.17.1 Email Alert Delivery Verification"
    msg["From"] = SMTP_USERNAME
    msg["To"] = ALERT_EMAIL_TO

    body = f"""GPT Quant Phase 3.7.17.1 Controlled Test Alert

This is a SAFE TEST EMAIL.

Purpose:
Verify that the Phase 3.7.17 production watchdog can deliver email alerts through GitHub Actions.

Timestamp UTC:
{now.isoformat()}

Safety Contract:
- Controlled Test Only: YES
- Watchdog Read-Only: YES
- Qualification Mutation: DISABLED
- Synthetic Qualification: DISABLED
- Manual Counter Increment: DISABLED
- Production Schedule Mutation: DISABLED
- Broker Order Submission: DISABLED
- Real-Money Trading: DISABLED

If you received this email, SMTP delivery from GitHub Actions is functioning.
"""
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
        smtp.login(SMTP_USERNAME, SMTP_APP_PASSWORD)
        smtp.send_message(msg)

def main():
    ART_DIR.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).isoformat()
    missing = validate_secrets()

    email_sent = False
    email_error = None

    if missing:
        state = "CONTROLLED_TEST_BLOCKED_MISSING_EMAIL_SECRETS"
        operational = False
    else:
        try:
            send_controlled_test_email()
            email_sent = True
            state = "CONTROLLED_TEST_EMAIL_SENT_AWAITING_USER_DELIVERY_CONFIRMATION"
            operational = True
        except Exception as exc:
            email_error = str(exc)
            state = "CONTROLLED_TEST_EMAIL_SEND_FAILED"
            operational = False

    result = {
        "contract": CONTRACT,
        "captured_at": captured_at,
        "state": state,
        "operational": operational,
        "email_sent": email_sent,
        "delivery_confirmed_by_user": False,
        "email_error": email_error,
        "missing_secrets": missing,
        "safety": {
            "controlled_test_only": CONTROLLED_TEST_ONLY,
            "watchdog_read_only": WATCHDOG_READ_ONLY,
            "qualification_mutation_allowed": QUALIFICATION_MUTATION_ALLOWED,
            "synthetic_qualification_allowed": SYNTHETIC_QUALIFICATION_ALLOWED,
            "manual_counter_increment_allowed": MANUAL_COUNTER_INCREMENT_ALLOWED,
            "production_schedule_mutation_allowed": PRODUCTION_SCHEDULE_MUTATION_ALLOWED,
            "broker_order_submission_enabled": BROKER_ORDER_SUBMISSION_ENABLED,
            "real_money_trading_enabled": REAL_MONEY_TRADING_ENABLED,
        },
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# GPT Quant V9.2 Paper Trading — Phase 3.7.17.1",
        "",
        "## Watchdog Email Alert Controlled Test + Delivery Verification",
        "",
        f"- State: **{state}**",
        f"- Operational: **{'YES' if operational else 'NO'}**",
        f"- Email Sent: **{'YES' if email_sent else 'NO'}**",
        f"- Email Error: **{email_error or 'NONE'}**",
        f"- Missing Secrets: **{', '.join(missing) if missing else 'NONE'}**",
        "",
        "## Delivery Verification",
        "",
        "- GitHub Actions SMTP Send Attempt: **" + ("PASS" if email_sent else "FAIL") + "**",
        "- User Inbox Delivery Confirmation: **PENDING**",
        "",
        "## Safety Boundary",
        "",
        "- Controlled Test Only: **YES**",
        "- Watchdog Read-Only: **YES**",
        "- Qualification Mutation: **DISABLED**",
        "- Synthetic Qualification: **DISABLED**",
        "- Manual Counter Increment: **DISABLED**",
        "- Production Schedule Mutation: **DISABLED**",
        "- Broker Order Submission: **DISABLED**",
        "- Real-Money Trading: **DISABLED**",
    ]
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"State: {state}")
    print(f"Email Sent: {'YES' if email_sent else 'NO'}")
    print(f"Email Error: {email_error or 'NONE'}")
    print("Delivery Confirmation: PENDING USER INBOX CHECK")

    return 0 if operational else 1

if __name__ == "__main__":
    raise SystemExit(main())
'@

$ymlText = @'
name: GPT Quant Phase 3.7.17.1 - Watchdog Email Alert Controlled Test Delivery Verification

on:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: phase37171-watchdog-email-alert-controlled-test
  cancel-in-progress: false

jobs:
  controlled-email-test:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    env:
      ALERT_EMAIL_TO: ${{ secrets.ALERT_EMAIL_TO }}
      SMTP_USERNAME: ${{ secrets.SMTP_USERNAME }}
      SMTP_APP_PASSWORD: ${{ secrets.SMTP_APP_PASSWORD }}
      SMTP_HOST: smtp.gmail.com
      SMTP_PORT: "465"

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Compile Phase 3.7.17.1
        run: python -m py_compile automation/v92/paper_trading_phase37171_watchdog_email_alert_controlled_test_delivery_verification.py

      - name: Validate controlled-test safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase37171_watchdog_email_alert_controlled_test_delivery_verification.py"
          grep -q 'CONTROLLED_TEST_ONLY = True' "$f"
          grep -q 'WATCHDOG_READ_ONLY = True' "$f"
          grep -q 'QUALIFICATION_MUTATION_ALLOWED = False' "$f"
          grep -q 'SYNTHETIC_QUALIFICATION_ALLOWED = False' "$f"
          grep -q 'MANUAL_COUNTER_INCREMENT_ALLOWED = False' "$f"
          grep -q 'PRODUCTION_SCHEDULE_MUTATION_ALLOWED = False' "$f"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED = False' "$f"
          grep -q 'REAL_MONEY_TRADING_ENABLED = False' "$f"
          echo "Phase 3.7.17.1 controlled-test safety contract: PASS"

      - name: Send controlled test email
        id: phase37171
        continue-on-error: true
        run: python automation/v92/paper_trading_phase37171_watchdog_email_alert_controlled_test_delivery_verification.py

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37171/phase37171_summary.md ]; then
            cat artifacts/phase37171/phase37171_summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload Phase 3.7.17.1 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37171-watchdog-email-alert-controlled-test
          path: artifacts/phase37171
          if-no-files-found: warn
          retention-days: 90

      - name: Enforce controlled test result
        if: always()
        shell: bash
        run: |
          if [ "${{ steps.phase37171.outcome }}" != "success" ]; then
            echo "Phase 3.7.17.1 controlled test failed."
            exit 1
          fi
          echo "Phase 3.7.17.1 email send succeeded. Confirm delivery in recipient inbox."
'@

$utf8 = New-Object System.Text.UTF8Encoding($false)
foreach ($p in @($pyPath, $ymlPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $p) | Out-Null
}
[System.IO.File]::WriteAllText($pyPath, $pyText + [Environment]::NewLine, $utf8)
[System.IO.File]::WriteAllText($ymlPath, $ymlText + [Environment]::NewLine, $utf8)

python -m py_compile $pyPath
if ($LASTEXITCODE -ne 0) { throw "Python compile failed." }

$combined = (Get-Content -LiteralPath $pyPath -Raw) + "`n" + (Get-Content -LiteralPath $ymlPath -Raw)
$required = @(
  'CONTROLLED_TEST_ONLY = True',
  'WATCHDOG_READ_ONLY = True',
  'QUALIFICATION_MUTATION_ALLOWED = False',
  'SYNTHETIC_QUALIFICATION_ALLOWED = False',
  'MANUAL_COUNTER_INCREMENT_ALLOWED = False',
  'PRODUCTION_SCHEDULE_MUTATION_ALLOWED = False',
  'BROKER_ORDER_SUBMISSION_ENABLED = False',
  'REAL_MONEY_TRADING_ENABLED = False',
  'CONTROLLED_TEST_EMAIL_SENT_AWAITING_USER_DELIVERY_CONFIRMATION',
  'CONTROLLED_TEST_EMAIL_SEND_FAILED',
  'CONTROLLED_TEST_BLOCKED_MISSING_EMAIL_SECRETS'
)

foreach ($token in $required) {
    if ($combined -notmatch [regex]::Escape($token)) {
        throw "Verification failed: missing $token"
    }
}

Write-Host ""
Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Controlled-test safety contract: PASS" -ForegroundColor Green
Write-Host "Gmail SMTP delivery-test contract: PASS" -ForegroundColor Green
Write-Host "Qualification mutation prohibition: PASS" -ForegroundColor Green
Write-Host "Production schedule mutation prohibition: PASS" -ForegroundColor Green
Write-Host "Broker/real-money safety lock: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37171 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL schema change is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Expected GitHub Actions result after running Phase 3.7.17.1:"
Write-Host "  CONTROLLED_TEST_EMAIL_SENT_AWAITING_USER_DELIVERY_CONFIRMATION"
Write-Host "  Email Sent: YES"
Write-Host "  User Inbox Delivery Confirmation: PENDING"
Write-Host ""
Write-Host "Required existing GitHub Secrets:"
Write-Host "  ALERT_EMAIL_TO"
Write-Host "  SMTP_USERNAME"
Write-Host "  SMTP_APP_PASSWORD"
Write-Host ""
Write-Host "Backup: $backup"
Write-Host ""
Write-Host "NEXT:"
Write-Host '1. git add "automation/v92/paper_trading_phase37171_watchdog_email_alert_controlled_test_delivery_verification.py"'
Write-Host '2. git add ".github/workflows/gpt-quant-v92-paper-trading-phase37171-watchdog-email-alert-controlled-test-delivery-verification.yml"'
Write-Host '3. git diff --cached --name-only'
Write-Host '4. git commit -m "Deploy Phase 37171 watchdog email alert controlled test delivery verification"'
Write-Host '5. git push origin main'
Write-Host '6. Run a NEW Phase 3.7.17.1 workflow and check the recipient inbox.'
