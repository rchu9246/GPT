import { useState } from "react";
import CommandCenterV9 from "../pages/CommandCenterV9";
import ScreenerV9 from "../pages/ScreenerV9";
import StockIntelligenceV9 from "../pages/StockIntelligenceV9";
import AIAdvisorV11 from "../pages/AIAdvisorV11";
import GlobalMarketsV11 from "../pages/GlobalMarketsV11";
import NewsSentimentV11 from "../pages/NewsSentimentV11";
import ResearchCenterV11 from "../pages/ResearchCenterV11";
import PortfolioOSV11 from "../pages/PortfolioOSV11";
import MultiStrategyV10 from "../pages/MultiStrategyV10";
import StrategyLabV9 from "../pages/StrategyLabV9";
import RiskCenterV9 from "../pages/RiskCenterV9";
import SystemOpsV9 from "../pages/SystemOpsV9";

type Page =
  | "command"
  | "assistant"
  | "markets"
  | "research"
  | "sentiment"
  | "screener"
  | "portfolio"
  | "risk"
  | "multistrategy"
  | "strategy"
  | "system";

const nav: Array<[Page, string]> = [
  ["command", "AI 指揮中心"],
  ["assistant", "GPT 助理"],
  ["markets", "全球市場"],
  ["research", "研究中心"],
  ["sentiment", "事件情緒"],
  ["screener", "AI 選股"],
  ["portfolio", "Portfolio OS"],
  ["risk", "風險中心"],
  ["multistrategy", "多策略"],
  ["strategy", "策略實驗室"],
  ["system", "系統管線"],
];

export default function App() {
  const [page, setPage] = useState<Page>("command");
  const [symbol, setSymbol] = useState<string | null>(null);

  const go = (next: Page) => {
    setPage(next);
    setSymbol(null);
  };

  let content;
  if (symbol) {
    content = (
      <StockIntelligenceV9
        symbol={symbol}
        onBack={() => setSymbol(null)}
      />
    );
  } else if (page === "command") {
    content = <CommandCenterV9 onOpenStock={setSymbol} />;
  } else if (page === "assistant") {
    content = <AIAdvisorV11 onOpenStock={setSymbol} />;
  } else if (page === "markets") {
    content = <GlobalMarketsV11 />;
  } else if (page === "research") {
    content = <ResearchCenterV11 onOpenStock={setSymbol} />;
  } else if (page === "sentiment") {
    content = <NewsSentimentV11 onOpenStock={setSymbol} />;
  } else if (page === "screener") {
    content = <ScreenerV9 onOpenStock={setSymbol} />;
  } else if (page === "portfolio") {
    content = <PortfolioOSV11 />;
  } else if (page === "risk") {
    content = <RiskCenterV9 />;
  } else if (page === "multistrategy") {
    content = <MultiStrategyV10 />;
  } else if (page === "strategy") {
    content = <StrategyLabV9 />;
  } else {
    content = <SystemOpsV9 />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">GPT QUANT V11 ENTERPRISE AI</div>
          <div className="subtitle">
            Explainable AI → Global Risk → Research → Portfolio OS → Strategy Intelligence
          </div>
        </div>
        <nav>
          {nav.map(([key, label]) => (
            <button
              key={key}
              className={`nav ${!symbol && page === key ? "active" : ""}`}
              onClick={() => go(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      <main className="content">{content}</main>
      <footer>
        GPT Quant V11 Enterprise AI · 模型、代理指標與歷史績效僅供研究，不構成投資建議
      </footer>
    </div>
  );
}
