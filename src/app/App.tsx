import { useState } from "react";
import CommandCenterV9 from "../pages/CommandCenterV9";
import DailyBriefV9 from "../pages/DailyBriefV9";
import PortfolioV9 from "../pages/PortfolioV9";
import RiskCenterV9 from "../pages/RiskCenterV9";
import ScreenerV9 from "../pages/ScreenerV9";
import StockIntelligenceV9 from "../pages/StockIntelligenceV9";
import StrategyLabV9 from "../pages/StrategyLabV9";
import SystemOpsV9 from "../pages/SystemOpsV9";
import WatchlistV91 from "../pages/WatchlistV91";
import CompareV91 from "../pages/CompareV91";
import AlertsV91 from "../pages/AlertsV91";

type Page = "command" | "screener" | "watchlist" | "compare" | "alerts" | "brief" | "portfolio" | "risk" | "strategy" | "system";
const nav: Array<[Page,string]> = [["command","指揮中心"],["screener","選股"],["watchlist","自選"],["compare","比較"],["alerts","警示"],["brief","每日簡報"],["portfolio","投資組合"],["risk","風險中心"],["strategy","策略實驗室"],["system","系統管線"]];
export default function App(){ const [page,setPage]=useState<Page>("command"); const [symbol,setSymbol]=useState<string|null>(null); const go=(next:Page)=>{setPage(next);setSymbol(null);}; let content;
 if(symbol) content=<StockIntelligenceV9 symbol={symbol} onBack={()=>setSymbol(null)}/>;
 else if(page==="command") content=<CommandCenterV9 onOpenStock={setSymbol}/>;
 else if(page==="screener") content=<ScreenerV9 onOpenStock={setSymbol}/>;
 else if(page==="watchlist") content=<WatchlistV91 onOpenStock={setSymbol}/>;
 else if(page==="compare") content=<CompareV91 onOpenStock={setSymbol}/>;
 else if(page==="alerts") content=<AlertsV91 onOpenStock={setSymbol}/>;
 else if(page==="brief") content=<DailyBriefV9/>; else if(page==="portfolio") content=<PortfolioV9/>; else if(page==="risk") content=<RiskCenterV9/>; else if(page==="strategy") content=<StrategyLabV9/>; else content=<SystemOpsV9/>;
 return <div className="app-shell"><header className="topbar"><div><div className="brand">GPT QUANT V9.1 ENTERPRISE PLUS</div><div className="subtitle">Market Intelligence → Watchlist → Alerts → Portfolio OS → Strategy Research</div></div><nav>{nav.map(([key,label])=><button key={key} className={`nav ${!symbol&&page===key?"active":""}`} onClick={()=>go(key)}>{label}</button>)}</nav></header><main className="content">{content}</main><footer>GPT Quant V9.1 Enterprise Plus · 模型與歷史績效僅供研究，不構成投資建議</footer></div>; }
