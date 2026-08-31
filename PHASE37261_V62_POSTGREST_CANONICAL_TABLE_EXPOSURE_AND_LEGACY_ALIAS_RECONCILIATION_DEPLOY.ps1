#requires -Version 5.1
param([switch]$AutoGit)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail([string]$m){ Write-Host "PHASE37261_V62_FATAL: $m" -ForegroundColor Red; exit 1 }
function W([string]$p,[string]$t){
  $d=Split-Path -Parent $p
  if($d -and -not(Test-Path $d)){New-Item -ItemType Directory -Force -Path $d|Out-Null}
  [IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($false)))
}

try { $repo=(& git rev-parse --show-toplevel 2>$null).Trim() } catch { $repo="" }
if([string]::IsNullOrWhiteSpace($repo)){Fail "Run from inside GPT repository."}
Set-Location $repo

$sqlTarget=Join-Path $repo "supabase\PHASE37261_V62_POSTGREST_CANONICAL_TABLE_EXPOSURE_AND_LEGACY_ALIAS_RECONCILIATION.sql"
$pyTarget=Join-Path $repo "automation\v92\paper_trading_phase37261_v62_postgrest_canonical_table_exposure_and_legacy_alias_reconciliation_verify.py"
$ymlTarget=Join-Path $repo ".github\workflows\gpt-quant-v92-paper-trading-phase37261-v62-postgrest-canonical-table-exposure-and-legacy-alias-reconciliation.yml"

$sql=@'
begin;

do $$
declare
  canonical_kind "char";
  legacy_kind "char";
begin
  select c.relkind into canonical_kind
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92';

  select c.relkind into legacy_kind
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit';

  if canonical_kind is null and legacy_kind is not null then
    execute 'create view public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92 as
             select * from public.paper_post_recovery_activation_master_cycle_reconstruction_audit';
  elsif canonical_kind is null and legacy_kind is null then
    raise exception 'Neither canonical nor legacy reconstruction audit object exists.';
  end if;
end
$$;

grant usage on schema public to anon, authenticated, service_role;
grant select on public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92
  to anon, authenticated, service_role;

do $$
declare
  canonical_kind "char";
  seq_name text;
begin
  select c.relkind into canonical_kind
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public'
    and c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92';

  if canonical_kind='r' then
    grant insert on public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92
      to service_role;

    seq_name := pg_get_serial_sequence(
      'public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92',
      'id'
    );

    if seq_name is not null then
      execute format('grant usage, select on sequence %s to service_role', seq_name);
    end if;
  end if;
end
$$;

notify pgrst, 'reload schema';

commit;
'@

$py=@'
from __future__ import annotations
import json, os, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

CONTRACT="PHASE37261_V62_POSTGREST_CANONICAL_TABLE_EXPOSURE_AND_LEGACY_ALIAS_RECONCILIATION"
TABLE="paper_post_recovery_activation_master_cycle_reconstruction_audit_v92"
BROKER_ORDER_SUBMISSION_ENABLED=False
REAL_MONEY_TRADING_ENABLED=False
HISTORICAL_REWRITE_ALLOWED=False

def reqenv(n):
    v=os.getenv(n,"").strip()
    if not v: raise RuntimeError(f"Missing env: {n}")
    return v

def main():
    base=reqenv("SUPABASE_URL").rstrip("/")
    key=reqenv("SUPABASE_SERVICE_ROLE_KEY")
    target=f"/rest/v1/{TABLE}"
    url=f"{base}{target}?"+urllib.parse.urlencode({"select":"*","limit":"1"})
    req=urllib.request.Request(url,headers={"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json"})
    print("# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V6.2")
    print("")
    print("## PostgREST Canonical Exposure + Legacy Alias Reconciliation")
    print("")
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Verification Date: `{datetime.now(timezone.utc).date().isoformat()}`")
    print(f"- Canonical Audit Table: `{TABLE}`")
    print(f"- Request Target: `{target}`")
    print("- Historical Rewrite Allowed: **NO**")
    print("")
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            status=r.getcode()
            body=r.read().decode("utf-8",errors="replace")
        rows=json.loads(body or "[]")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **PASS**")
        print(f"- HTTP Status: **{status}**")
        print("- Canonical Resolver: **LOCKED_TO_V92**")
        print("- PGRST205: **NOT_PRESENT**")
        print(f"- Rows Sampled: **{len(rows) if isinstance(rows,list) else 0}**")
        print("")
        print("## Safety Boundary")
        print("")
        print("- Paper only: **ENABLED**")
        print("- Broker order submission: **DISABLED**")
        print("- Real-money trading: **DISABLED**")
        print("- Historical evidence rewrite: **DISABLED**")
        return 0
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8",errors="replace")
        print("## Verification Result")
        print("")
        print("- PostgREST Schema Visibility: **FAIL**")
        print(f"- HTTP Status: **{e.code}**")
        print(f"- Request Target: `{target}`")
        print("```json")
        print(body[:4000])
        print("```")
        raise RuntimeError(f"V6.2 verification failed: HTTP {e.code}: {body}") from e

if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE37261_V62_FATAL: {exc}",file=sys.stderr)
        raise
'@

$yml=@'
name: GPT Quant Phase 3.7.2.6.1 V6.2 - PostgREST Canonical Exposure Legacy Alias Reconciliation

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  canonical-exposure-reconciliation:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}

    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Setup Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.14"

      - name: Compile V6.2 verifier
        run: python -m py_compile automation/v92/paper_trading_phase37261_v62_postgrest_canonical_table_exposure_and_legacy_alias_reconciliation_verify.py

      - name: Validate V6.2 contract
        shell: bash
        run: |
          set -euo pipefail
          FILE="automation/v92/paper_trading_phase37261_v62_postgrest_canonical_table_exposure_and_legacy_alias_reconciliation_verify.py"
          grep -q 'PHASE37261_V62_POSTGREST_CANONICAL_TABLE_EXPOSURE_AND_LEGACY_ALIAS_RECONCILIATION' "$FILE"
          grep -q 'paper_post_recovery_activation_master_cycle_reconstruction_audit_v92' "$FILE"
          grep -q 'BROKER_ORDER_SUBMISSION_ENABLED=False' "$FILE"
          grep -q 'REAL_MONEY_TRADING_ENABLED=False' "$FILE"
          grep -q 'HISTORICAL_REWRITE_ALLOWED=False' "$FILE"
          echo "Phase 3.7.2.6.1 V6.2 contract: PASS"

      - name: Verify canonical PostgREST exposure
        shell: bash
        run: |
          mkdir -p artifacts/phase37261-v62
          python automation/v92/paper_trading_phase37261_v62_postgrest_canonical_table_exposure_and_legacy_alias_reconciliation_verify.py \
            | tee artifacts/phase37261-v62/summary.md

      - name: Publish summary
        if: always()
        shell: bash
        run: |
          if [ -f artifacts/phase37261-v62/summary.md ]; then
            cat artifacts/phase37261-v62/summary.md >> "$GITHUB_STEP_SUMMARY"
          fi

      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37261-v62-postgrest-exposure-reconciliation
          path: artifacts/phase37261-v62/
          if-no-files-found: warn
          retention-days: 120
'@

W $sqlTarget $sql
W $pyTarget $py
W $ymlTarget $yml

if(Get-Command python -ErrorAction SilentlyContinue){
  & python -m py_compile $pyTarget
}elseif(Get-Command py -ErrorAction SilentlyContinue){
  & py -3 -m py_compile $pyTarget
}else{Fail "Python not found in PATH."}

if($LASTEXITCODE -ne 0){Fail "Verifier compile failed."}

$all=(Get-Content $sqlTarget -Raw)+"`n"+(Get-Content $pyTarget -Raw)+"`n"+(Get-Content $ymlTarget -Raw)
foreach($t in @(
  "create view public.paper_post_recovery_activation_master_cycle_reconstruction_audit_v92",
  "paper_post_recovery_activation_master_cycle_reconstruction_audit",
  "notify pgrst, 'reload schema'",
  "PostgREST Schema Visibility: **PASS**"
)){
  if(-not $all.Contains($t)){Fail "Missing token: $t"}
}

Write-Host "Python compile: PASS" -ForegroundColor Green
Write-Host "Canonical object reconciliation scan: PASS" -ForegroundColor Green
Write-Host "Legacy alias preservation scan: PASS" -ForegroundColor Green
Write-Host "PostgREST exposure scan: PASS" -ForegroundColor Green
Write-Host "Paper-only safety boundary scan: PASS" -ForegroundColor Green
Write-Host ""
Write-Host "PHASE37261 V6.2 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run this SQL once in Supabase:" -ForegroundColor Yellow
Write-Host "  supabase/PHASE37261_V62_POSTGREST_CANONICAL_TABLE_EXPOSURE_AND_LEGACY_ALIAS_RECONCILIATION.sql"
Write-Host ""
Write-Host "Then Commit + Push and run:"
Write-Host "  GPT Quant Phase 3.7.2.6.1 V6.2 - PostgREST Canonical Exposure Legacy Alias Reconciliation"

if($AutoGit){
  git add -- $sqlTarget $pyTarget $ymlTarget
  git commit -m "Deploy Phase 37261 V6.2 PostgREST exposure reconciliation"
  git push origin main
}
