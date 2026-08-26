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
