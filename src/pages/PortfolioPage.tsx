import { useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import type {
  Portfolio,
  PortfolioPosition,
  PortfolioSnapshot,
} from "../types/quant";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      if (!supabase) {
        setError("Supabase 尚未設定");
        return;
      }

      const portfolioResult = await supabase
        .from("portfolios")
        .select("*")
        .eq("is_active", true)
        .order("created_at", { ascending: true })
        .limit(1)
        .maybeSingle();

      if (portfolioResult.error) {
        setError(portfolioResult.error.message);
        return;
      }

      const loadedPortfolio = portfolioResult.data as Portfolio | null;
      setPortfolio(loadedPortfolio);

      if (!loadedPortfolio) return;

      const [positionsResult, snapshotsResult] = await Promise.all([
        supabase
          .from("portfolio_positions")
          .select("*, stocks(symbol,name,industry)")
          .eq("portfolio_id", loadedPortfolio.id)
          .order("weight", { ascending: false }),
        supabase
          .from("portfolio_snapshots")
          .select("*")
          .eq("portfolio_id", loadedPortfolio.id)
          .order("snapshot_date", { ascending: false })
          .limit(60),
      ]);

      if (positionsResult.error) {
        setError(positionsResult.error.message);
        return;
      }

      setPositions((positionsResult.data ?? []) as unknown as PortfolioPosition[]);
      setSnapshots((snapshotsResult.data ?? []) as PortfolioSnapshot[]);
    }

    load();
  }, []);

  const marketValue = useMemo(
    () => positions.reduce((sum, position) => sum + Number(position.market_value ?? 0), 0),
    [positions],
  );
  const unrealizedPnl = useMemo(
    () => positions.reduce((sum, position) => sum + Number(position.unrealized_pnl ?? 0), 0),
    [positions],
  );
  const totalEquity = Number(portfolio?.cash_balance ?? 0) + marketValue;
  const latestSnapshot = snapshots[0];

  return (
    <section>
      <div className="page-title">
        <h1>專業投資組合中心</h1>
        <p>檢視現金、持倉、市值、未實現損益、曝險與資產配置。</p>
      </div>

      {error && <div className="panel">錯誤：{error}</div>}

      {!error && !portfolio && (
        <div className="panel">尚未建立投資組合。</div>
      )}

      {portfolio && (
        <>
          <div className="cards">
            <Metric title="總資產" value={money(totalEquity)} sub={portfolio.name} />
            <Metric title="現金" value={money(portfolio.cash_balance)} sub={`${totalEquity ? (portfolio.cash_balance / totalEquity * 100).toFixed(1) : "0.0"}%`} />
            <Metric title="持倉市值" value={money(marketValue)} sub={`${positions.length} 檔`} />
            <Metric title="未實現損益" value={signedMoney(unrealizedPnl)} sub={`累積報酬 ${percent(latestSnapshot?.cumulative_return)}`} />
          </div>

          <div className="grid2">
            <div className="panel">
              <div className="panel-title">💼 持倉明細</div>
              {positions.length === 0 ? (
                <p>目前沒有持倉。後續可由紙上交易或自動策略建立部位。</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>股票</th>
                        <th>數量</th>
                        <th>成本</th>
                        <th>現價</th>
                        <th>市值</th>
                        <th>損益</th>
                        <th>權重</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((position) => (
                        <tr key={position.id}>
                          <td><b>{position.stocks?.symbol ?? position.stock_id}</b> {position.stocks?.name ?? ""}</td>
                          <td>{position.quantity}</td>
                          <td>{money(position.average_cost)}</td>
                          <td>{money(position.current_price)}</td>
                          <td>{money(position.market_value)}</td>
                          <td>{signedMoney(position.unrealized_pnl)}</td>
                          <td>{percent(position.weight)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="panel">
              <div className="panel-title">🛡️ 組合風險</div>
              <div className="regime">
                <span>最大回撤</span>
                <b>{percent(latestSnapshot?.max_drawdown, true)}</b>
              </div>
              <div className="regime">
                <span>20日波動</span>
                <b>{percent(latestSnapshot?.volatility_20d)}</b>
              </div>
              <div className="regime">
                <span>VaR 95%</span>
                <b>{percent(latestSnapshot?.var_95, true)}</b>
              </div>
              <div className="regime">
                <span>資料日期</span>
                <b>{latestSnapshot?.snapshot_date ?? "—"}</b>
              </div>
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
  return Number.isFinite(numberValue)
    ? new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 }).format(numberValue)
    : "—";
}

function signedMoney(value: number | null | undefined) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "—";
  return `${numberValue >= 0 ? "+" : ""}${money(numberValue)}`;
}

function percent(value: number | null | undefined, negative = false) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "—";
  const adjusted = negative ? -Math.abs(numberValue) : numberValue;
  return `${adjusted >= 0 ? "+" : ""}${(adjusted * 100).toFixed(2)}%`;
}
