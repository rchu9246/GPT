import { useEffect, useState } from "react";
import Dashboard from "../pages/Dashboard";
import Screener from "../pages/Screener";
import DataPipeline from "../pages/DataPipeline";
import Backtest from "../pages/Backtest";
import StrategyLeaderboard from "../pages/StrategyLeaderboard";
import DailyReportPage from "../pages/DailyReportPage";
import PortfolioPage from "../pages/PortfolioPage";
import WalkForward from "../pages/WalkForward";
import PaperTrading from "../pages/PaperTrading";
import StockDetail from "../pages/StockDetail";

type Page =
  | "dashboard"
  | "screener"
  | "report"
  | "portfolio"
  | "pipeline"
  | "backtest"
  | "leaderboard"
  | "walkforward"
  | "paper";

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [selectedStock, setSelectedStock] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => {
      const hash = location.hash.replace("#/", "");
      if (hash.startsWith("stock/")) {
        setSelectedStock(hash.split("/")[1] || null);
        setPage("dashboard");
      } else if (
        [
          "dashboard",
          "screener",
          "report",
          "portfolio",
          "pipeline",
          "backtest",
          "leaderboard",
          "walkforward",
          "paper",
        ].includes(hash)
      ) {
        setSelectedStock(null);
        setPage(hash as Page);
      }
    };

    onHash();
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);

  const nav = (target: Page) => {
    location.hash = `/${target}`;
    setSelectedStock(null);
  };

  if (selectedStock) {
    return <StockDetail symbol={selectedStock} onBack={() => nav("dashboard")} />;
  }

  const items: Array<[Page, string]> = [
    ["dashboard", "總覽"],
    ["screener", "選股"],
    ["report", "每日報告"],
    ["portfolio", "投資組合"],
    ["backtest", "回測"],
    ["leaderboard", "策略排行"],
    ["pipeline", "資料管線"],
    ["walkforward", "Walk-forward"],
    ["paper", "紙上交易"],
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">GPT QUANT V5 PROFESSIONAL</div>
          <div className="subtitle">
            Data → Signals → Risk → Portfolio → Backtest → Decision Intelligence
          </div>
        </div>
        <nav>
          {items.map(([id, label]) => (
            <button
              key={id}
              className={page === id ? "nav active" : "nav"}
              onClick={() => nav(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="content">
        {page === "dashboard" && <Dashboard />}
        {page === "screener" && <Screener />}
        {page === "report" && <DailyReportPage />}
        {page === "portfolio" && <PortfolioPage />}
        {page === "pipeline" && <DataPipeline />}
        {page === "backtest" && <Backtest />}
        {page === "leaderboard" && <StrategyLeaderboard />}
        {page === "walkforward" && <WalkForward />}
        {page === "paper" && <PaperTrading />}
      </main>

      <footer>
        GPT Quant V5 Professional · 模型與歷史績效僅供研究，不構成投資建議
      </footer>
    </div>
  );
}
