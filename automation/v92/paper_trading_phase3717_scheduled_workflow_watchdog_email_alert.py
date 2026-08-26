import json,os,smtplib,ssl,urllib.request
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from pathlib import Path

WATCHDOG_READ_ONLY=True
QUALIFICATION_MUTATION_ALLOWED=False
SYNTHETIC_QUALIFICATION_ALLOWED=False
MANUAL_COUNTER_INCREMENT_ALLOWED=False
BROKER_ORDER_SUBMISSION_ENABLED=False
REAL_MONEY_TRADING_ENABLED=False

REPO=os.environ["GITHUB_REPOSITORY"]
TOKEN=os.environ["GITHUB_TOKEN"]
TO=os.getenv("ALERT_EMAIL_TO","")
USER=os.getenv("SMTP_USERNAME","")
PWD=os.getenv("SMTP_APP_PASSWORD","")
GRACE=30
OUT=Path("artifacts/phase3717"); OUT.mkdir(parents=True,exist_ok=True)

WORKFLOWS=[
("3.7.13","gpt-quant-v92-paper-trading-phase3713-production-paper-natural-qualification-daily-orchestration-promotion-readiness-automation.yml",17,5),
("3.7.14","gpt-quant-v92-paper-trading-phase3714-production-paper-qualification-3of3-promotion-finalization-paper-runtime-activation-gate.yml",17,35),
("3.7.15","gpt-quant-v92-paper-trading-phase3715-production-paper-runtime-activation-first-live-paper-session-safety-validation.yml",17,50),
("3.7.15.1","gpt-quant-v92-paper-trading-phase37151-paper-runtime-pre-activation-configuration-first-session-dry-run-readiness-audit.yml",18,5),
("3.7.16","gpt-quant-v92-paper-trading-phase3716-first-live-paper-session-execution-order-lifecycle-safety-validation.yml",18,20),
("3.7.16.1","gpt-quant-v92-paper-trading-phase37161-first-live-paper-session-preflight-canonical-3of3-activation-handoff-integrity.yml",18,35),
("3.7.16.2","gpt-quant-v92-paper-trading-phase37162-natural-2of3-to-3of3-qualification-transition-first-paper-session-release-observation.yml",18,50),
]

def api(path):
    req=urllib.request.Request("https://api.github.com/repos/"+REPO+path,headers={
      "Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json","User-Agent":"phase3717-watchdog"})
    with urllib.request.urlopen(req,timeout=30) as r:return json.loads(r.read())

def dt(s): return datetime.fromisoformat(s.replace("Z","+00:00"))

now=datetime.now(timezone.utc); checks=[]; alerts=[]
for phase,wf,h,m in WORKFLOWS:
    expected=now.replace(hour=h,minute=m,second=0,microsecond=0)
    grace=expected+timedelta(minutes=GRACE)
    runs=api("/actions/workflows/"+wf+"/runs?branch=main&per_page=30").get("workflow_runs",[])
    candidates=[r for r in runs if expected-timedelta(minutes=10)<=dt(r["created_at"])<=grace+timedelta(minutes=20)]
    candidates.sort(key=lambda r:r["created_at"],reverse=True)
    run=candidates[0] if candidates else None
    if now<grace: status="GRACE_PERIOD"
    elif not run: status="MISSED_RUN"
    elif run.get("status")!="completed": status="NOT_COMPLETED"
    elif run.get("conclusion")!="success": status="FAILED"
    else: status="PASS"
    row={"phase":phase,"workflow":wf,"status":status,"expected_utc":expected.isoformat(),
         "run_url":run.get("html_url") if run else None,"conclusion":run.get("conclusion") if run else None}
    checks.append(row)
    if status in {"MISSED_RUN","NOT_COMPLETED","FAILED"}: alerts.append(row)

email_sent=False; email_error=None
if alerts:
    try:
        if not (TO and USER and PWD): raise RuntimeError("EMAIL_SECRETS_MISSING")
        msg=EmailMessage()
        msg["Subject"]=f"[GPT Quant ALERT] {len(alerts)} workflow issue(s)"
        msg["From"]=USER; msg["To"]=TO
        body=["GPT Quant Phase 3.7.17 Watchdog Alert","",f"Repository: {REPO}",f"UTC: {now.isoformat()}",""]
        for a in alerts:
            body += [f"Phase {a['phase']}: {a['status']}",f"Expected: {a['expected_utc']}",f"Run: {a['run_url'] or 'NONE'}",""]
        body += ["Watchdog is read-only. Qualification and trading settings were not modified."]
        msg.set_content("\n".join(body))
        with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context(),timeout=30) as s:
            s.login(USER,PWD); s.send_message(msg)
        email_sent=True
    except Exception as e: email_error=str(e)

state="WATCHDOG_ALL_SCHEDULED_WORKFLOWS_HEALTHY" if not alerts else "WATCHDOG_ALERT_DETECTED"
result={"state":state,"alert_count":len(alerts),"email_sent":email_sent,"email_error":email_error,"checks":checks}
(OUT/"phase3717_result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
summary=["# Phase 3.7.17 — Scheduled Workflow Watchdog","",f"- State: **{state}**",f"- Alert Count: **{len(alerts)}**",f"- Email Sent: **{'YES' if email_sent else 'NO'}**",f"- Email Error: **{email_error or 'NONE'}**",""]
for x in checks: summary += [f"- Phase {x['phase']}: **{x['status']}**"]
summary += ["","## Safety","- Watchdog Read-Only: **YES**","- Qualification Mutation: **DISABLED**","- Broker Order Submission: **DISABLED**","- Real-Money Trading: **DISABLED**"]
(OUT/"phase3717_summary.md").write_text("\n".join(summary)+"\n",encoding="utf-8")
print(state); print("Alert Count:",len(alerts)); print("Email Sent:","YES" if email_sent else "NO")
raise SystemExit(0 if not alerts else 1)
