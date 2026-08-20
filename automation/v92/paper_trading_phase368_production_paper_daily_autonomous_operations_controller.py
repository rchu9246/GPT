from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

CONTRACT = "PHASE368_PRODUCTION_PAPER_DAILY_AUTONOMOUS_OPERATIONS_CONTROLLER"
PORTFOLIO_DEFAULT = "V92_PRODUCTION_PAPER_V91"
STRATEGY_DEFAULT = "V9.1"

PAPER_ONLY = True
BROKER_API_USED = False
BROKER_CREDENTIALS_USED = False
BROKER_ORDER_SUBMISSION_ENABLED = False
REAL_MONEY_TRADING_ENABLED = False
LIVE_MONEY_RELEASE_AUTHORIZED = False
FAIL_CLOSED_POLICY = True

CONTROLLER_COMPLETED = "COMPLETED"
CONTROLLER_COMPLETED_OBSERVATION = "COMPLETED_WITH_OBSERVATION"
CONTROLLER_BLOCKED = "BLOCKED"
CONTROLLER_FAILED = "FAILED"
CONTROLLER_FAIL_CLOSED = "FAIL_CLOSED"

ALLOWED_ACTIVATION = {"ACTIVE", "ACTIVE_WITH_OBSERVATION"}
ALLOWED_QUALIFICATION = {"QUALIFIED", "QUALIFIED_WITH_OBSERVATION"}
ALLOWED_SUPERVISION = {"CONTINUE_ACTIVE", "CONTINUE_WITH_OBSERVATION"}
PASS_MASTER_STATES = {
    "PASS",
    "COMPLETED",
    "DAILY_MASTER_CYCLE_COMPLETED",
    "MASTER_CYCLE_COMPLETED",
}

def env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""

def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class Supabase:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def request(
        self,
        method: str,
        table: str,
        query: str = "",
        payload: Optional[Any] = None,
        prefer: Optional[str] = None,
    ) -> Any:
        endpoint = f"{self.url}/rest/v1/{table}"
        if query:
            endpoint += "?" + query
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, headers=headers, data=data, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body.strip() else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{table}: HTTP {exc.code}: {body}") from exc

    def get(self, table: str, query: str) -> List[Dict[str, Any]]:
        value = self.request("GET", table, query=query)
        return value if isinstance(value, list) else []

    def upsert(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        query = "on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
        self.request(
            "POST",
            table,
            query=query,
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )

def latest(sb: Supabase, table: str, portfolio_id: str, order_column: str) -> Optional[Dict[str, Any]]:
    query = (
        "select=*"
        "&portfolio_id=eq." + urllib.parse.quote(portfolio_id, safe="")
        + f"&order={order_column}.desc&limit=1"
    )
    rows = sb.get(table, query)
    return rows[0] if rows else None

def master_state(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return "MISSING"
    return str(
        row.get("cycle_status")
        or row.get("master_status")
        or row.get("final_state")
        or row.get("status")
        or "UNKNOWN"
    ).upper()

def preflight(supervision: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if supervision is None:
        return {
            "authorized": False,
            "activation_state": "MISSING",
            "qualification_state": "MISSING",
            "supervision_state": "MISSING",
            "supervision_score": 0.0,
            "reason": "RUNTIME_SUPERVISION_MISSING",
            "observation": False,
        }

    activation_state = str(supervision.get("activation_state") or "MISSING").upper()
    qualification_state = str(supervision.get("qualification_state") or "MISSING").upper()
    supervision_state = str(supervision.get("supervision_state") or "MISSING").upper()
    continued = as_bool(supervision.get("autonomous_paper_operations_continued"), False)
    revoked = as_bool(supervision.get("safety_revocation_triggered"), False)
    score = float(supervision.get("supervision_score") or 0.0)

    reasons: List[str] = []
    if activation_state not in ALLOWED_ACTIVATION:
        reasons.append("ACTIVATION_NOT_ACTIVE")
    if qualification_state not in ALLOWED_QUALIFICATION:
        reasons.append("QUALIFICATION_NOT_QUALIFIED")
    if supervision_state not in ALLOWED_SUPERVISION:
        reasons.append("SUPERVISION_NOT_CONTINUABLE")
    if not continued:
        reasons.append("AUTONOMOUS_CONTINUATION_NOT_AUTHORIZED")
    if revoked:
        reasons.append("SAFETY_REVOCATION_ALREADY_TRIGGERED")

    return {
        "authorized": not reasons,
        "activation_state": activation_state,
        "qualification_state": qualification_state,
        "supervision_state": supervision_state,
        "supervision_score": score,
        "reason": "PRECHECK_PASS" if not reasons else "|".join(reasons),
        "observation": (
            activation_state == "ACTIVE_WITH_OBSERVATION"
            or qualification_state == "QUALIFIED_WITH_OBSERVATION"
            or supervision_state == "CONTINUE_WITH_OBSERVATION"
        ),
    }

def run_master(approver: str, portfolio_id: str, strategy_version: str) -> subprocess.CompletedProcess[str]:
    script = os.path.join(
        os.getcwd(),
        "automation",
        "v92",
        "paper_trading_phase360_production_paper_daily_master_orchestrator.py",
    )
    if not os.path.isfile(script):
        raise RuntimeError("Phase 3.6.0 master orchestrator missing")

    env = os.environ.copy()
    env["PAPER_TRADING_MODE"] = "SHADOW_ONLY_NO_BROKER"
    env["PAPER_STRATEGY_VERSION"] = strategy_version
    env["STRATEGY_VERSION"] = strategy_version
    env["PHASE360_PORTFOLIO_ID"] = portfolio_id
    for phase in ("350", "351", "352", "353", "354", "355", "356"):
        env[f"PHASE{phase}_PORTFOLIO_ID"] = portfolio_id

    return subprocess.run(
        [sys.executable, script, "--approver", approver],
        env=env,
        text=True,
        capture_output=True,
        timeout=int(os.getenv("PHASE368_MASTER_TIMEOUT_SECONDS", "4800")),
        check=False,
    )

def persist(
    sb: Supabase,
    args: argparse.Namespace,
    state: str,
    pre: Dict[str, Any],
    master: Optional[Dict[str, Any]],
    executed: bool,
    exit_code: int,
    reasons: List[str],
    stdout_tail: str = "",
    stderr_tail: str = "",
) -> str:
    final_master_state = master_state(master)
    passed = state in {CONTROLLER_COMPLETED, CONTROLLER_COMPLETED_OBSERVATION}

    evidence = {
        "contract": CONTRACT,
        "controller_date": args.controller_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "controller_state": state,
        "preflight": pre,
        "master_cycle_state": final_master_state,
        "daily_paper_cycle_executed": executed,
        "master_exit_code": exit_code,
        "reason_codes": reasons,
        "safety": {
            "paper_only": True,
            "broker_api_used": False,
            "broker_credentials_used": False,
            "broker_order_submission_enabled": False,
            "real_money_trading_enabled": False,
            "live_money_release_authorized": False,
            "fail_closed_policy": True,
        },
    }
    sha = stable_hash(evidence)

    payload = {
        "controller_date": args.controller_date,
        "portfolio_id": args.portfolio_id,
        "strategy_version": args.strategy_version,
        "contract": CONTRACT,
        "controller_state": state,
        "controller_passed": passed,
        "autonomous_daily_operations_authorized": bool(pre["authorized"]),
        "daily_paper_cycle_executed": executed,
        "activation_state": pre["activation_state"],
        "qualification_state": pre["qualification_state"],
        "runtime_supervision_state": pre["supervision_state"],
        "runtime_supervision_score": pre["supervision_score"],
        "master_cycle_state": final_master_state,
        "master_exit_code": exit_code,
        "safety_revocation_triggered": state in {CONTROLLER_BLOCKED, CONTROLLER_FAIL_CLOSED},
        "reason_codes": reasons,
        "paper_only": True,
        "broker_api_used": False,
        "broker_credentials_used": False,
        "broker_order_submission_enabled": False,
        "real_money_trading_enabled": False,
        "live_money_release_authorized": False,
        "fail_closed_policy": True,
        "evidence_sha256": sha,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    sb.upsert("paper_daily_autonomous_controller_v92", payload, "portfolio_id,controller_date")

    audit = dict(payload)
    audit.pop("updated_at", None)
    audit["stdout_tail"] = stdout_tail[-4000:]
    audit["stderr_tail"] = stderr_tail[-4000:]
    audit["created_at"] = datetime.now(timezone.utc).isoformat()
    sb.request(
        "POST",
        "paper_daily_autonomous_controller_audit_v92",
        payload=audit,
        prefer="return=minimal",
    )
    return sha

def print_summary(
    args: argparse.Namespace,
    state: str,
    pre: Dict[str, Any],
    master: Optional[Dict[str, Any]],
    executed: bool,
    reasons: List[str],
    sha: str,
) -> None:
    print("# GPT Quant V9.2 Paper Trading - Phase 3.6.8")
    print()
    print("## Production Paper Daily Autonomous Operations Controller")
    print()
    print(f"- Contract: `{CONTRACT}`")
    print(f"- Portfolio ID: `{args.portfolio_id}`")
    print(f"- Controller Date: `{args.controller_date}`")
    print(f"- Controller State: **{state}**")
    print(f"- Qualification State: **{pre['qualification_state']}**")
    print(f"- Activation State: **{pre['activation_state']}**")
    print(f"- Runtime Supervision: **{pre['supervision_state']}**")
    print(f"- Runtime Supervision Score: **{pre['supervision_score']:.4f}**")
    print(f"- Daily Master Cycle: **{master_state(master)}**")
    print(f"- Autonomous Daily Operations Authorized: **{'YES' if pre['authorized'] else 'NO'}**")
    print(f"- Daily Paper Cycle Executed: **{'YES' if executed else 'NO'}**")
    print(f"- Safety Revocation Triggered: **{'YES' if state in {CONTROLLER_BLOCKED, CONTROLLER_FAIL_CLOSED} else 'NO'}**")
    print(f"- Final Controller Result: **{'PASS' if state in {CONTROLLER_COMPLETED, CONTROLLER_COMPLETED_OBSERVATION} else 'FAIL_CLOSED'}**")
    print()
    print("## Controller Reasons")
    print()
    for reason in reasons:
        print(f"- `{reason}`")
    print()
    print("## Safety Boundary")
    print()
    print("- Paper only: **ENABLED**")
    print("- Broker API used: **NO**")
    print("- Broker credentials used: **NO**")
    print("- Broker order submission: **DISABLED**")
    print("- Real-money trading: **DISABLED**")
    print("- Live-money release authorized: **NO**")
    print("- Fail-closed policy: **ENABLED**")
    print(f"- Evidence SHA256: `{sha}`")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-id", default=PORTFOLIO_DEFAULT)
    parser.add_argument("--strategy-version", default=STRATEGY_DEFAULT)
    parser.add_argument("--approver", default=os.getenv("PHASE368_APPROVER", "rchu9246"))
    parser.add_argument("--controller-date", default=str(date.today()))
    args = parser.parse_args()

    # Validate date early.
    date.fromisoformat(args.controller_date)
    if not args.approver.strip():
        raise RuntimeError("Approver must not be empty")

    url = env_first("SUPABASE_URL", "VITE_SUPABASE_URL")
    key = env_first(
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
        "VITE_SUPABASE_PUBLISHABLE_KEY",
    )
    if not url or not key:
        raise RuntimeError("Missing Supabase URL/key")

    sb = Supabase(url, key)

    supervision = latest(
        sb,
        "paper_runtime_supervision_state_v92",
        args.portfolio_id,
        "supervision_date",
    )
    pre = preflight(supervision)

    if not pre["authorized"]:
        reasons = ["PRECHECK_BLOCKED", pre["reason"]]
        sha = persist(
            sb, args, CONTROLLER_FAIL_CLOSED, pre, None, False, 0, reasons
        )
        print_summary(args, CONTROLLER_FAIL_CLOSED, pre, None, False, reasons, sha)
        return 2

    before_master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")

    proc = run_master(args.approver.strip(), args.portfolio_id, args.strategy_version)

    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    after_master = latest(sb, "paper_master_cycles_v92", args.portfolio_id, "cycle_date")
    final_master = after_master or before_master
    final_master_state = master_state(final_master)

    if proc.returncode != 0:
        reasons = ["MASTER_ORCHESTRATOR_FAILED", f"MASTER_EXIT_CODE_{proc.returncode}"]
        sha = persist(
            sb,
            args,
            CONTROLLER_FAIL_CLOSED,
            pre,
            final_master,
            True,
            proc.returncode,
            reasons,
            proc.stdout,
            proc.stderr,
        )
        print_summary(args, CONTROLLER_FAIL_CLOSED, pre, final_master, True, reasons, sha)
        return proc.returncode if proc.returncode > 0 else 1

    if final_master_state not in PASS_MASTER_STATES:
        # Phase 3.6.0 historically persists final_state values; accept explicit
        # successful contract evidence when the subprocess passed.
        phase360_pass = "PHASE360 PASS:" in (proc.stdout or "")
        if not phase360_pass:
            reasons = ["MASTER_CANONICAL_STATE_NOT_PASS", final_master_state]
            sha = persist(
                sb,
                args,
                CONTROLLER_FAIL_CLOSED,
                pre,
                final_master,
                True,
                0,
                reasons,
                proc.stdout,
                proc.stderr,
            )
            print_summary(args, CONTROLLER_FAIL_CLOSED, pre, final_master, True, reasons, sha)
            return 3

    state = CONTROLLER_COMPLETED_OBSERVATION if pre["observation"] else CONTROLLER_COMPLETED
    reasons = [
        "AUTONOMOUS_PRECHECK_PASS",
        "DAILY_MASTER_ORCHESTRATOR_PASS",
        "DAILY_AUTONOMOUS_CONTROLLER_PASS",
    ]
    if pre["observation"]:
        reasons.append("AUTHORIZED_WITH_OBSERVATION")

    sha = persist(
        sb,
        args,
        state,
        pre,
        final_master,
        True,
        0,
        reasons,
        proc.stdout,
        proc.stderr,
    )
    print_summary(args, state, pre, final_master, True, reasons, sha)

    out_dir = os.path.join(os.getcwd(), "artifacts", "phase368")
    os.makedirs(out_dir, exist_ok=True)
    evidence = {
        "contract": CONTRACT,
        "controller_state": state,
        "portfolio_id": args.portfolio_id,
        "controller_date": args.controller_date,
        "preflight": pre,
        "master_cycle_state": master_state(final_master),
        "reason_codes": reasons,
        "evidence_sha256": sha,
    }
    with open(
        os.path.join(out_dir, "daily_autonomous_controller_evidence.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"PHASE368_FATAL: {exc}", file=sys.stderr)
        raise