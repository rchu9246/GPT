import { useState } from "react";
import report from "../data/v101ResearchReport.json";

type Result = { strategy_id: string; fold: string; stress: number; net_return?: number; excess_return?: number; max_drawdown?: number; sharpe?: number | null; turnover?: number; fees?: number; samples?: number; status?: string; reason?: string; trade_count?: number; average_exposure?: number };
const pct = (v?: number) => v === undefined ? "—" : `${(v * 100).toFixed(2)}%`;
const num = (v?: number | null) => v == null ? "—" : v.toLocaleString("zh-TW", { maximumFractionDigits: 2 });
export default function ChallengerV101() {
  const [stress, setStress] = useState(1);
  const rows: Result[] = report.results;
  return <section>
    <div className="page-title"><div><div className="eyebrow">V10.1 · PAPER RESEARCH ONLY</div><h1>模擬策略挑戰組</h1><p>獨立帳戶與固定假說。歷史價格診斷不等於未來模擬實績。</p></div></div>
    <div className="panel"><h2>資格：未通過</h2><p>真實交易停用 · 新策略 forward 觀察 {report.forward_sessions} / 60 日 · 未啟動交易</p>
      <p>歷史資料截至 {report.data_date}；研究完成時間 {report.generated_at}。最後成功 forward session：無。</p>
      <p>來源：TWSE 官方每日全市場日表；原始 V10 artifact Run {report.baseline_run_id}。公司行動／股利／下市結算尚未完整驗證，歷史結果僅供診斷。</p>
      <p>所有假說均列出，不以最終測試區間挑選勝出策略。這個頁面沒有下單或啟用功能。</p>
    </div>
    <div className="panel"><h2>歷史分段比較</h2><p>零成交區段只代表持有現金；回撤較低不能視為策略有效。三個挑戰組在原始 18 日區間均為零成交。</p><label>成本情境 <select value={stress} onChange={e => setStress(Number(e.target.value))}><option value={1}>基準費用＋10 bp 滑價</option><option value={2}>雙倍佣金與滑價</option></select></label>
      <div className="table-wrap"><table><thead><tr><th>策略／區段</th><th>淨報酬</th><th>超額</th><th>最大回撤</th><th>Sharpe</th><th>換手</th><th>成本 NT$</th><th>樣本</th></tr></thead><tbody>
        {rows.filter(r => r.stress === stress).map(r => <tr key={`${r.strategy_id}-${r.fold}`}><td>{r.strategy_id}<br/>{r.fold}{r.trade_count === 0 && <p>零成交 · 全現金</p>}{r.status === "BLOCKED" && <p>資料阻擋：{r.reason}</p>}</td><td>{pct(r.net_return)}</td><td>{pct(r.excess_return)}</td><td>{pct(r.max_drawdown)}</td><td>{num(r.sharpe)}</td><td>{num(r.turnover)}</td><td>{num(r.fees)}</td><td>{r.samples ?? "—"}</td></tr>)}
      </tbody></table></div><p>Sharpe 使用 252 日年化與零無風險利率，短期值不穩定。換手＝買賣總成交金額／平均權益。</p>
    </div>
  </section>;
}
