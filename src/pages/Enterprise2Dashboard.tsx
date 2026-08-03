import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { moneyV14, percentV14 } from "../lib/v14Operations";
import { loadEnterprise2 } from "../lib/enterprise2";
import type {
  EnterpriseDecision,
  EnterpriseHealth,
  EnterprisePortfolio,
  EnterpriseRun,
} from "../types/enterprise2";

export default function Enterprise2Dashboard() {
  const [health, setHealth] = useState<EnterpriseHealth | null>(null);
  const [decisions, setDecisions] = useState<EnterpriseDecision[]>([]);
  const [latestRun, setLatestRun] = useState<EnterpriseRun | null>(null);
  const [portfolio, setPortfolio] = useState<EnterprisePortfolio | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise2()
      .then((data) => {
        setHealth(data.health);
        setDecisions(data.decisions);
        setLatestRun(data.latestRun);
        setPortfolio(data.portfolio);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const accountDecision = useMemo(
    () =>
      decisions.find(
        (row) =>
          row.decision_scope === "PORTFOLIO" &&
          row.entity_type === "ACCOUNT",
      ) ?? null,
    [decisions],
  );

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 2.0</div>
          <h1>統一量化投資作業平台</h1>
          <p>
            固定核心資料模型、模組化引擎、單一每日工作流程、
            統一決策紀錄與完整稽核鏈。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="enterprise2-command panel">
        <div>
          <div className="panel-title">Latest Portfolio Directive</div>
          <div className="enterprise2-action">
            {accountDecision?.action ?? "尚未執行"}
          </div>
          <p className="report-summary">
            {accountDecision?.rationale ??
              "執行 Enterprise 2.0 Daily Master Cycle 後顯示。"}
          </p>
        </div>
        <div className="enterprise2-health">
          <span>System Health</span>
          <strong>{health?.overall_score?.toFixed(0) ?? "0"}</strong>
          <small>/100 · {health?.status ?? "NO DATA"}</small>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="最新執行"
          value={latestRun?.status ?? "尚未執行"}
          note={`${latestRun?.success_count ?? 0}/${latestRun?.module_count ?? 0} 模組成功`}
        />
        <MetricCard
          label="帳戶淨值"
          value={moneyV14(portfolio?.equity)}
          note={`${portfolio?.positions_count ?? 0} 個持倉`}
        />
        <MetricCard
          label="現金"
          value={moneyV14(portfolio?.cash)}
          note={`Gross ${portfolio?.gross_exposure_pct?.toFixed(1) ?? "—"}%`}
        />
        <MetricCard
          label="總報酬"
          value={percentV14(portfolio?.total_return)}
          note={`Sharpe ${portfolio?.sharpe?.toFixed(2) ?? "—"}`}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">平台健康度</div>
          {[
            ["Data", health?.data_score],
            ["Signals", health?.signal_score],
            ["Execution", health?.execution_score],
            ["Portfolio", health?.portfolio_score],
            ["Risk", health?.risk_score],
            ["Automation", health?.automation_score],
          ].map(([label, value]) => (
            <div className="regime" key={label}>
              <span>{label}</span>
              <strong>{Number(value ?? 0).toFixed(0)}</strong>
            </div>
          ))}
        </div>

        <div className="panel">
          <div className="panel-title">Portfolio Risk</div>
          <div className="regime">
            <span>Unrealized P&amp;L</span>
            <strong>{moneyV14(portfolio?.unrealized_pnl)}</strong>
          </div>
          <div className="regime">
            <span>Max Drawdown</span>
            <strong>{portfolio?.max_drawdown?.toFixed(2) ?? "—"}%</strong>
          </div>
          <div className="regime">
            <span>VaR 95%</span>
            <strong>{moneyV14(portfolio?.var_95)}</strong>
          </div>
          <div className="regime">
            <span>Net Exposure</span>
            <strong>{portfolio?.net_exposure_pct?.toFixed(1) ?? "—"}%</strong>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">統一決策紀錄</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th>
                <th>範圍</th>
                <th>標的</th>
                <th>模組</th>
                <th>版本</th>
                <th>動作</th>
                <th>分數</th>
                <th>信心</th>
                <th>目標權重</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((row) => (
                <tr key={row.id}>
                  <td>{row.decision_date}</td>
                  <td>{row.decision_scope}</td>
                  <td>{row.entity_key}</td>
                  <td>{row.module_key}</td>
                  <td>{row.engine_version}</td>
                  <td><strong>{row.action}</strong></td>
                  <td>{row.score?.toFixed(1) ?? "—"}</td>
                  <td>{row.confidence?.toFixed(1) ?? "—"}</td>
                  <td>{row.target_weight?.toFixed(1) ?? "—"}%</td>
                </tr>
              ))}
              {decisions.length === 0 && (
                <tr><td colSpan={9}>尚無 Enterprise 2.0 決策資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Enterprise 2.0 遷移原則</div>
        <div className="execution-step"><b>1</b><span>保留 V13–V22 正常運作的舊引擎</span></div>
        <div className="execution-step"><b>2</b><span>透過 Bridge 將結果寫入固定核心資料表</span></div>
        <div className="execution-step"><b>3</b><span>新功能只新增模組，不新增整套版本資料表</span></div>
        <div className="execution-step"><b>4</b><span>逐步淘汰 Legacy 表，不一次破壞既有系統</span></div>
      </div>
    </section>
  );
}
