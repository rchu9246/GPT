import { useEffect, useMemo, useState } from "react";
import MetricCard from "../app/MetricCard";
import { loadEnterprise30Stable } from "../lib/enterprise30stable";
import type {
  DataQuality30,
  StableRun30,
} from "../types/enterprise30stable";

export default function Enterprise30Stable() {
  const [run, setRun] = useState<StableRun30 | null>(null);
  const [quality, setQuality] = useState<DataQuality30[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEnterprise30Stable()
      .then((data) => {
        setRun(data.run);
        setQuality(data.quality);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "讀取失敗"),
      );
  }, []);

  const successfulStages = useMemo(
    () => run?.stage_results.filter((row) => row.status === "SUCCESS").length ?? 0,
    [run],
  );
  const failedStages = useMemo(
    () => run?.stage_results.filter((row) => row.status === "FAILED").length ?? 0,
    [run],
  );
  const passedChecks = quality.filter((row) => row.check_status === "PASS").length;
  const failedChecks = quality.filter((row) => row.check_status === "FAIL").length;

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">GPT QUANT ENTERPRISE 3.0 STABLE</div>
          <h1>Production-Grade PAPER Investment Platform</h1>
          <p>
            單一正式每日流程、Fail-Closed Schema Gate、Stage Isolation、
            Data Quality、完整 Release Run 與可追溯營運狀態。
          </p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="stable30-hero panel">
        <div>
          <div className="panel-title">Stable Release Status</div>
          <div className="stable30-status">
            {run?.run_status ?? "尚未執行"}
          </div>
          <p className="report-summary">
            {run?.error_message ??
              `Current stage: ${run?.current_stage ?? "—"} · ${
                run?.release_version ?? "3.0.0"
              }`}
          </p>
        </div>
        <div className="stable30-badge">
          <span>Release</span>
          <strong>3.0.0</strong>
          <small>PAPER ONLY</small>
        </div>
      </div>

      <div className="cards">
        <MetricCard
          label="成功階段"
          value={String(successfulStages)}
          note={`${failedStages} failed`}
        />
        <MetricCard
          label="資料品質"
          value={`${passedChecks} PASS`}
          note={`${failedChecks} FAIL`}
        />
        <MetricCard
          label="Blockers"
          value={String(run?.blockers?.length ?? 0)}
          note={run?.blockers?.join(", ") || "None"}
        />
        <MetricCard
          label="最新執行日"
          value={run?.run_date ?? "—"}
          note={run?.completed_at ?? run?.started_at ?? "—"}
        />
      </div>

      <div className="grid2">
        <div className="panel">
          <div className="panel-title">Stable Pipeline Stages</div>
          <div className="run-list">
            {(run?.stage_results ?? []).map((row) => (
              <div className="run-item" key={row.stage}>
                <span>{row.stage}</span>
                <b>{row.status}</b>
                <small>
                  {row.critical ? "CRITICAL" : "NONCRITICAL"}
                  {row.error ? ` · ${row.error}` : ""}
                </small>
              </div>
            ))}
            {(run?.stage_results ?? []).length === 0 && (
              <div className="run-item">
                <span>Stable Daily Cycle</span>
                <b>NO DATA</b>
                <small>執行 Enterprise 3.0 Stable Daily Cycle。</small>
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">Release Guarantees</div>
          <div className="execution-step"><b>1</b><span>必要 Schema 缺少時停止執行</span></div>
          <div className="execution-step"><b>2</b><span>關鍵 Stage 失敗時 Fail Closed</span></div>
          <div className="execution-step"><b>3</b><span>所有 Stage 結果寫入 Release Run</span></div>
          <div className="execution-step"><b>4</b><span>實盤交易保持鎖定</span></div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Data Quality Checks</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>日期</th><th>檢查</th><th>狀態</th>
                <th>嚴重度</th><th>觀察值</th><th>預期值</th><th>說明</th>
              </tr>
            </thead>
            <tbody>
              {quality.map((row) => (
                <tr key={row.id}>
                  <td>{row.check_date}</td>
                  <td><strong>{row.check_key}</strong></td>
                  <td>{row.check_status}</td>
                  <td>{row.severity}</td>
                  <td>{row.observed_value ?? "—"}</td>
                  <td>{row.expected_value ?? "—"}</td>
                  <td>{row.message}</td>
                </tr>
              ))}
              {quality.length === 0 && (
                <tr><td colSpan={7}>尚無 Data Quality 檢查資料。</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
