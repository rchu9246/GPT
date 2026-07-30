import { useState } from "react";
import DashboardV7 from "../pages/DashboardV7";
import ScreenerV7 from "../pages/ScreenerV7";
import DailyReportV7 from "../pages/DailyReportV7";
import PortfolioV7 from "../pages/PortfolioV7";
import BacktestV7 from "../pages/BacktestV7";
import StockDetailV7 from "../pages/StockDetailV7";
import SimpleV7 from "../pages/SimpleV7";

type Page = "dashboard" | "screener" | "report" | "portfolio" | "backtest" | "ranking" | "pipeline" | "walkforward" | "paper";

const nav: Array<[Page, string]> = [
  ["dashboard", "總覽"], ["screener", "選股"], ["report", "每日報告"], ["portfolio", "投資組合"],
  ["backtest", "回測"], ["ranking", "策略排行"], ["pipeline", "資料管線"], ["walkforward", "Walk-forward"], ["paper", "紙上交易"],
];

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [symbol, setSymbol] = useState<string | null>(null);

  const openStock = (value: string) => setSymbol(value);
  const go = (next: Page) => { setSymbol(null); setPage(next); };

  let content;
  if (symbol) content = <StockDetailV7 symbol={symbol} onBack={() => setSymbol(null)} />;
  else if (page === "dashboard") content = <DashboardV7 onOpenStock={openStock} />;
  else if (page === "screener") content = <ScreenerV7 onOpenStock={openStock} />;
  else if (page === "report") content = <DailyReportV7 />;
  else if (page === "portfolio") content = <PortfolioV7 />;
  else if (page === "backtest") content = <BacktestV7 />;
  else if (page === "ranking") content = <SimpleV7 title="策略排行" subtitle="比較不同策略版本的績效與穩定度。" items={["報酬與回撤排行", "Sharpe 與勝率排行", "穩定度與樣本數"]} />;
  else if (page === "pipeline") content = <SimpleV7 title="資料管線" subtitle="追蹤 FinMind、Supabase 與策略計算狀態。" items={["行情下載", "特徵計算", "訊號生成", "報告更新"]} />;
  else if (page === "walkforward") content = <SimpleV7 title="Walk-forward" subtitle="用滾動訓練與測試區間驗證策略穩健度。" items={["訓練視窗", "測試視窗", "參數漂移", "樣本外績效"]} />;
  else content = <SimpleV7 title="紙上交易" subtitle="用模擬部位驗證真實執行效果。" items={["模擬下單", "持倉管理", "損益追蹤", "風險限制"]} />;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div><div className="brand">GPT QUANT V7 PROFESSIONAL</div><div className="subtitle">Signals → Research → Portfolio → Backtest → Decision Intelligence</div></div>
        <nav>{nav.map(([key, label]) => <button key={key} className={`nav ${!symbol && page === key ? "active" : ""}`} onClick={() => go(key)}>{label}</button>)}</nav>
      </header>
      <main className="content">{content}</main>
      <footer>GPT Quant V7 Professional · 模型與歷史績效僅供研究，不構成投資建議</footer>
    </div>
  );
}
