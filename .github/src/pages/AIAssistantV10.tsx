import { useEffect, useState } from "react";
import { buildAssistantInsights, loadLatestSignals } from "../lib/v9Data";
import type { AssistantInsight } from "../types/v9";

export default function AIAssistantV10() {
  const [insights, setInsights] = useState<AssistantInsight[]>([]);
  useEffect(() => { loadLatestSignals().then((rows) => setInsights(buildAssistantInsights(rows))).catch(() => setInsights([])); }, []);
  return <section><div className="page-title"><div><div className="eyebrow">V10 AI INVESTMENT COPILOT</div><h1>AI 投資助理</h1><p>把市場狀態、產業輪動與個股訊號轉換成可執行研究重點。</p></div></div><div className="assistant-grid">{insights.map((item) => <article className={`assistant-card tone-${item.tone.toLowerCase()}`} key={item.title}><span>{item.tone === "POSITIVE" ? "機會" : item.tone === "CAUTION" ? "風險" : "觀察"}</span><h3>{item.title}</h3><p>{item.message}</p></article>)}</div></section>;
}
