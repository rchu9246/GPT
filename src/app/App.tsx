import { useState } from "react";
import DashboardV8 from "../pages/DashboardV8";
import ScreenerV8 from "../pages/ScreenerV8";
import DailyReportV8 from "../pages/DailyReportV8";
import PortfolioV8 from "../pages/PortfolioV8";
import BacktestV8 from "../pages/BacktestV8";
import StockDetailV8 from "../pages/StockDetailV8";
import SimpleV8 from "../pages/SimpleV8";

type Page = "dashboard" | "screener" | "report" | "portfolio" | "backtest" | "ranking" | "pipeline" | "walkforward" | "paper";

const nav: Array<[Page, string]> = [
  ["dashboard", "總覽"], ["screener", "選股"], ["report", "每日報告"],
  ["portfolio", "投資組合"], ["backtest", "回測"], ["ranking", "策略排行"],
  ["pipeline", "資料管線"], ["walkforward", "Walk-forward"], ["paper", "紙上交易"],
];

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [symbol, setSymbol] = useState<string | null>(null);

  const go = (next: Page) => { setPage(next); setSymbol(null); };

  let content;
  if (symbol) content = <StockDetailV8 symbol={symbol} onBack={() => setSymbol(null)} />;
  else if (page === "dashboard") content = <DashboardV8 onOpenStock={setSymbol} />;
  else if (page === "screener") content = <ScreenerV8 onOpenStock={setSymbol} />;
  else if (page === "report") content = <DailyReportV8 />;
  else if (page === "portfolio") content = <PortfolioV8 />;
  else if (page === "backtest") content = <BacktestV8 />;
  else if (page === "ranking") content = <SimpleV8 title="策略排行" subtitle="比較多策略績效與穩定度。" items={["總報酬排行", "Sharpe 排行", "最大回撤排行"]} />;
  else if (page === "pipeline") content = <SimpleV8 title="資料管線" subtitle="追蹤 FinMind、Supabase 與訊號產製狀態。" items={["行情下載", "特徵計算", "訊號生成", "報告發布"]} />;
  else if (page === "walkforward") content = <SimpleV8 title="Walk-forward" subtitle="檢驗樣本外績效與參數穩定性。" items={["訓練視窗", "測試視窗", "參數漂移", "樣本外績效"]} />;
  else content = <SimpleV8 title="紙上交易" subtitle="用模擬部位驗證策略執行效果。" items={["模擬下單", "持倉管理", "損益追蹤", "風險限制"]} />;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div><div className="brand">GPT QUANT V8 PROFESSIONAL</div><div className="subtitle">AI Ratings → Technicals → Portfolio → Backtest → Decision Intelligence</div></div>
        <nav>{nav.map(([key, label]) => <button key={key} className={`nav ${!symbol && page === key ? "active" : ""}`} onClick={() => go(key)}>{label}</button>)}</nav>
      </header>
      <main className="content">{content}</main>
      <footer>GPT Quant V8 Professional · 模型與歷史績效僅供研究，不構成投資建議</footer>
    </div>
  );
}
