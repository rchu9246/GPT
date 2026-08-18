$ErrorActionPreference="Stop"
$root=(Get-Location).Path
$a=Join-Path $root "automation\v92"
$w=Join-Path $root ".github\workflows"
New-Item -ItemType Directory -Force $a,$w|Out-Null

$py=@'
import json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
MODE="SHADOW_ONLY_NO_BROKER"
STRATEGY=os.getenv("PAPER_STRATEGY_VERSION","V9.1")
OUT=ROOT/"phase342_output"; OUT.mkdir(exist_ok=True)
p341=ROOT/"automation/v92/paper_trading_phase341_daily_qualification.py"
p34=ROOT/"automation/v92/paper_trading_phase34_human_approval_release.py"
def call(cmd,env):
 p=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
 print(p.stdout); print(p.stderr,file=sys.stderr)
 return p
def main():
 if MODE!="SHADOW_ONLY_NO_BROKER": raise RuntimeError("Safety lock")
 if not p341.exists() or not p34.exists(): raise RuntimeError("Missing Phase 3.4/3.4.1 engine")
 env=os.environ.copy(); env["STRATEGY_VERSION"]=STRATEGY
 env["PAPER_STRATEGY_VERSION"]=STRATEGY; env["PAPER_TRADING_MODE"]=MODE
 if call([sys.executable,str(p341)],env).returncode: raise RuntimeError("3.4.1 failed")
 ok=False
 for cmd in ([sys.executable,str(p34),"--action","evaluate","--strategy-version",STRATEGY],
             [sys.executable,str(p34),"evaluate"],[sys.executable,str(p34)]):
  r=call(cmd,env)
  if r.returncode==0: ok=True; break
  s=((r.stdout or "")+(r.stderr or "")).lower()
  if not any(x in s for x in ("unrecognized arguments","usage:","invalid choice")): break
 if not ok: raise RuntimeError("3.4 evaluation failed")
 d={"phase":"3.4.2","status":"PASS","strategy_version":STRATEGY,"mode":MODE,
    "human_approval_required":True,"automatic_approval":False,
    "broker_execution_enabled":False,"real_money_enabled":False,
    "completed_at":datetime.now(timezone.utc).isoformat()}
 (OUT/"daily_operations.json").write_text(json.dumps(d,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(d,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
'@

$yml=@'
name: GPT Quant Phase 3.4.2 - Production Paper Daily Operations
on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
  schedule:
    - cron: "15 9 * * 1-5" # 17:15 Taiwan, after Phase 3.4.1
permissions:
  contents: read
concurrency:
  group: gpt-quant-phase342-production-paper-daily
  cancel-in-progress: false
jobs:
  production-paper-daily:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --upgrade pip requests
      - name: Safety validation
        shell: bash
        run: |
          set -euo pipefail
          test -f automation/v92/paper_trading_phase34_human_approval_release.py
          test -f automation/v92/paper_trading_phase341_daily_qualification.py
          test -f automation/v92/paper_trading_phase342_daily_operations.py
          grep -q SHADOW_ONLY_NO_BROKER automation/v92/paper_trading_phase342_daily_operations.py
      - name: V9.1 Confidence Calibration
        run: python automation/gpt_quant_v91_confidence_calibration.py
      - name: V9.1 Adaptive Risk
        run: python automation/gpt_quant_v91_adaptive_risk_manager.py --base-risk-budget "0.60"
      - name: V9.1 Portfolio Optimizer
        run: python automation/gpt_quant_v91_portfolio_optimizer.py --max-positions "10" --max-single-weight "0.10"
      - name: V9.1 Paper Trading
        run: python automation/gpt_quant_v91_paper_trading_engine.py --starting-equity "1000000"
      - name: Phase 3.4.2 Daily Qualification + Release Guard
        run: python automation/v92/paper_trading_phase342_daily_operations.py
      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase342-production-paper-daily-${{ github.run_id }}
          path: |
            phase34_result.json
            phase34_summary.md
            phase341_output/
            phase342_output/
          if-no-files-found: warn
          retention-days: 30
'@

[IO.File]::WriteAllText((Join-Path $a "paper_trading_phase342_daily_operations.py"),$py,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $w "gpt-quant-v92-paper-trading-phase342-daily-operations.yml"),$yml,[Text.UTF8Encoding]::new($false))
Write-Host "PHASE 3.4.2 READY"
Write-Host "Created automation/v92/paper_trading_phase342_daily_operations.py"
Write-Host "Created .github/workflows/gpt-quant-v92-paper-trading-phase342-daily-operations.yml"
Write-Host "Safety: human approval REQUIRED; automatic approval/broker/real-money DISABLED"
