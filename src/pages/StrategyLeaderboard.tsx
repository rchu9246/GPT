import { useEffect, useState } from "react";
import { supabase } from "../lib/supabase";
import type { StrategyLeaderboardRow } from "../types/quant";

export default function StrategyLeaderboard() {
  const [rows, setRows] = useState<StrategyLeaderboardRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!supabase) {
      setError("Supabase 尚未設定");
      return;
    }

    supabase
      .from("strategy_leaderboard")
      .select("*")
      .order("avg_sharpe_ratio", { ascending: false })
      .then(({ data, error: queryError }) => {
        if (queryError) {
          setError(queryError.message);
          return;
        }
        setRows((data ?? []) as StrategyLeaderboardRow[]);
      });
  }, []);

  return (
    <section>
      <div className="page-title">
        <h1>策略排行榜</h1>
        <p>比較不同策略版本的歷史回測結果，避免只憑單次訊號判斷策略品質。</p>
      </div>

      {error && <div className="panel">錯誤：{error}</div>}

      <div className="panel">
        <div className="panel-title">🏆 Strategy Leaderboard</div>
        {rows.length === 0 ? (
          <p>尚無完成的回測。請先執行 Run Quant Backtest。</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>排名</th>
                  <th>策略</th>
                  <th>回測次數</th>
                  <th>平均報酬</th>
                  <th>平均勝率</th>
                  <th>Profit Factor</th>
                  <th>Sharpe</th>
                  <th>平均回撤</th>
                  <th>最佳報酬</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={row.strategy_version}>
                    <td>{index + 1}</td>
                    <td><b>{row.strategy_version}</b></td>
                    <td>{row.run_count}</td>
                    <td>{percent(row.avg_total_return)}</td>
                    <td>{percent(row.avg_win_rate)}</td>
                    <td>{number(row.avg_profit_factor)}</td>
                    <td>{number(row.avg_sharpe_ratio)}</td>
                    <td>{percent(-Math.abs(Number(row.avg_max_drawdown)))}</td>
                    <td>{percent(row.best_total_return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function percent(value: number | null | undefined) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue)
    ? `${numberValue >= 0 ? "+" : ""}${(numberValue * 100).toFixed(2)}%`
    : "—";
}

function number(value: number | null | undefined) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue.toFixed(2) : "—";
}
