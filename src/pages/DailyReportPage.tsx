import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { DailyReport, RiskSnapshot } from "../types/quant";

export default function DailyReportPage() {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [risk, setRisk] = useState<RiskSnapshot | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      if (!supabase) {
        setError("Supabase 尚未設定");
        return;
      }

      const [reportResult, riskResult] = await Promise.all([
        supabase
          .from("daily_reports")
          .select("*")
          .order("report_date", { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from("risk_snapshots")
          .select("*")
          .order("snapshot_date", { ascending: false })
          .limit(1)
          .maybeSingle(),
      ]);

      if (reportResult.error) {
        setError(reportResult.error.message);
        return;
      }

      setReport(reportResult.data as DailyReport | null);
      setRisk(riskResult.data as RiskSnapshot | null);
    }

    load();
  }, []);

  return (
    <section>
      <div className="page-title">
        <h1>每日專業研究報告</h1>
        <p>由市場資料、V3.1 多因子訊號與風險規則自動產生。</p>
      </div>

      {error && <div className="panel">錯誤：{error}</div>}

      {!error && !report && (
        <div className="panel">
          尚無報告。到 GitHub Actions 執行「Generate Professional Daily Report」。
        </div>
      )}

      {report && (
        <>
          <div className="cards">
            <Metric title="報告日期" value={report.report_date} sub={report.generated_by} />
            <Metric title="市場狀態" value={report.market_state} sub={`Score ${report.market_score.toFixed(1)}`} />
            <Metric title="策略健康度" value={`${report.strategy_health.toFixed(0)}/100`} sub="訊號、風險與多頭比例" />
            <Metric title="風險等級" value={risk?.risk_level ?? "—"} sub={`平均波動 ${risk ? risk.average_volatility.toFixed(2) : "—"}`} />
          </div>

          <div className="grid2">
            <div className="panel">
              <div className="panel-title">🧠 市場摘要</div>
              <p className="report-summary">{report.summary}</p>
              <div className="panel-title">🎯 行動方案</div>
              <p className="report-action">{report.action_plan}</p>
            </div>

            <div className="panel">
              <div className="panel-title">⚠️ 風險警示</div>
              {report.risk_flags.length === 0 ? (
                <p>目前沒有低於安全門檻的風險標的。</p>
              ) : (
                report.risk_flags.map((flag) => (
                  <div className="regime" key={`${flag.symbol}-${flag.message}`}>
                    <span><b>{flag.symbol}</b> {flag.name}</span>
                    <small>{flag.message} · Score {flag.score.toFixed(1)} · Risk {flag.risk_score.toFixed(1)}</small>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-title">⭐ 今日重點訊號</div>
            <div className="professional-signal-grid">
              {report.top_signals.map((signal) => (
                <article className="professional-signal-card" key={signal.symbol}>
                  <div className="signal-card-head">
                    <div>
                      <b>{signal.symbol}</b>
                      <span>{signal.name}</span>
                    </div>
                    <strong>{signal.score.toFixed(1)}</strong>
                  </div>
                  <p>{signal.signal} · 信心 {signal.confidence.toFixed(1)}%</p>
                  <div className="signal-levels">
                    <span>進場 {money(signal.entry_low)}～{money(signal.entry_high)}</span>
                    <span>停損 {money(signal.stop_loss)}</span>
                    <span>目標 {money(signal.target_1)}</span>
                  </div>
                  <ul>
                    {(signal.reasons ?? []).slice(0, 5).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function Metric({ title, value, sub }: { title: string; value: string; sub: string }) {
  return (
    <div className="metric">
      <span>{title}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function money(value: number | null | undefined) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue.toFixed(2) : "—";
}
