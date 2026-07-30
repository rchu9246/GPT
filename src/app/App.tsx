import { useEffect, useState } from "react";
import Dashboard from "../pages/Dashboard";
import Screener from "../pages/Screener";
import Backtest from "../pages/Backtest";
import WalkForward from "../pages/WalkForward";
import PaperTrading from "../pages/PaperTrading";
import StockDetail from "../pages/StockDetail";

type Page = "dashboard" | "screener" | "backtest" | "walkforward" | "paper";

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [selectedStock, setSelectedStock] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => {
      const hash = location.hash.replace("#/", "");
      if (hash.startsWith("stock/")) {
        setSelectedStock(hash.split("/")[1] || null);
        setPage("dashboard");
      } else if (["dashboard","screener","backtest","walkforward","paper"].includes(hash)) {
        setSelectedStock(null);
        setPage(hash as Page);
      }
    };
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = (p: Page) => {
    location.hash = `/${p}`;
    setSelectedStock(null);
  };

  if (selectedStock) {
    return <StockDetail symbol={selectedStock} onBack={() => navigate("dashboard")} />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">台股 QUANT V2</div>
          <div className="subtitle">Signal → Outcome → Backtest → Walk-forward</div>
        </div>
        <nav>
          {([
            ["dashboard","儀表板"],
            ["screener","選股"],
            ["backtest","回測"],
            ["walkforward","Walk-forward"],
            ["paper","紙上交易"]
          ] as const).map(([id,label]) =>
            <button key={id} className={page===id ? "nav active" : "nav"} onClick={() => navigate(id)}>{label}</button>
          )}
        </nav>
      </header>
      <main className="content">
        {page === "dashboard" && <Dashboard />}
        {page === "screener" && <Screener />}
        {page === "backtest" && <Backtest />}
        {page === "walkforward" && <WalkForward />}
        {page === "paper" && <PaperTrading />}
      </main>
      <footer>V2.0 MVP · 僅供策略研究與回測，不構成投資建議</footer>
    </div>
  );
}
