#requires -Version 5.1
<#
GPT Quant V9.2
Phase 3.5.1 — Production Paper Performance Analytics + Risk Metrics Engine

Creates/overwrites:
  supabase/PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS.sql
  automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py
  .github/workflows/gpt-quant-v92-paper-trading-phase351-production-paper-performance-analytics-risk-metrics-engine.yml

Upstream canonical source:
  public.paper_performance_ledger_v92 (Phase 3.5.0)

Hard safety locks remain unchanged: paper/shadow only, no broker, no real money,
no synthetic market data/signals, no fake prices, fail-closed enabled.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 112) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 112) -ForegroundColor DarkCyan
}
function Fail([string]$Message) {
    Write-Host ""
    Write-Host "DEPLOY FAILED: $Message" -ForegroundColor Red
    exit 1
}

Section "GPT Quant V9.2 — Phase 3.5.1 Performance Analytics + Risk Metrics Engine"
$repoRoot = $null
try { $repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim() } catch { $repoRoot = $null }
if ([string]::IsNullOrWhiteSpace($repoRoot)) { Fail "Run this script inside the GPT Git repository." }
Set-Location $repoRoot
Write-Host "Repository: $repoRoot" -ForegroundColor Green

$required = @(
    "automation/v92/paper_trading_phase350_production_paper_daily_orchestrator_persistent_performance_ledger.py",
    "supabase/PHASE350_PRODUCTION_PAPER_PERFORMANCE_LEDGER.sql"
)
foreach ($item in $required) { if (-not (Test-Path $item)) { Fail "Required Phase 3.5.0 upstream file not found: $item" } }

$sqlTarget = "supabase/PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS.sql"
$pythonTarget = "automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py"
$workflowTarget = ".github/workflows/gpt-quant-v92-paper-trading-phase351-production-paper-performance-analytics-risk-metrics-engine.yml"
foreach ($target in @($sqlTarget,$pythonTarget,$workflowTarget)) { New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $repoRoot ".phase351-backup-$stamp"
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
foreach ($target in @($sqlTarget,$pythonTarget,$workflowTarget)) {
    if (Test-Path $target) {
        $dest = Join-Path $backupRoot ($target -replace '[\\/]', '__')
        Copy-Item $target $dest -Force
        Write-Host "Backup: $target -> $dest" -ForegroundColor DarkGray
    }
}

Section "Writing Phase 3.5.1 Supabase analytics schema"
$sql = @'
begin;

create table if not exists public.paper_performance_analytics_v92 (
    analytics_id text primary key,
    portfolio_id text not null,
    strategy_version text not null,
    as_of_date date not null,
    analytics_state text not null,
    ledger_rows integer not null,
    first_ledger_date date not null,
    last_ledger_date date not null,
    initial_nav numeric not null,
    current_nav numeric not null,
    daily_return numeric not null,
    cumulative_return numeric not null,
    annualized_volatility numeric,
    sharpe_ratio numeric,
    current_drawdown numeric not null,
    max_drawdown numeric not null,
    positive_days integer not null,
    negative_days integer not null,
    flat_days integer not null,
    win_rate numeric,
    average_gain numeric,
    average_loss numeric,
    profit_factor numeric,
    return_observations integer not null,
    min_history_required integer not null,
    risk_free_rate_annual numeric not null default 0,
    synthetic_market_data boolean not null default false,
    synthetic_signals boolean not null default false,
    fake_prices_allowed boolean not null default false,
    broker_api_used boolean not null default false,
    broker_credentials_used boolean not null default false,
    broker_order_submission_enabled boolean not null default false,
    real_money_trading_enabled boolean not null default false,
    live_money_release_authorized boolean not null default false,
    fail_closed_policy boolean not null default true,
    evidence_sha256 text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists uq_paper_performance_analytics_v92_portfolio_date
    on public.paper_performance_analytics_v92 (portfolio_id, as_of_date);

alter table public.paper_performance_analytics_v92 enable row level security;

comment on table public.paper_performance_analytics_v92 is
'GPT Quant V9.2 production-paper performance analytics and risk metrics derived only from canonical paper_performance_ledger_v92. Simulation only; broker and real-money trading hard-disabled.';

commit;
'@
Set-Content -LiteralPath $sqlTarget -Value $sql -Encoding UTF8
Write-Host "Wrote: $sqlTarget" -ForegroundColor Green

Section "Writing Phase 3.5.1 Python analytics engine"
$python = @'
#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, math, os, statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "phase351_output"
OUT.mkdir(exist_ok=True)
MODE = "SHADOW_ONLY_NO_BROKER"
STRATEGY = os.getenv("PAPER_STRATEGY_VERSION", "V9.1").strip() or "V9.1"
PORTFOLIO_ID = os.getenv("PHASE351_PORTFOLIO_ID", "V92_PRODUCTION_PAPER_V91").strip()
LEDGER_TABLE = "paper_performance_ledger_v92"
ANALYTICS_TABLE = "paper_performance_analytics_v92"
CONTRACT = "PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS_RISK_METRICS_ENGINE"
RESULT_JSON = OUT / "phase351_performance_analytics.json"
MIN_HISTORY = max(2, int(os.getenv("PHASE351_MIN_HISTORY", "5")))
TRADING_DAYS = 252
RISK_FREE_RATE = float(os.getenv("PHASE351_RISK_FREE_RATE_ANNUAL", "0"))


def stable_hash(payload: Any) -> str:
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")

def supabase():
    base=os.getenv("SUPABASE_URL","").strip().rstrip("/")
    key=os.getenv("SUPABASE_SERVICE_ROLE_KEY","").strip()
    if not base or not key: raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing")
    return base,{"apikey":key,"Authorization":f"Bearer {key}","Content-Type":"application/json","Accept":"application/json"}

def rest_get(table: str, params):
    base,headers=supabase(); url=f"{base}/rest/v1/{quote(table,safe='')}"
    r=requests.get(url,headers=headers,params=params,timeout=25)
    if r.status_code>=400: raise RuntimeError(f"{table}: GET HTTP {r.status_code}: {r.text[:1000]}")
    data=r.json()
    if not isinstance(data,list): raise RuntimeError(f"{table}: expected list response")
    return [x for x in data if isinstance(x,dict)]

def rest_upsert(table: str, rows, on_conflict: str):
    base,headers=supabase(); headers=dict(headers); headers["Prefer"]="resolution=merge-duplicates,return=minimal"
    r=requests.post(f"{base}/rest/v1/{quote(table,safe='')}",headers=headers,params={"on_conflict":on_conflict},data=json.dumps(rows,ensure_ascii=False,default=str),timeout=25)
    if r.status_code>=400: raise RuntimeError(f"{table}: UPSERT HTTP {r.status_code}: {r.text[:1000]}")

def f(v: Any) -> float: return float(v or 0.0)
def finite_or_none(v: float | None):
    return v if v is not None and math.isfinite(v) else None

def load_ledger():
    rows=rest_get(LEDGER_TABLE,[("select","*"),("portfolio_id",f"eq.{PORTFOLIO_ID}"),("order","ledger_date.asc")])
    if not rows: raise RuntimeError("No Phase 3.5.0 performance ledger rows found; run Phase 3.5.0 first")
    for row in rows:
        if row.get("cycle_status") != "COMPLETED": raise RuntimeError("Ledger contains non-COMPLETED cycle")
        for key in ("synthetic_market_data","synthetic_signals","fake_prices_allowed","broker_api_used","broker_credentials_used","broker_order_submission_enabled","real_money_trading_enabled","live_money_release_authorized"):
            if row.get(key) is not False: raise RuntimeError(f"Safety contract violation in ledger: {key}={row.get(key)!r}")
        if row.get("fail_closed_policy") is not True: raise RuntimeError("Ledger fail_closed_policy must be enabled")
        if f(row.get("nav")) < 0 or f(row.get("cash")) < 0: raise RuntimeError("Negative NAV/cash in canonical ledger")
    return rows

def calculate(rows):
    returns=[f(r.get("daily_return")) for r in rows]
    navs=[f(r.get("nav")) for r in rows]
    drawdowns=[f(r.get("drawdown")) for r in rows]
    observations=max(0,len(returns)-1)  # first ledger row has no true prior-period return
    observed_returns=returns[1:] if len(returns)>1 else []
    positive=[x for x in observed_returns if x>0]
    negative=[x for x in observed_returns if x<0]
    flat=[x for x in observed_returns if abs(x)<=1e-15]
    enough=len(rows)>=MIN_HISTORY and observations>=2
    volatility=None; sharpe=None
    if enough:
        daily_std=statistics.stdev(observed_returns)
        volatility=daily_std*math.sqrt(TRADING_DAYS)
        daily_rf=(1.0+RISK_FREE_RATE)**(1.0/TRADING_DAYS)-1.0
        if daily_std>0:
            sharpe=((statistics.mean(observed_returns)-daily_rf)/daily_std)*math.sqrt(TRADING_DAYS)
    win_rate=(len(positive)/(len(positive)+len(negative))) if (positive or negative) else None
    avg_gain=statistics.mean(positive) if positive else None
    avg_loss=statistics.mean(negative) if negative else None
    gross_gain=sum(positive)
    gross_loss=abs(sum(negative))
    profit_factor=(gross_gain/gross_loss) if gross_loss>0 else None
    state="ANALYTICS_READY" if enough else "INSUFFICIENT_HISTORY_VALID_STATE"
    current=rows[-1]
    initial_nav=f(rows[0].get("initial_nav") or rows[0].get("nav"))
    current_nav=navs[-1]
    cumulative=(current_nav/initial_nav-1.0) if initial_nav else 0.0
    max_dd=min(drawdowns) if drawdowns else 0.0
    seed={"portfolio_id":PORTFOLIO_ID,"as_of_date":str(current["ledger_date"]),"ledger_rows":len(rows),"current_nav":current_nav,"cumulative_return":cumulative,"max_drawdown":max_dd,"analytics_state":state}
    return {
      "analytics_id":"P351A-"+stable_hash(seed)[:28],"portfolio_id":PORTFOLIO_ID,"strategy_version":STRATEGY,
      "as_of_date":str(current["ledger_date"]),"analytics_state":state,"ledger_rows":len(rows),
      "first_ledger_date":str(rows[0]["ledger_date"]),"last_ledger_date":str(current["ledger_date"]),
      "initial_nav":initial_nav,"current_nav":current_nav,"daily_return":returns[-1],"cumulative_return":cumulative,
      "annualized_volatility":finite_or_none(volatility),"sharpe_ratio":finite_or_none(sharpe),
      "current_drawdown":drawdowns[-1] if drawdowns else 0.0,"max_drawdown":max_dd,
      "positive_days":len(positive),"negative_days":len(negative),"flat_days":len(flat),"win_rate":win_rate,
      "average_gain":avg_gain,"average_loss":avg_loss,"profit_factor":profit_factor,"return_observations":observations,
      "min_history_required":MIN_HISTORY,"risk_free_rate_annual":RISK_FREE_RATE,
      "synthetic_market_data":False,"synthetic_signals":False,"fake_prices_allowed":False,"broker_api_used":False,
      "broker_credentials_used":False,"broker_order_submission_enabled":False,"real_money_trading_enabled":False,
      "live_money_release_authorized":False,"fail_closed_policy":True,"evidence_sha256":stable_hash(seed),
      "updated_at":datetime.now(timezone.utc).isoformat()
    }

def persist(row):
    rest_upsert(ANALYTICS_TABLE,[row],"portfolio_id,as_of_date")
    got=rest_get(ANALYTICS_TABLE,[("select","*"),("portfolio_id",f"eq.{PORTFOLIO_ID}"),("as_of_date",f"eq.{row['as_of_date']}"),("limit","1")])
    if not got: raise RuntimeError("Analytics persistence verification failed")
    return got[0]

def fmt_pct(v): return "N/A" if v is None else f"{float(v):.6%}"
def fmt_num(v): return "N/A" if v is None else f"{float(v):.6f}"
def write_summary(r):
    lines=[
      "# GPT Quant V9.2 Paper Trading - Phase 3.5.1","","## Production Paper Performance Analytics + Risk Metrics Engine","",
      f"- Strategy: `{r['strategy_version']}`",f"- Trading Mode: `{MODE}`",f"- Contract: **{CONTRACT}**",f"- Portfolio ID: `{r['portfolio_id']}`",f"- Analytics Status: **PASS**",f"- Analytics State: **{r['analytics_state']}**","",
      "### Canonical Ledger History","",f"- Ledger Rows: **{r['ledger_rows']}**",f"- Return Observations: **{r['return_observations']}**",f"- Minimum History Required: **{r['min_history_required']}**",f"- First Ledger Date: `{r['first_ledger_date']}`",f"- As Of Date: `{r['as_of_date']}`","",
      "### Performance","",f"- Initial NAV: **{float(r['initial_nav']):.2f}**",f"- Current NAV: **{float(r['current_nav']):.2f}**",f"- Daily Return: **{fmt_pct(r['daily_return'])}**",f"- Cumulative Return: **{fmt_pct(r['cumulative_return'])}**",f"- Positive Days: **{r['positive_days']}**",f"- Negative Days: **{r['negative_days']}**",f"- Flat Days: **{r['flat_days']}**",f"- Win Rate: **{fmt_pct(r.get('win_rate'))}**",f"- Average Gain: **{fmt_pct(r.get('average_gain'))}**",f"- Average Loss: **{fmt_pct(r.get('average_loss'))}**",f"- Profit Factor: **{fmt_num(r.get('profit_factor'))}**","",
      "### Risk Metrics","",f"- Annualized Volatility: **{fmt_pct(r.get('annualized_volatility'))}**",f"- Sharpe Ratio: **{fmt_num(r.get('sharpe_ratio'))}**",f"- Current Drawdown: **{fmt_pct(r['current_drawdown'])}**",f"- Maximum Drawdown: **{fmt_pct(r['max_drawdown'])}**",f"- Annual Risk-Free Rate: **{fmt_pct(r['risk_free_rate_annual'])}**","",
      "### Safety Boundary","","- Synthetic market data: **DISABLED**","- Synthetic signals: **DISABLED**","- Fake prices: **DISABLED**","- Broker API used: **NO**","- Broker credentials used: **NO**","- Broker order submission: **DISABLED**","- Real-money trading: **DISABLED**","- Live-money release authorized: **NO**","- Fail-closed policy: **ENABLED**",f"- Evidence SHA256: `{r['evidence_sha256']}`"
    ]
    text="\n".join(lines)+"\n"; (OUT/"phase351_performance_analytics.md").write_text(text,encoding="utf-8")
    gh=os.getenv("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh,"a",encoding="utf-8") as h: h.write(text)

def main():
    argparse.ArgumentParser().parse_args()
    if MODE != "SHADOW_ONLY_NO_BROKER": raise RuntimeError("Safety violation: paper-only mode required")
    rows=load_ledger(); row=calculate(rows); persisted=persist(row)
    result={k: persisted.get(k) for k in persisted}
    result.update({"version":"3.5.1","status":"PASS","trading_mode":MODE,"contract":CONTRACT,"analytics_written":True})
    for k in ("ledger_rows","positive_days","negative_days","flat_days","return_observations","min_history_required"): result[k]=int(result[k])
    for k in ("initial_nav","current_nav","daily_return","cumulative_return","current_drawdown","max_drawdown","risk_free_rate_annual"):
        result[k]=float(result[k])
    for k in ("annualized_volatility","sharpe_ratio","win_rate","average_gain","average_loss","profit_factor"):
        result[k]=None if result.get(k) is None else float(result[k])
    dump_json(RESULT_JSON,result); write_summary(result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print(f"PHASE351 PASS: state={result['analytics_state']}, rows={result['ledger_rows']}, as_of={result['as_of_date']}, cumulative_return={result['cumulative_return']:.8f}, max_drawdown={result['max_drawdown']:.8f}.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
'@
Set-Content -LiteralPath $pythonTarget -Value $python -Encoding UTF8
Write-Host "Wrote: $pythonTarget" -ForegroundColor Green

Section "Writing Phase 3.5.1 GitHub Actions workflow"
$workflow = @'
name: GPT Quant Phase 3.5.1 - Production Paper Performance Analytics Risk Metrics Engine

on:
  workflow_dispatch:
    inputs:
      strategy_version:
        description: Strategy version
        required: true
        default: V9.1
        type: string
      portfolio_id:
        description: Persistent paper portfolio ID
        required: true
        default: V92_PRODUCTION_PAPER_V91
        type: string
      min_history:
        description: Minimum ledger rows before full risk analytics
        required: true
        default: "5"
        type: string
  schedule:
    - cron: "5 9 * * 1-5"

permissions:
  contents: read
concurrency:
  group: gpt-quant-phase351-production-paper-performance-analytics
  cancel-in-progress: false

jobs:
  production-paper-performance-analytics:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
      PAPER_STRATEGY_VERSION: ${{ inputs.strategy_version || 'V9.1' }}
      PAPER_TRADING_MODE: SHADOW_ONLY_NO_BROKER
      PHASE351_PORTFOLIO_ID: ${{ inputs.portfolio_id || 'V92_PRODUCTION_PAPER_V91' }}
      PHASE351_MIN_HISTORY: ${{ inputs.min_history || '5' }}
      PHASE351_RISK_FREE_RATE_ANNUAL: "0"
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install runtime dependencies
        run: python -m pip install --upgrade pip requests
      - name: Validate Phase 3.5.1 safety contract
        shell: bash
        run: |
          set -euo pipefail
          test -n "${SUPABASE_URL:-}"
          test -n "${SUPABASE_SERVICE_ROLE_KEY:-}"
          test -f automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py
          test -f supabase/PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS.sql
          grep -q 'PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS_RISK_METRICS_ENGINE' automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py
          grep -q '"broker_order_submission_enabled":False' automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py
          grep -q '"real_money_trading_enabled":False' automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py
          echo "Phase 3.5.1 safety contract: PASS"
      - name: Execute Phase 3.5.1 analytics engine
        run: python automation/v92/paper_trading_phase351_production_paper_performance_analytics_risk_metrics_engine.py
      - name: Validate Phase 3.5.1 output
        shell: bash
        run: |
          set -euo pipefail
          test -f phase351_output/phase351_performance_analytics.json
          python - <<'PY'
          import json
          from pathlib import Path
          d=json.loads(Path("phase351_output/phase351_performance_analytics.json").read_text(encoding="utf-8"))
          assert d["version"]=="3.5.1", d
          assert d["status"]=="PASS", d
          assert d["analytics_written"] is True, d
          assert d["analytics_state"] in {"ANALYTICS_READY","INSUFFICIENT_HISTORY_VALID_STATE"}, d
          assert d["ledger_rows"]>=1, d
          assert d["current_nav"]>=0, d
          assert d["max_drawdown"]<=1e-12, d
          assert d["synthetic_market_data"] is False, d
          assert d["synthetic_signals"] is False, d
          assert d["fake_prices_allowed"] is False, d
          assert d["broker_api_used"] is False, d
          assert d["broker_credentials_used"] is False, d
          assert d["broker_order_submission_enabled"] is False, d
          assert d["real_money_trading_enabled"] is False, d
          assert d["live_money_release_authorized"] is False, d
          assert d["fail_closed_policy"] is True, d
          print("Phase 3.5.1 output validation: PASS")
          PY
      - name: Upload Phase 3.5.1 evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase351-performance-analytics-${{ github.run_id }}
          path: phase351_output/
          if-no-files-found: warn
          retention-days: 90
'@
Set-Content -LiteralPath $workflowTarget -Value $workflow -Encoding UTF8
Write-Host "Wrote: $workflowTarget" -ForegroundColor Green

Section "Static validation"
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) { $pythonCmd = "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { $pythonCmd = "py" } else { Fail "Python was not found in PATH." }
if ($pythonCmd -eq "py") { & py -3 -m py_compile $pythonTarget } else { & python -m py_compile $pythonTarget }
if ($LASTEXITCODE -ne 0) { Fail "Python compile validation failed." }
Write-Host "Python compile: PASS" -ForegroundColor Green
$source=Get-Content -LiteralPath $pythonTarget -Raw
$needles=@('PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS_RISK_METRICS_ENGINE','paper_performance_ledger_v92','paper_performance_analytics_v92','INSUFFICIENT_HISTORY_VALID_STATE','ANALYTICS_READY','annualized_volatility','sharpe_ratio','max_drawdown','win_rate','profit_factor','"broker_order_submission_enabled":False','"real_money_trading_enabled":False')
foreach($needle in $needles){ if(-not $source.Contains($needle)){ Fail "Required Phase 3.5.1 token missing: $needle" } }
Write-Host "Phase 3.5.1 analytics/risk contract scan: PASS" -ForegroundColor Green

Section "Git diff"
& git status --short
& git diff -- $sqlTarget $pythonTarget $workflowTarget

Section "DEPLOY COMPLETE"
Write-Host "Created/updated:" -ForegroundColor Green
Write-Host "  $sqlTarget"
Write-Host "  $pythonTarget"
Write-Host "  $workflowTarget"
Write-Host ""
Write-Host "Phase 3.5.1 canonical flow:" -ForegroundColor Cyan
Write-Host "  Phase 3.5.0 paper_performance_ledger_v92"
Write-Host "      -> return history"
Write-Host "      -> volatility / Sharpe / drawdown / win-rate / profit-factor"
Write-Host "      -> paper_performance_analytics_v92"
Write-Host ""
Write-Host "Valid analytics states:" -ForegroundColor Yellow
Write-Host "  INSUFFICIENT_HISTORY_VALID_STATE  (valid PASS while history < minimum)"
Write-Host "  ANALYTICS_READY                   (full analytics active)"
Write-Host ""
Write-Host "Supabase SQL required before first Action run:" -ForegroundColor Yellow
Write-Host "  Run: supabase/PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS.sql"
Write-Host ""
Write-Host "Schedule:" -ForegroundColor Cyan
Write-Host "  Phase 3.5.0: 08:50 UTC / 16:50 Taiwan weekdays"
Write-Host "  Phase 3.5.1: 09:05 UTC / 17:05 Taiwan weekdays"
Write-Host ""
Write-Host "Hard safety locks:" -ForegroundColor Yellow
Write-Host "  Synthetic market data/signals: DISABLED"
Write-Host "  Fake prices: DISABLED"
Write-Host "  Broker API/credentials/order submission: DISABLED"
Write-Host "  Real-money trading/live-money release: DISABLED"
Write-Host "  Fail-closed: ENABLED"
Write-Host ""
Write-Host "Next:" -ForegroundColor Yellow
Write-Host "  1) Run Supabase SQL: PHASE351_PRODUCTION_PAPER_PERFORMANCE_ANALYTICS.sql"
Write-Host "  2) Review GitHub Desktop changes."
Write-Host "  3) Commit and Push origin."
Write-Host "  4) GitHub Actions -> GPT Quant Phase 3.5.1."
Write-Host "  5) Run once manually with defaults."
Write-Host "  6) Confirm Analytics Status = PASS and Analytics State is valid."
Write-Host ""
Write-Host "Backup folder: $backupRoot" -ForegroundColor DarkGray
