import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadDirectorV22 } from "../lib/v22Director";
import type {
  DirectorReasoningV22,
  MarketStateV22,
  TradingDirectiveV22,
} from "../types/v22";

export default function TradingDirectorV22() {
  const [directive, setDirective] = useState<TradingDirectiveV22 | null>(null);
  const [market, setMarket] = useState<MarketStateV22 | null>(null);
  const [reasoning, setReasoning] = useState<DirectorReasoningV22[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadDirectorV22()
      .then((data) => {
        setDirective(data.directive);
        setMarket(data.market);
        setReasoning(data.reasoning);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V22 AUTONOMOUS TRADING DIRECTOR</div>
          <h1>最高交易決策中樞</h1>
          <p>
            整合市場狀態、投資委員會、風控、投組回撤與機構健康度，
            形成唯一的每日最高層交易指令。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="director-hero panel">
        <div>
          <div className="panel-title">Today's Trading Directive</div>
          <div className="director-command">
            {directive?.directive ?? "尚未執行"}
          </div>
          <p className="report-summary">
            {directive?.portfolio_action ??
              "執行 V22 Autonomous Trading Director 後顯示。"}
          </p>
        </div>
        <div className="director-confidence">
          <span>Confidence</span>
          <strong>{directive?.confidence?.toFixed(1) ?? "0"}</strong>
          <small>/100</small>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="市場狀態"
          value={directive?.market_state ?? market?.market_state ?? "—"}
          note={`市場信心 ${market?.confidence?.toFixed(1) ?? "—"}`}
        />
        <MetricCard
          label="風險閘門"
          value={directive?.risk_gate ?? "—"}
          note={directive?.council_alignment ?? "—"}
        />
        <MetricCard
          label="目標現金"
          value={`${directive?.target_cash_pct?.toFixed(1) ?? "—"}%`}
          note="Target Cash"
        />
        <MetricCard
          label="資本調整"
          value={
            directive?.directive === "BUY"
              ? `+${directive.deploy_capital_pct.toFixed(1)}%`
              : directive?.directive === "REDUCE" ||
                  directive?.directive === "EXIT" ||
                  directive?.directive === "CASH"
                ? `-${directive.reduce_exposure_pct.toFixed(1)}%`
                : "0%"
          }
          note="建議，不自動成交"
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Market State</div>
          <div className="regime">
            <span>Opportunity</span>
            <strong>{market?.opportunity_score?.toFixed(1) ?? "—"}</strong>
          </div>
          <div className="regime">
            <span>Risk</span>
            <strong>{market?.risk_score?.toFixed(1) ?? "—"}</strong>
          </div>
          <div className="regime">
            <span>Breadth</span>
            <strong>{market?.breadth_score?.toFixed(1) ?? "—"}</strong>
          </div>
          <div className="regime">
            <span>Liquidity</span>
            <strong>{market?.liquidity_score?.toFixed(1) ?? "—"}</strong>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Director Rationale</div>
          <h2>{directive?.rationale ?? "尚無 Director 理由"}</h2>
          <p className="report-summary">
            V22 僅輸出最高層指令與建議資金幅度，不會自動核准、
            模擬成交或送出真實券商訂單。
          </p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Decision Components</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>決策來源</th>
                <th>狀態</th>
                <th>分數</th>
                <th>權重</th>
                <th>貢獻</th>
                <th>說明</th>
              </tr>
            </thead>
            <tbody>
              {reasoning.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.component}</strong></td>
                  <td>{row.component_status}</td>
                  <td>{row.score.toFixed(1)}</td>
                  <td>{row.weight.toFixed(1)}%</td>
                  <td>{row.contribution.toFixed(1)}</td>
                  <td>{row.explanation}</td>
                </tr>
              ))}
              {reasoning.length === 0 && (
                <tr><td colSpan={6}>尚無 V22 決策組成資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
