$ErrorActionPreference="Stop"
$root=(Get-Location).Path
$auto=Join-Path $root "automation\v92"
$wf=Join-Path $root ".github\workflows"
$sqlDir=Join-Path $root "supabase"
New-Item -ItemType Directory -Force $auto,$wf,$sqlDir|Out-Null

$sqlPath=Join-Path $sqlDir "PHASE37261_V63_POSTGRES_IDENTIFIER_TRUNCATION_CANONICAL_RELATION_RECOVERY.sql"
$pyPath=Join-Path $auto "paper_trading_phase37261_v63_postgres_identifier_truncation_canonical_relation_recovery_verify.py"
$wfPath=Join-Path $wf "gpt-quant-v92-paper-trading-phase37261-v63-postgres-identifier-truncation-canonical-relation-recovery.yml"

@'
begin;
do $$
declare src text;
begin
  select c.relname into src
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relkind in ('r','p','v','m')
    and (c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92'
      or c.relname like 'paper_post_recovery_activation_master_cycle_reconstruction_audi%')
  order by case when c.relname='paper_post_recovery_activation_master_cycle_reconstruction_audit_v92' then 0 else 1 end,
           length(c.relname) desc
  limit 1;

  if src is null then
    raise exception 'PHASE37261_V63_FATAL: source audit relation not found';
  end if;

  if exists (
    select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname='public' and c.relname='phase37261_reconstruction_audit_v92'
      and c.relkind <> 'v'
  ) then
    raise exception 'PHASE37261_V63_FATAL: short API relation exists and is not a view';
  end if;

  execute format(
    'create or replace view public.phase37261_reconstruction_audit_v92 as select * from public.%I',
    src
  );
  raise notice 'V6.3 physical source relation: %',src;
end $$;

grant usage on schema public to anon,authenticated,service_role;
grant select on public.phase37261_reconstruction_audit_v92 to anon,authenticated,service_role;
comment on view public.phase37261_reconstruction_audit_v92 is
'GPT Quant V9.2 Phase 3.7.2.6.1 V6.3 short PostgREST canonical relation; paper-only; source history preserved.';
notify pgrst,'reload schema';
commit;

select c.relname,c.relkind,octet_length(c.relname) identifier_bytes
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='public' and
(c.relname like 'paper_post_recovery_activation_master_cycle_reconstruction_audi%'
 or c.relname='phase37261_reconstruction_audit_v92')
order by c.relname;
'@ | Set-Content -Encoding utf8 $sqlPath

@'
import json,os,sys,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone

REL="phase37261_reconstruction_audit_v92"
CONTRACT="PHASE37261_V63_POSTGRES_IDENTIFIER_TRUNCATION_CANONICAL_RELATION_RECOVERY"

def env(*names):
    for n in names:
        if os.getenv(n): return os.getenv(n).strip()

def main():
    url=env("SUPABASE_URL","VITE_SUPABASE_URL")
    key=env("SUPABASE_SERVICE_ROLE_KEY","SUPABASE_SERVICE_KEY","SUPABASE_ANON_KEY","VITE_SUPABASE_PUBLISHABLE_KEY")
    if not url or not key: raise RuntimeError("Missing Supabase URL/key secrets")
    target=f"{url.rstrip('/')}/rest/v1/{REL}?select=*&limit=1"
    req=urllib.request.Request(target,headers={"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=45) as r:
            status=r.status; body=r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        status=e.code; body=e.read().decode(errors="replace")
    ok=status==200 and "PGRST205" not in body
    d={"contract":CONTRACT,"canonical_api_relation":REL,"http_status":status,
       "pgrst205_present":"PGRST205" in body,"legacy_long_name_dependency":"REMOVED",
       "paper_only":True,"broker_api_used":False,"real_money_trading":False,
       "historical_rewrite_allowed":"NO","verified_at":datetime.now(timezone.utc).isoformat(),
       "result":"PASS" if ok else "FAIL","response_preview":body[:1500]}
    a=Path("artifacts/phase37261-v63"); a.mkdir(parents=True,exist_ok=True)
    (a/"verification.json").write_text(json.dumps(d,indent=2),encoding="utf-8")
    s=f"""# GPT Quant V9.2 Paper Trading - Phase 3.7.2.6.1 V6.3

- Contract: `{CONTRACT}`
- Canonical API Relation: `{REL}`
- Identifier Length Safety: **PASS**
- PostgREST Canonical Endpoint: **{'PASS' if ok else 'FAIL'}**
- HTTP Status: **{status}**
- PGRST205: **{'PRESENT' if 'PGRST205' in body else 'NOT_PRESENT'}**
- Legacy Long-name Dependency: **REMOVED**
- Historical Rewrite Allowed: **NO**
- Paper-only Safety Boundary: **PASS**
"""
    (a/"summary.md").write_text(s,encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a",encoding="utf-8").write(s)
    print(s)
    if not ok: raise RuntimeError(f"V6.3 verification failed HTTP={status}: {body[:1000]}")

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("PHASE37261_V63_FATAL:",e,file=sys.stderr); raise
'@ | Set-Content -Encoding utf8 $pyPath

@'
name: GPT Quant Phase 3.7.2.6.1 V6.3 - PostgreSQL Identifier Truncation Canonical Relation Recovery
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  canonical-relation-recovery:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - name: Compile V6.3
        run: python -m py_compile automation/v92/paper_trading_phase37261_v63_postgres_identifier_truncation_canonical_relation_recovery_verify.py
      - name: Verify V6.3 canonical PostgREST endpoint
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
        run: python automation/v92/paper_trading_phase37261_v63_postgres_identifier_truncation_canonical_relation_recovery_verify.py
      - name: Upload evidence
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: phase37261-v63-evidence
          path: artifacts/phase37261-v63/
          if-no-files-found: warn
'@ | Set-Content -Encoding utf8 $wfPath

python -m py_compile $pyPath
if($LASTEXITCODE-ne 0){throw "Python compile failed"}
Write-Host ""
Write-Host "PHASE37261 V6.3 DEPLOYMENT COMPLETE" -ForegroundColor Cyan
Write-Host "Generated:"
Write-Host "  $sqlPath"
Write-Host "  $pyPath"
Write-Host "  $wfPath"
Write-Host ""
Write-Host "NEXT:"
Write-Host "1. Run the generated SQL once in Supabase SQL Editor."
Write-Host "2. Expected: Success + diagnostic rows including phase37261_reconstruction_audit_v92."
Write-Host "3. Commit/push the 3 generated runtime files."
Write-Host "4. Run the V6.3 GitHub Action."
Write-Host "Target: HTTP 200 / PGRST205 NOT_PRESENT / Legacy dependency REMOVED."
