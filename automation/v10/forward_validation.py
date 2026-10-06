"""Forward-only all-market shadow paper validation; never broker-capable."""
from __future__ import annotations
import hashlib, json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from pathlib import Path
from statistics import median, pstdev
from .factors import FACTOR_NAMES, FACTOR_VERSION, HYPOTHESIS_WEIGHTS
from .ledger import AppendOnlyLedger, mark_to_market, replay_account
from .models import MarketBar, StrategyIntent
from .phase2_research import (BASELINE_COST, COST_MODEL_VERSION, INITIAL_CASH,
    LIQUIDITY_LOOKBACK, MAX_POSITION_WEIGHT, MINIMUM_HISTORY, MINIMUM_MEDIAN_TURNOVER,
    MINIMUM_PRICE, PRE_REGISTERED_CONFIGS, PROMOTION_MAX_DRAWDOWN, TARGET_EXPOSURE,
    ResearchConfig, TwseDailyTableProvider)
from .risk import RiskEngine
from .safety import SAFETY

FORWARD_SCHEMA_VERSION = 1
UNIVERSE_VERSION = "TWSE_DAILY_ELIGIBLE_V1"
RISK_VERSION = "V10_LONG_ONLY_RISK_V1"
MINIMUM_QUALIFICATION_DAYS = 60
PRELIMINARY_DAYS = 20
LABELS = ("RESEARCH_ONLY", "UNPROMOTED", "SHADOW_PAPER")

class ForwardValidationStatus(str, Enum):
    COLLECTING = "COLLECTING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    QUALIFIED = "QUALIFIED"

@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    hypothesis: str
    factor_version: str
    weights: tuple[tuple[str, str], ...]
    top_n: int
    rebalance_frequency: str
    risk_version: str
    cost_model_version: str
    universe_version: str
    labels: tuple[str, ...]
    spec_fingerprint: str

    @classmethod
    def from_config(cls, config: ResearchConfig) -> "StrategySpec":
        strategy_id = f"V10_SHADOW_{config.name}_V1"
        body = {"strategy_id": strategy_id, "hypothesis": config.hypothesis,
                "factor_version": FACTOR_VERSION,
                "weights": sorted((k, str(v)) for k, v in HYPOTHESIS_WEIGHTS[config.hypothesis].items()),
                "top_n": config.top_n, "rebalance_frequency": config.rebalance,
                "risk_version": RISK_VERSION, "cost_model_version": COST_MODEL_VERSION,
                "universe_version": UNIVERSE_VERSION, "labels": LABELS}
        fingerprint = hashlib.sha256(json.dumps(body, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
        return cls(strategy_id, config.hypothesis, FACTOR_VERSION, tuple(body["weights"]),
                   config.top_n, config.rebalance, RISK_VERSION, COST_MODEL_VERSION,
                   UNIVERSE_VERSION, LABELS, fingerprint)

SHADOW_STRATEGY_REGISTRY = tuple(StrategySpec.from_config(c) for c in PRE_REGISTERED_CONFIGS)
REGISTRY_FINGERPRINT = hashlib.sha256("|".join(s.spec_fingerprint for s in SHADOW_STRATEGY_REGISTRY).encode()).hexdigest()

def account_id(spec: StrategySpec) -> str:
    return hashlib.sha256(("FORWARD_SHADOW_ACCOUNT|" + spec.strategy_id).encode()).hexdigest()[:24]

class ForwardStore:
    def __init__(self, root: Path):
        self.root, self.accounts, self.runs, self.reports = root, root/"accounts", root/"runs", root/"reports"
        self.boundary_path, self.registry_path = root/"forward_boundary.json", root/"strategy_registry.json"

    @staticmethod
    def _write_once(path: Path, value: object) -> None:
        text = json.dumps(value, indent=2, default=str, sort_keys=True) + "\n"
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != json.loads(text):
                raise RuntimeError(f"immutable artifact conflict: {path.name}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def initialize(self, start_date: date) -> None:
        SAFETY.assert_safe()
        boundary = {"schema_version": FORWARD_SCHEMA_VERSION,
                    "forward_validation_start_date": start_date.isoformat(),
                    "historical_backfill_allowed": False, "mode": "FORWARD_SHADOW"}
        if not self.boundary_path.exists():
            self._write_once(self.boundary_path, boundary)
        elif start_date < self.boundary():
            raise RuntimeError("forward boundary is immutable")
        self._write_once(self.registry_path, {"registry_fingerprint": REGISTRY_FINGERPRINT,
                                             "strategies": [asdict(s) for s in SHADOW_STRATEGY_REGISTRY]})

    def boundary(self) -> date:
        return date.fromisoformat(json.loads(self.boundary_path.read_text(encoding="utf-8"))["forward_validation_start_date"])

    def ledger(self, spec: StrategySpec) -> tuple[AppendOnlyLedger, Path]:
        path = self.accounts/f"{account_id(spec)}.jsonl"
        return (AppendOnlyLedger.load(path) if path.exists() else AppendOnlyLedger()), path

    def completed_dates(self) -> tuple[date, ...]:
        return tuple(sorted(date.fromisoformat(p.stem) for p in self.runs.glob("*.json"))) if self.runs.exists() else ()

    def save_manifest(self, session: date, manifest: dict) -> Path:
        if session < self.boundary():
            raise RuntimeError("historical backfill cannot masquerade as forward evidence")
        path = self.runs/f"{session.isoformat()}.json"
        self._write_once(path, manifest)
        return path

class ForwardMarketData:
    def __init__(self, days: list[dict]):
        self.days = {date.fromisoformat(d["date"]): d for d in days if d.get("benchmark") is not None and d.get("bars")}
        self.bars_by_date, self.history = {}, {}
        for session, day in self.days.items():
            rows = {}
            for row in day["bars"]:
                bar = MarketBar(row["symbol"], session, Decimal(row["open"]), Decimal(row["high"]),
                                Decimal(row["low"]), Decimal(row["close"]), int(row["volume"]),
                                provider="TWSE_MI_INDEX", provider_observation_id=row["observation_id"])
                bar.validate()
                rows[bar.symbol] = bar
                self.history.setdefault(bar.symbol, []).append(bar)
            self.bars_by_date[session] = rows
        for values in self.history.values():
            values.sort(key=lambda b: b.session_date)

    def eligibility(self, session: date):
        eligible, excluded = [], {}
        for symbol, current in sorted(self.bars_by_date.get(session, {}).items()):
            history = [b for b in self.history[symbol] if b.session_date <= session][-MINIMUM_HISTORY:]
            reasons = []
            if len(history) < MINIMUM_HISTORY:
                reasons.append("INSUFFICIENT_HISTORY")
            if current.close < MINIMUM_PRICE:
                reasons.append("INVALID_PRICE")
            if len(history) < LIQUIDITY_LOOKBACK or median([b.close*b.volume for b in history[-LIQUIDITY_LOOKBACK:]]) < MINIMUM_MEDIAN_TURNOVER:
                reasons.append("INSUFFICIENT_LIQUIDITY")
            if reasons:
                excluded[symbol] = tuple(reasons)
            else:
                eligible.append(symbol)
        return tuple(eligible), excluded

    def normalized_factors(self, session: date, eligible: tuple[str, ...]):
        raw = {}
        for symbol in eligible:
            history = [b for b in self.history[symbol] if b.session_date <= session][-MINIMUM_HISTORY:]
            closes = [b.close for b in history]
            returns = [float(closes[i]/closes[i-1]-1) for i in range(1, len(closes))]
            raw[symbol] = {"trend": closes[-1]/(sum(closes[-20:])/Decimal(20))-1,
                "momentum": closes[-1]/closes[-60]-1, "relative_strength": closes[-1]/closes[-20]-1,
                "liquidity": Decimal(median([b.close*b.volume for b in history[-20:]])),
                "low_volatility": -Decimal(str(pstdev(returns[-20:]))),
                "breakout": closes[-1]/max(closes[-60:-1])-1}
        normalized = {s:{} for s in raw}
        for factor in FACTOR_NAMES:
            ordered = sorted(raw, key=lambda s:(raw[s][factor],s))
            denominator = Decimal(max(1,len(ordered)-1))
            for index, symbol in enumerate(ordered):
                normalized[symbol][factor] = Decimal(index)/denominator
        return normalized

def load_cached_market(provider: TwseDailyTableProvider, through: date, lookback_days: int = 180):
    days=[]
    current=through-timedelta(days=lookback_days)
    while current <= through:
        if current.weekday() < 5:
            day=provider.day(current)
            if day.get("bars") and day.get("benchmark") is not None:
                days.append(day)
        current += timedelta(days=1)
    return ForwardMarketData(days)

def _rebalance(spec: StrategySpec, session: date, prior: date|None) -> bool:
    if prior is None:
        return True
    return (session.isocalendar()[:2] != prior.isocalendar()[:2] if spec.rebalance_frequency == "WEEKLY"
            else (session.year,session.month)!=(prior.year,prior.month))

def validation_status(days: int, metrics: dict|None=None) -> ForwardValidationStatus:
    if days < PRELIMINARY_DAYS:
        return ForwardValidationStatus.COLLECTING
    if days < MINIMUM_QUALIFICATION_DAYS:
        return ForwardValidationStatus.INSUFFICIENT_EVIDENCE
    if not metrics:
        return ForwardValidationStatus.REJECTED
    passed = (Decimal(metrics["net_return"])>0 and Decimal(metrics["excess_return"])>0
              and Decimal(metrics["sharpe"])>Decimal("0.5")
              and Decimal(metrics["max_drawdown"])<=PROMOTION_MAX_DRAWDOWN
              and all(metrics.get(k) is True for k in ("accounting_valid","data_integrity_valid","concentration_valid",
                                                    "cost_stress_acceptable","strategy_stable"))
              and metrics.get("single_symbol_dominance") is False)
    return ForwardValidationStatus.QUALIFIED if passed else ForwardValidationStatus.REJECTED

def run_forward_day(data: ForwardMarketData, business_date: date, store: ForwardStore) -> dict:
    SAFETY.assert_safe()
    if business_date not in data.days or len(data.bars_by_date[business_date]) < 500:
        raise RuntimeError("complete authoritative market day unavailable")
    store.initialize(business_date)
    evidence_path=store.root/"market_evidence"/f"{business_date}.json"
    if not evidence_path.exists():
        ForwardStore._write_once(evidence_path, data.days[business_date])
    existing_manifest = store.runs/f"{business_date.isoformat()}.json"
    if existing_manifest.exists():
        existing=json.loads(existing_manifest.read_text(encoding="utf-8"))
        if existing["strategy_registry_fingerprint"] != REGISTRY_FINGERPRINT:
            raise RuntimeError("run registry fingerprint mismatch")
        for spec in SHADOW_STRATEGY_REGISTRY:
            store.ledger(spec)[0]  # reload verifies the complete hash chain
        ForwardStore._write_once(store.reports/f"{business_date.isoformat()}.json",existing)
        return existing
    completed=store.completed_dates()
    if completed and business_date < completed[-1]:
        raise RuntimeError("historical backfill rejected")
    eligible, excluded=data.eligibility(business_date)
    if not eligible:
        raise RuntimeError("eligible universe is empty")
    normalized=data.normalized_factors(business_date,eligible)
    prior=completed[-1] if completed else None
    if prior and any(prior < d < business_date and len(data.bars_by_date[d]) >= 500 for d in data.days):
        raise RuntimeError("intermediate tradable sessions must be processed first")
    accounts=[]; top_output=[]; total_fills=total_events=0
    for spec in SHADOW_STRATEGY_REGISTRY:
        ledger,path=store.ledger(spec)
        state=replay_account(ledger.events,INITIAL_CASH)
        fills=[]
        consumed={dict(e.payload)["target_event_id"] for e in ledger.events if e.event_type=="TARGET_EXECUTED"}
        target_events=[e for e in ledger.events if e.event_type=="TARGETS" and e.event_id not in consumed]
        executing_target = target_events[0] if target_events else None
        if executing_target and date.fromisoformat(dict(executing_target.payload)["signal_date"]) < business_date:
            payload=dict(executing_target.payload)
            signal_date=date.fromisoformat(payload["signal_date"])
            targets=json.loads(payload["targets"])
            executed_symbols={dict(e.payload)["symbol"] for e in ledger.events
                if e.event_type=="TARGET_SYMBOL_EXECUTED" and dict(e.payload)["target_event_id"]==executing_target.event_id}
            day=data.bars_by_date[business_date]
            current=dict(state.positions)
            equity=state.cash+sum((day[s].open*q for s,q in current.items() if s in day),Decimal("0"))
            for symbol in sorted(set(current)|set(targets)):
                if symbol not in day or symbol in executed_symbols:
                    continue
                next_dates=sorted(d for d in data.days if d>signal_date and symbol in data.bars_by_date[d])
                if not next_dates or next_dates[0]!=business_date:
                    raise RuntimeError("next actual symbol tradable open cannot be proven")
                target_qty=int((equity*Decimal(targets.get(symbol,"0"))/day[symbol].open).to_integral_value(rounding=ROUND_DOWN))
                quantity=target_qty-current.get(symbol,0)
                if quantity>0:
                    affordable=int((state.cash/(day[symbol].open*(1+BASELINE_COST.buy_commission))).to_integral_value(rounding=ROUND_DOWN))
                    quantity=min(quantity,affordable)
                if not quantity:
                    ledger.append(f"{executing_target.event_id}|{symbol}","TARGET_SYMBOL_EXECUTED",business_date,
                        {"target_event_id":executing_target.event_id,"symbol":symbol})
                    continue
                notional=day[symbol].open*abs(quantity)
                fee=notional*(BASELINE_COST.buy_commission if quantity>0 else BASELINE_COST.sell_commission+BASELINE_COST.sell_tax)
                fill_id=hashlib.sha256(f"{spec.strategy_id}|{signal_date}|{business_date}|{symbol}|{quantity}|{day[symbol].open}".encode()).hexdigest()
                ledger.append(fill_id,"PAPER_FILL",business_date,{"fill_id":fill_id,"symbol":symbol,
                    "quantity":quantity,"price":day[symbol].open,"fee":fee,"lineage":spec.spec_fingerprint,
                    "signal_date":signal_date.isoformat(),"target_event_id":executing_target.event_id,
                    "reference":"TWSE_ACTUAL_NEXT_TRADABLE_OPEN","observation_id":day[symbol].provider_observation_id})
                ledger.append(f"{executing_target.event_id}|{symbol}","TARGET_SYMBOL_EXECUTED",business_date,
                    {"target_event_id":executing_target.event_id,"symbol":symbol})
                fills.append(fill_id)
                state=replay_account(ledger.events,INITIAL_CASH)
            if all(symbol in day for symbol in set(current)|set(targets)):
                consumed_id=hashlib.sha256(f"TARGET_EXECUTED|{spec.strategy_id}|{executing_target.event_id}|{business_date}".encode()).hexdigest()
                ledger.append(consumed_id,"TARGET_EXECUTED",business_date,{"target_event_id":executing_target.event_id,"execution_date":business_date.isoformat()})
        weights=dict(spec.weights)
        denominator=sum((Decimal(v) for v in weights.values()),Decimal("0"))
        scores={s:sum((normalized[s][f]*Decimal(weights[f]) for f in FACTOR_NAMES),Decimal("0"))/denominator for s in eligible}
        ranked=sorted(scores,key=lambda s:(-scores[s],s))
        selected=ranked[:spec.top_n]
        weight=min(MAX_POSITION_WEIGHT,TARGET_EXPOSURE/Decimal(len(selected)))
        risk=RiskEngine(); exposure=Decimal("0"); targets={}; risk_decisions={}
        for symbol in selected:
            intent=StrategyIntent(symbol,business_date,weight,f"{spec.strategy_id}:{spec.spec_fingerprint}")
            decision=risk.decide(intent,exposure,Decimal("0"),Decimal("0"),True)
            targets[symbol]=str(decision.approved_weight); exposure+=decision.approved_weight
            risk_decisions[symbol]=decision.decision
        if _rebalance(spec,business_date,prior):
            event_id=hashlib.sha256(f"TARGETS|{spec.strategy_id}|{business_date}".encode()).hexdigest()
            ledger.append(event_id,"TARGETS",business_date,{"signal_date":business_date.isoformat(),
                "targets":json.dumps(targets,separators=(",",":"),sort_keys=True),
                "signal_scores":json.dumps({s:str(scores[s]) for s in targets},sort_keys=True),
                "spec_fingerprint":spec.spec_fingerprint})
        ledger.persist(path)
        fills=[dict(e.payload)["fill_id"] for e in ledger.events if e.event_type=="PAPER_FILL" and e.event_date==business_date]
        state=replay_account(ledger.events,INITIAL_CASH)
        closes={s:b.close for s,b in data.bars_by_date[business_date].items()}
        market_value,equity=mark_to_market(state,closes)
        if state.cash+market_value!=equity:
            raise RuntimeError("accounting identity failed")
        prior_account = None
        if completed:
            prior_manifest=json.loads((store.runs/f"{completed[-1].isoformat()}.json").read_text(encoding="utf-8"))
            prior_account=next(a for a in prior_manifest["strategies"] if a["strategy_id"]==spec.strategy_id)
        prior_equity=Decimal(prior_account["equity"]) if prior_account else INITIAL_CASH
        daily_pnl=equity-prior_equity
        cumulative_return=equity/INITIAL_CASH-1
        prior_rows=[]
        for completed_date in completed:
            prior_manifest=json.loads((store.runs/f"{completed_date.isoformat()}.json").read_text(encoding="utf-8"))
            prior_rows.append(next(a for a in prior_manifest["strategies"] if a["strategy_id"]==spec.strategy_id))
        equity_history=[INITIAL_CASH]+[Decimal(a["equity"]) for a in prior_rows]+[equity]
        daily_returns=[equity_history[i]/equity_history[i-1]-1 for i in range(1,len(equity_history))]
        deviation=pstdev([float(v) for v in daily_returns]) if len(daily_returns)>1 else 0
        sharpe=Decimal(str(sum(float(v) for v in daily_returns)/len(daily_returns)/deviation*(252**0.5))) if deviation else Decimal("0")
        peak=equity_history[0]; max_drawdown=Decimal("0")
        for value in equity_history:
            peak=max(peak,value); max_drawdown=max(max_drawdown,Decimal("1")-value/peak)
        changes=[equity_history[i]-equity_history[i-1] for i in range(1,len(equity_history))]
        gross_profit=sum((max(v,Decimal("0")) for v in changes),Decimal("0"))
        gross_loss=sum((max(-v,Decimal("0")) for v in changes),Decimal("0"))
        profit_factor=gross_profit/gross_loss if gross_loss else Decimal("999999") if gross_profit else Decimal("0")
        win_rate=Decimal(sum(v>0 for v in changes))/Decimal(max(1,len(changes)))
        realized=state.realized_pnl
        costs=dict(state.average_costs)
        unrealized=sum(((closes[s]-costs[s])*q for s,q in state.positions if s in closes),Decimal("0"))
        exposure=market_value/equity if equity else Decimal("0")
        daily_notional=sum((data.bars_by_date[business_date][dict(e.payload)["symbol"]].open*abs(int(dict(e.payload)["quantity"]))
                            for e in ledger.events if e.event_type=="PAPER_FILL" and e.event_date==business_date),Decimal("0"))
        turnover=daily_notional/prior_equity if prior_equity else Decimal("0")
        prior_fees=Decimal(prior_account["transaction_cost_cumulative"]) if prior_account else Decimal("0")
        cumulative_turnover=sum((Decimal(a.get("turnover","0")) for a in prior_rows),Decimal("0"))+turnover
        concentration=max((closes[s]*q/equity for s,q in state.positions if s in closes),default=Decimal("0"))
        stress_extra_cost=state.fees+cumulative_turnover*INITIAL_CASH*Decimal("0.001")
        metrics={"trading_days":len(completed)+1,"net_return":str(cumulative_return),
            "benchmark_return":"0","excess_return":"0","sharpe":str(sharpe),
            "max_drawdown":str(max_drawdown),"profit_factor":str(profit_factor),
            "win_rate":str(win_rate),"turnover":str(cumulative_turnover),"cost_drag":str(state.fees),
            "accounting_valid":True,"data_integrity_valid":True,
            "concentration_valid":concentration<=Decimal("0.40"),
            "single_symbol_dominance":concentration>Decimal("0.40"),
            "cost_stress_acceptable":equity-stress_extra_cost>INITIAL_CASH,
            "strategy_stable":len(daily_returns)>=20 and equity/equity_history[-21]-1>0}
        accounts.append({"strategy_id":spec.strategy_id,"account_id":account_id(spec),
            "spec_fingerprint":spec.spec_fingerprint,"equity":str(equity),"cash":str(state.cash),
            "market_value":str(market_value),"daily_pnl":str(daily_pnl),
            "cumulative_pnl":str(equity-INITIAL_CASH),"return":str(cumulative_return),
            "benchmark_return":None,"excess_return":None,"realized_pnl":str(realized),
            "unrealized_pnl":str(unrealized),"drawdown":str(max_drawdown),"exposure":str(exposure),
            "turnover":str(turnover),"transaction_cost":str(state.fees-prior_fees),
            "transaction_cost_cumulative":str(state.fees),"positions":list(state.positions),"fills":fills,"forward_metrics":metrics,
            "execution_status":"FILLED_NEXT_TRADABLE_OPEN" if fills else "PENDING_NEXT_TRADABLE_OPEN",
            "validation_status":validation_status(len(completed)+1,metrics).value})
        total_fills+=len(fills)
        total_events+=len(ledger.events)
        if spec==SHADOW_STRATEGY_REGISTRY[0]:
            top_output=[{"rank":i,"symbol":s,"factor_scores":{f:str(normalized[s][f]) for f in FACTOR_NAMES},
                "composite_score":str(scores[s]),"eligibility":"ELIGIBLE","target_weight":targets.get(s,"0"),
                "strategy_id":spec.strategy_id,"risk_decision":risk_decisions.get(s,"NOT_SELECTED"),
                "order_intent":"TARGET" if s in targets and _rebalance(spec,business_date,prior) else "NONE",
                "execution_status":"PENDING_NEXT_TRADABLE_OPEN" if s in targets and _rebalance(spec,business_date,prior) else "NO_NEW_INTENT"} for i,s in enumerate(ranked[:20],1)]
    benchmark=Decimal(data.days[business_date]["benchmark"])
    first=benchmark
    if completed:
        first=Decimal(json.loads((store.runs/f"{completed[0].isoformat()}.json").read_text(encoding="utf-8"))["benchmark"]["twse_index"])
    benchmark_return=benchmark/first-1
    for account in accounts:
        account["benchmark_return"]=str(benchmark_return)
        account["excess_return"]=str(Decimal(account["return"])-benchmark_return)
        account["forward_metrics"]["benchmark_return"]=str(benchmark_return)
        account["forward_metrics"]["excess_return"]=account["excess_return"]
        account["validation_status"]=validation_status(len(completed)+1,account["forward_metrics"]).value
    benchmark_ledger_path=store.root/"benchmark.jsonl"
    benchmark_ledger=AppendOnlyLedger.load(benchmark_ledger_path) if benchmark_ledger_path.exists() else AppendOnlyLedger()
    benchmark_event_id=hashlib.sha256(f"BENCHMARK|{business_date}|{benchmark}".encode()).hexdigest()
    benchmark_ledger.append(benchmark_event_id,"BENCHMARK_MARK",business_date,{"twse_index":benchmark,"cash_return":0})
    benchmark_ledger.persist(benchmark_ledger_path)
    run_id=hashlib.sha256(f"FORWARD_SHADOW|{business_date}|{REGISTRY_FINGERPRINT}".encode()).hexdigest()
    reasons={r:sum(r in rs for rs in excluded.values()) for r in sorted({x for rs in excluded.values() for x in rs})}
    manifest={"schema_version":1,"run_id":run_id,"mode":"FORWARD_SHADOW","labels":list(LABELS),
        "business_date":business_date.isoformat(),"data_date":business_date.isoformat(),
        "provider":"TWSE_MI_INDEX","data_freshness":"CURRENT_COMPLETE_SESSION",
        "total_symbols":len(data.bars_by_date[business_date]),"eligible_symbols":len(eligible),
        "excluded_symbols":len(excluded),"exclusion_reasons":reasons,
        "strategy_registry_fingerprint":REGISTRY_FINGERPRINT,
        "account_ids":[a["account_id"] for a in accounts],"strategies":accounts,
        "top_candidates":top_output,
        "benchmark":{"cash_return":"0","twse_index":str(benchmark),"twse_return":str(benchmark_return)},
        "forward_trading_days":len(completed)+1,
        "execution_status":"FILLED_NEXT_TRADABLE_OPEN" if total_fills else "PENDING_NEXT_TRADABLE_OPEN",
        "event_count":total_events,"fill_count":total_fills,"broker_orders_created":0,"paper_only":True}
    store.save_manifest(business_date,manifest)
    ForwardStore._write_once(store.reports/f"{business_date.isoformat()}.json",manifest)
    return manifest

def latest_complete_session(provider: TwseDailyTableProvider, as_of: date) -> date:
    current=as_of
    for _ in range(10):
        if current.weekday()<5:
            day=provider.day(current)
            if day.get("benchmark") is not None and len(day.get("bars",[]))>=500:
                return current
        current-=timedelta(days=1)
    raise RuntimeError("no recent complete TWSE session")

