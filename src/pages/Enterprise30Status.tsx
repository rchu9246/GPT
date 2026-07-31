import { useEffect, useState } from "react";
import { loadEnterprise30Stable } from "../lib/enterprise30stable";
import type {
  DataQuality30,
  StableRun30,
} from "../types/enterprise30stable";

export default function Enterprise30Status() {
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

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">ENTERPRISE 3.0.3 STATUS</div>
          <h1>Deployment & Runtime Status</h1>
          <p>集中查看版本、最近 Stable Run、品質檢查與目前阻擋項目。</p>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="cards">
        <div className="card">
          <span>Version</span>
          <strong>3.0.3</strong>
          <small>Stable</small>
        </div>
        <div className="card">
          <span>Run Status</span>
          <strong>{run?.run_status ?? "NO DATA"}</strong>
          <small>{run?.run_date ?? "—"}</small>
        </div>
        <div className="card">
          <span>Quality PASS</span>
          <strong>{quality.filter((row) => row.check_status === "PASS").length}</strong>
          <small>{quality.length} checks</small>
        </div>
        <div className="card">
          <span>Blockers</span>
          <strong>{run?.blockers?.length ?? 0}</strong>
          <small>{run?.blockers?.join(", ") || "None"}</small>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Latest Stage Results</div>
        <div className="run-list">
          {(run?.stage_results ?? []).map((stage) => (
            <div className="run-item" key={stage.stage}>
              <span>{stage.stage}</span>
              <b>{stage.status}</b>
              <small>{stage.critical ? "CRITICAL" : "NONCRITICAL"}</small>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
