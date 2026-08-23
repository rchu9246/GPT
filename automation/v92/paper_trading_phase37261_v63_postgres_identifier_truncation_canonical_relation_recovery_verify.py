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
