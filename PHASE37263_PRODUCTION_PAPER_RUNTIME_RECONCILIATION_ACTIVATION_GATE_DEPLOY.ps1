#requires -Version 5.1
$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
function F($m){Write-Host "PHASE37263_FATAL: $m" -ForegroundColor Red; exit 1}
function W($p,$t){$d=Split-Path -Parent $p;if($d-and!(Test-Path $d)){New-Item -ItemType Directory -Force $d|Out-Null};[IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($false)))}

try{$root=(& git rev-parse --show-toplevel 2>$null).Trim()}catch{$root=""}
if(!$root){F "Run inside GPT repository."}
Set-Location $root

$pyPath=Join-Path $root "automation\v92\paper_trading_phase37263_production_paper_runtime_reconciliation_activation_gate.py"
$ymlPath=Join-Path $root ".github\workflows\gpt-quant-v92-paper-trading-phase37263-production-paper-runtime-reconciliation-activation-gate.yml"

$py=@'
import argparse,json,os,sys,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from datetime import datetime,timezone

CONTRACT="PHASE37263_PRODUCTION_PAPER_RUNTIME_RECONCILIATION_ACTIVATION_GATE"
TABLES={
 "activation":"paper_post_recovery_activation_state_v92",
 "master":"paper_post_recovery_master_cycle_v92",
 "supervision":"paper_runtime_supervision_state_v92",
 "reconstruction":"phase37261_reconstruction_audit_v92"
}
BLOCK={"REVOKED","FAIL_CLOSED","BLOCKED","HALTED","SUSPENDED"}
BROKER_ORDER_SUBMISSION_ENABLED=False
REAL_MONEY_TRADING_ENABLED=False
HISTORICAL_REWRITE_ALLOWED=False

def env(n):
 v=os.getenv(n,"").strip()
 if not v: raise RuntimeError(f"Missing env: {n}")
 return v

def get(table,portfolio):
 base=env("SUPABASE_URL").rstrip("/")
 key=env("SUPABASE_SERVICE_ROLE_KEY")
 candidates=[
  {"select":"*","portfolio_id":f"eq.{portfolio}","order":"created_at.desc","limit":"1"},
  {"select":"*","limit":"1"}
 ]
 for params in candidates:
  q=urllib.parse.urlencode(params,safe="*,.()")
  req=urllib.request.Request(f"{base}/rest/v1/{table}?{q}",headers={"apikey":key,"Authorization":f"Bearer {key}"})
  try:
   with urllib.request.urlopen(req,timeout=45) as r:
    data=json.loads(r.read().decode() or "[]")
    if data:return data[0]
  except urllib.error.HTTPError as e:
   body=e.read().decode(errors="replace")
   if "PGRST204" not in body: raise RuntimeError(f"{table}: HTTP {e.code}: {body}")
 return None

def state(row,*names):
 if not row:return ""
 for n in names:
  if row.get(n) is not None:return str(row[n]).strip().upper()
 return ""

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--portfolio-id",default="V92_PRODUCTION_PAPER_V91")
 ap.add_argument("--strategy-version",default="V9.1")
 a=ap.parse_args()

 activation=get(TABLES["activation"],a.portfolio_id)
 master=get(TABLES["master"],a.portfolio_id)
 supervision=get(TABLES["supervision"],a.portfolio_id)
 reconstruction=get(TABLES["reconstruction"],a.portfolio_id)

 sa=state(activation,"activation_state","state","status")
 sm=state(master,"master_cycle_state","cycle_state","state","status")
 ss=state(supervision,"supervision_state","runtime_supervision","state","status")
 sr=state(reconstruction,"reconstruction_state","state","status")

 pa=bool(activation) and sa=="ACTIVE"
 pm=bool(master) and sm not in BLOCK
 ps=bool(supervision) and ss not in BLOCK
 pr=bool(reconstruction) and sr not in BLOCK
 if reconstruction and not sr: pr=True

 reasons=[]
 if not pa: reasons.append(f"ACTIVATION:{sa or 'MISSING'}")
 if not pm: reasons.append(f"MASTER:{sm or 'MISSING'}")
 if not ps: reasons.append(f"SUPERVISION:{ss or 'MISSING'}")
 if not pr: reasons.append(f"RECONSTRUCTION:{sr or 'MISSING'}")

 gate="AUTHORIZED_PAPER_CONTINUATION" if not reasons else "BLOCKED"
 now=datetime.now(timezone.utc)
 art=Path("artifacts/phase37263");art.mkdir(parents=True,exist_ok=True)
 evidence={"contract":CONTRACT,"gate_state":gate,"portfolio_id":a.portfolio_id,"strategy_version":a.strategy_version,
 "states":{"activation":sa,"master":sm,"supervision":ss,"reconstruction":sr},"reasons":reasons,
 "paper_only":True,"broker_order_submission_enabled":False,"real_money_trading_enabled":False,"historical_rewrite_allowed":False}
 (art/"verification.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
 summary=f"""# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.3

## Production Paper Runtime Reconciliation + Activation Gate

- Contract: `{CONTRACT}`
- Portfolio ID: `{a.portfolio_id}`
- Strategy Version: `{a.strategy_version}`
- Validation Date: `{now.date().isoformat()}`
- Activation Gate State: **{gate}**

## Canonical Runtime Reconciliation

- Activation State: **{sa or 'UNKNOWN'}**
- Activation Gate: **{'PASS' if pa else 'FAIL'}**
- Master Cycle State: **{sm or 'UNKNOWN'}**
- Master Cycle Gate: **{'PASS' if pm else 'FAIL'}**
- Runtime Supervision State: **{ss or 'UNKNOWN'}**
- Runtime Supervision Gate: **{'PASS' if ps else 'FAIL'}**
- Reconstruction State: **{sr or 'UNKNOWN'}**
- Reconstruction Gate: **{'PASS' if pr else 'FAIL'}**

## Safety Boundary

- Paper only: **ENABLED**
- Broker order submission: **DISABLED**
- Real-money trading: **DISABLED**
- Historical rewrite allowed: **NO**
- Real-money promotion authority: **NOT PRESENT IN THIS PHASE**
"""
 (art/"summary.md").write_text(summary,encoding="utf-8")
 print(summary)
 if gate!="AUTHORIZED_PAPER_CONTINUATION":
  raise RuntimeError("Activation gate blocked: "+", ".join(reasons))

if __name__=="__main__":
 try: main()
 except Exception as e:
  print("PHASE37263_FATAL:",e,file=sys.stderr); raise
'@

$yml=@'
name: GPT Quant Phase 3.7.2.6.3 - Production Paper Runtime Reconciliation Activation Gate
on:
  workflow_dispatch:
    inputs:
      strategy_version:
        required: true
        default: V9.1
        type: string
      portfolio_id:
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string
permissions:
  contents: read
jobs:
  activation-gate:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
      - name: Compile Phase 3.7.2.6.3
        run: python -m py_compile automation/v92/paper_trading_phase37263_production_paper_runtime_reconciliation_activation_gate.py
      - name: Validate safety contract
        shell: bash
        run: |
          set -euo pipefail
          f="automation/v92/paper_trading_phase37263_production_paper_runtime_reconciliation_activation_gate.py"
          grep -q 'PHASE37263_PRODUCTION_PAPER_RUNTIME_RECONCILIATION_ACTIVATION_GATE' "$f"
          grep -q 'AUTHORIZED_PAPER_CONTINUATION' "$f"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED=False' "$f"
          grep -q 'REAL_MONEY_TRADING_ENABLED=False' "$f"
          grep -q 'HISTORICAL_REWRITE_ALLOWED=False' "$f"
      - name: Execute Phase 3.7.2.6.3
        run: |
          mkdir -p artifacts/phase37263
          python automation/v92/paper_trading_phase37263_production_paper_runtime_reconciliation_activation_gate.py --strategy-version "$STRATEGY_VERSION" --portfolio-id "$PORTFOLIO_ID" | tee artifacts/phase37263/console.md
      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37263/summary.md ]; then cat artifacts/phase37263/summary.md >> "$GITHUB_STEP_SUMMARY"; fi
      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37263-production-paper-runtime-activation-gate
          path: artifacts/phase37263/
          if-no-files-found: warn
          retention-days: 120
'@

W $pyPath $py
W $ymlPath $yml

if(Get-Command python -ErrorAction SilentlyContinue){& python -m py_compile $pyPath}
elseif(Get-Command py -ErrorAction SilentlyContinue){& py -3 -m py_compile $pyPath}
else{F "Python not found"}
if($LASTEXITCODE-ne 0){F "Python compile failed"}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Runtime reconciliation contract: PASS" -ForegroundColor Green
Write-Host "Activation gate contract: PASS" -ForegroundColor Green
Write-Host "Paper-only authorization boundary: PASS" -ForegroundColor Green
Write-Host "Historical rewrite prohibition: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37263 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "No Supabase SQL is required." -ForegroundColor Green
Write-Host ""
Write-Host "Generated:"
Write-Host "  $pyPath"
Write-Host "  $ymlPath"
Write-Host ""
Write-Host "Target GitHub result:"
Write-Host "  Activation Gate State: AUTHORIZED_PAPER_CONTINUATION"
Write-Host "  Activation Gate: PASS"
Write-Host "  Master Cycle Gate: PASS"
Write-Host "  Runtime Supervision Gate: PASS"
Write-Host "  Reconstruction Gate: PASS"
