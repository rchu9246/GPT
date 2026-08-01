import { useState } from "react";
import Enterprise43Committee from "../pages/Enterprise43Committee";
import Enterprise42Adaptive from "../pages/Enterprise42Adaptive";
import Enterprise41RiskCenter from "../pages/Enterprise41RiskCenter";
import Enterprise40Foundation from "../pages/Enterprise40Foundation";
import Enterprise32Dashboard from "../pages/Enterprise32Dashboard";
import Enterprise31Operations from "../pages/Enterprise31Operations";
import Enterprise30Status from "../pages/Enterprise30Status";
import Enterprise30Stable from "../pages/Enterprise30Stable";
import Enterprise30Release from "../pages/Enterprise30Release";
import Enterprise30Dashboard from "../pages/Enterprise30Dashboard";
import Enterprise21Operational from "../pages/Enterprise21Operational";
import Enterprise2Dashboard from "../pages/Enterprise2Dashboard";
import TradingDirectorV22 from "../pages/TradingDirectorV22";
import MultiAgentCouncilV21 from "../pages/MultiAgentCouncilV21";
import InstitutionalDashboardV20 from "../pages/InstitutionalDashboardV20";
import HedgeFundV19 from "../pages/HedgeFundV19";
import AIFundManagerV18 from "../pages/AIFundManagerV18";
import PortfolioOSV17 from "../pages/PortfolioOSV17";
import TradingEngineV16 from "../pages/TradingEngineV16";
import AutoPortfolioV15 from "../pages/AutoPortfolioV15";
import ExecutionConsoleV145 from "../pages/ExecutionConsoleV145";
import TradingOperationsV14 from "../pages/TradingOperationsV14";
import AutoTraderV13 from "../pages/AutoTraderV13";
import TradeLedgerV13 from "../pages/TradeLedgerV13";
import AgentCouncilV12 from "../pages/AgentCouncilV12";
import AIAdvisorV11 from "../pages/AIAdvisorV11";
import MarketHeatmapV12 from "../pages/MarketHeatmapV12";
import AIWatchlistV12 from "../pages/AIWatchlistV12";
import GlobalMarketsV11 from "../pages/GlobalMarketsV11";
import ResearchCenterV11 from "../pages/ResearchCenterV11";
import NewsSentimentV11 from "../pages/NewsSentimentV11";
import ScreenerV9 from "../pages/ScreenerV9";
import StockIntelligenceV9 from "../pages/StockIntelligenceV9";
import PortfolioOSV11 from "../pages/PortfolioOSV11";
import RiskAnalyticsV12 from "../pages/RiskAnalyticsV12";
import MultiStrategyV10 from "../pages/MultiStrategyV10";
import StrategyLabV9 from "../pages/StrategyLabV9";
import SystemOpsV9 from "../pages/SystemOpsV9";

type Page =
  | "enterprise43"
  | "enterprise42"
  | "enterprise41"
  | "enterprise40"
  | "enterprise32"
  | "enterprise31"
  | "status30"
  | "stable30"
  | "release30"
  | "enterprise30"
  | "enterprise21"
  | "enterprise2"
  | "director22"
  | "council21"
  | "institutional"
  | "hedgefund"
  | "fundmanager"
  | "portfolioos"
  | "engine"
  | "autoportfolio"
  | "execution"
  | "operations"
  | "autotrader"
  | "ledger"
  | "agents"
  | "assistant"
  | "heatmap"
  | "watchlist"
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
  ["enterprise43", "Enterprise 4.3"],
  ["enterprise42", "Enterprise 4.2"],
  ["enterprise41", "Enterprise 4.1"],
  ["enterprise40", "Enterprise 4.0"],
  ["enterprise32", "Enterprise 3.2"],
  ["enterprise31", "Enterprise 3.1"],
  ["status30", "3.0 Status"],
  ["stable30", "3.0 Stable"],
  ["release30", "3.0 Command"],
  ["enterprise30", "3.0 Research"],
  ["enterprise21", "Enterprise 2.1"],
  ["enterprise2", "Enterprise 2.0"],
  ["director22", "Legacy Director"],
  ["council21", "V21 委員會"],
  ["institutional", "機構總控"],
  ["hedgefund", "避險基金"],
  ["fundmanager", "AI 基金經理"],
  ["portfolioos", "Portfolio OS"],
  ["engine", "交易引擎"],
  ["autoportfolio", "自動投組"],
  ["execution", "執行控制"],
  ["operations", "交易營運"],
  ["autotrader", "本機模擬"],
  ["ledger", "持倉帳本"],
  ["agents", "Agent 議會"],
  ["assistant", "AI 助理"],
  ["heatmap", "熱力圖"],
  ["watchlist", "AI 自選"],
  ["markets", "全球市場"],
  ["research", "研究中心"],
  ["sentiment", "事件情緒"],
  ["screener", "AI 選股"],
  ["portfolio", "舊版投組"],
  ["risk", "進階風險"],
  ["multistrategy", "多策略"],
  ["strategy", "策略實驗室"],
  ["system", "系統管線"],
];

export default function App() {
  const [page, setPage] = useState<Page>("enterprise43");
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
  } else if (page === "enterprise43") {
    content = <Enterprise43Committee />;
  } else if (page === "enterprise42") {
    content = <Enterprise42Adaptive />;
  } else if (page === "enterprise41") {
    content = <Enterprise41RiskCenter />;
  } else if (page === "enterprise40") {
    content = <Enterprise40Foundation />;
  } else if (page === "enterprise32") {
    content = <Enterprise32Dashboard />;
  } else if (page === "enterprise31") {
    content = <Enterprise31Operations />;
  } else if (page === "status30") {
    content = <Enterprise30Status />;
  } else if (page === "stable30") {
    content = <Enterprise30Stable />;
  } else if (page === "release30") {
    content = <Enterprise30Release />;
  } else if (page === "enterprise30") {
    content = <Enterprise30Dashboard />;
  } else if (page === "enterprise21") {
    content = <Enterprise21Operational />;
  } else if (page === "enterprise2") {
    content = <Enterprise2Dashboard />;
  } else if (page === "director22") {
    content = <TradingDirectorV22 />;
  } else if (page === "council21") {
    content = <MultiAgentCouncilV21 />;
  } else if (page === "institutional") {
    content = <InstitutionalDashboardV20 />;
  } else if (page === "hedgefund") {
    content = <HedgeFundV19 />;
  } else if (page === "fundmanager") {
    content = <AIFundManagerV18 />;
  } else if (page === "portfolioos") {
    content = <PortfolioOSV17 />;
  } else if (page === "engine") {
    content = <TradingEngineV16 />;
  } else if (page === "autoportfolio") {
    content = <AutoPortfolioV15 />;
  } else if (page === "execution") {
    content = <ExecutionConsoleV145 />;
  } else if (page === "operations") {
    content = <TradingOperationsV14 />;
  } else if (page === "autotrader") {
    content = <AutoTraderV13 />;
  } else if (page === "ledger") {
    content = <TradeLedgerV13 />;
  } else if (page === "agents") {
    content = <AgentCouncilV12 onOpenStock={setSymbol} />;
  } else if (page === "assistant") {
    content = <AIAdvisorV11 onOpenStock={setSymbol} />;
  } else if (page === "heatmap") {
    content = <MarketHeatmapV12 onOpenStock={setSymbol} />;
  } else if (page === "watchlist") {
    content = <AIWatchlistV12 onOpenStock={setSymbol} />;
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
    content = <RiskAnalyticsV12 />;
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
          <div className="brand">GPT QUANT ENTERPRISE 4.3 STABLE</div>
          <div className="subtitle">
            Schema Gate → Stable Pipeline → Data Quality → Governance → PAPER Operations
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
        GPT Quant Enterprise 3.0 Stable · Governed AI PAPER investment platform
      </footer>
    </div>
  );
}
