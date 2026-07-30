import { useEffect, useState } from "react";
import Dashboard from "../pages/Dashboard";
import Screener from "../pages/Screener";
import Backtest from "../pages/Backtest";
import StrategyLeaderboard from "../pages/StrategyLeaderboard";
import WalkForward from "../pages/WalkForward";
import PaperTrading from "../pages/PaperTrading";
import StockDetail from "../pages/StockDetail";
import DataPipeline from "../pages/DataPipeline";

type Page =
  | "dashboard"
  | "screener"
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
    ["dashboard", "儀表板"],
    ["screener", "選股"],
    ["pipeline", "資料管線"],
    ["backtest", "回測"],
    ["leaderboard", "策略排行"],
    ["walkforward", "Walk-forward"],
    ["paper", "紙上交易"],
  ];

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">GPT QUANT V4</div>
          <div className="subtitle">
            Signals → Backtest → Leaderboard → Decision Intelligence
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
        {page === "pipeline" && <DataPipeline />}
        {page === "backtest" && <Backtest />}
        {page === "leaderboard" && <StrategyLeaderboard />}
        {page === "walkforward" && <WalkForward />}
        {page === "paper" && <PaperTrading />}
      </main>

      <footer>
        GPT Quant V4 · 歷史回測不代表未來績效，資料與模型僅供研究
      </footer>
    </div>
  );
}
