import { useEffect, useMemo, useState } from "react";
import { buildDecisionAlerts, loadLatestSignals } from "../lib/v9Data";
import type { SignalRow } from "../types/v9";
export default function AlertsV91({ onOpenStock }: { onOpenStock: (symbol: string) => void }) {
 const [signals,setSignals]=useState<SignalRow[]>([]); useEffect(()=>{loadLatestSignals().then(setSignals).catch(()=>setSignals([]));},[]); const alerts=useMemo(()=>buildDecisionAlerts(signals),[signals]);
 return <section><div className="page-title"><div><div className="eyebrow">PROACTIVE RISK MONITOR</div><h1>決策警示中心</h1><p>集中呈現機會、弱勢與高風險標的。</p></div></div><div className="alert-board">{alerts.map((alert)=><button key={alert.id} className={`decision-alert severity-${alert.severity.toLowerCase()}`} onClick={()=>alert.symbol&&onOpenStock(alert.symbol)}><small>{alert.severity}</small><strong>{alert.title}</strong><span>{alert.message}</span></button>)}</div></section>;
}
