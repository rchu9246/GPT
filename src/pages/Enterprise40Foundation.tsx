import { useEffect, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise40 } from "../lib/enterprise40";
import type {
  Portfolio40,
  Regime40,
  Release40,
  Run40,
  Strategy40,
} from "../types/enterprise40";

export default function Enterprise40Foundation() {
  const [portfolios, setPortfolios] = useState<Portfolio40[]>([]);
  const [strategies, setStrategies] = useState<Strategy40[]>([]);
  const [regime, setRegime] = useState<Regime40 | null>(null);
  const [run, setRun] = useState<Run40 | null>(null);
  const [release, setRelease] = useState<Release40 | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise40()
      .then((data) => {
        setPortfolios(data.portfolios);
        setStrategies(data.strategies);
        setRegime(data.regime);
        setRun(data.run);
        setRelease(data.release);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const paperApproved = strategies.filter((row) => row.paper_approved).length;
  const liveApproved = strategies.filter((row) => row.live_approved).length;

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 4.0 FOUNDATION</div>
          <h1>Multi-Portfolio & Multi-Strategy Foundation</h1>
          <p>
            Portfolio Registry、Strategy Registry、Run Tracking、Audit、
            Market Regime 與 3.x 相容層。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="enterprise40-hero panel">
        <div>
          <div className="panel-title">Foundation Readiness</div>
          <div className="enterprise40-score">
            {release?.readiness_score?.toFixed(0) ?? "0"}%
          </div>
          <p className="report-summary">
            {run?.status ?? "尚未執行 Foundation Run"} ·{" "}
            {run?.current_stage ?? "NO STAGE"}
          </p>
        </div>
        <div className="enterprise40-mode">
          <span>Execution Mode</span>
          <strong>PAPER ONLY</strong>
          <small>
            Live approved strategies: {liveApproved}
          </small>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="Portfolios"
          value={String(portfolios.length)}
          note="Registered portfolios"
        />
        <MetricCard
          label="Strategies"
          value={String(strategies.length)}
          note={`${paperApproved} PAPER approved`}
        />
        <MetricCard
          label="Market Regime"
          value={regime?.regime ?? "UNKNOWN"}
          note={`Confidence ${regime?.confidence?.toFixed(1) ?? "0"}`}
        />
        <MetricCard
          label="Latest Run"
          value={run?.status ?? "NO DATA"}
          note={run?.run_date ?? "—"}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Portfolio Registry</div>
          <div className="run-list">
            {portfolios.map((row) => (
              <div className="run-item" key={row.id}>
                <span>{row.portfolio_name}</span>
                <b>{row.lifecycle_status}</b>
                <small>
                  {row.portfolio_key} · Cash reserve{" "}
                  {row.reserve_cash_pct.toFixed(0)}% · Max{" "}
                  {row.max_positions} positions
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Strategy Registry</div>
          <div className="run-list">
            {strategies.map((row) => (
              <div className="run-item" key={row.id}>
                <span>{row.strategy_name}</span>
                <b>{row.lifecycle_status}</b>
                <small>
                  {row.strategy_family} · PAPER{" "}
                  {row.paper_approved ? "YES" : "NO"} · LIVE{" "}
                  {row.live_approved ? "YES" : "NO"}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Market Regime Foundation</div>
        <h2>{regime?.regime ?? "UNKNOWN"}</h2>
        <p className="report-summary">
          {regime?.rationale ?? "尚未產生 Regime 資料。"}
        </p>
      </div>

      <div className="panel">
        <div className="panel-title">Release Guarantees</div>
        <div className="run-list">
          {[
            ["Foundation", release?.foundation_ready],
            ["Registry", release?.registry_ready],
            ["Run Tracking", release?.run_tracking_ready],
            ["Audit", release?.audit_ready],
            ["Regime", release?.regime_ready],
            ["Compatibility", release?.compatibility_ready],
          ].map(([label, ready]) => (
            <div className="run-item" key={String(label)}>
              <span>{String(label)}</span>
              <b>{ready ? "READY" : "PENDING"}</b>
              <small>Enterprise 4.0 Foundation capability</small>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
