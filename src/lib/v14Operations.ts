import { supabase } from "./supabase";
import type {
  EngineRunV14,
  EquitySnapshotV14,
  PaperAccountV14,
  PaperFillV14,
  PaperOperationsV14,
  PaperOrderV14,
  PaperPositionV14,
} from "../types/v14";

function numeric(value: unknown): number {
  const result = Number(value);
  return Number.isFinite(result) ? result : 0;
}

function mapNumbers<T extends Record<string, unknown>>(
  row: T,
  fields: string[],
): T {
  const result = { ...row };
  for (const field of fields) {
    if (field in result) {
      (result as Record<string, unknown>)[field] = numeric(result[field]);
    }
  }
  return result;
}

export async function loadPaperOperationsV14(
  accountName = "paper-main",
): Promise<PaperOperationsV14> {
  if (!supabase) {
    return {
      account: null,
      positions: [],
      orders: [],
      fills: [],
      snapshots: [],
      runs: [],
    };
  }

  const [
    accountResult,
    positionsResult,
    ordersResult,
    fillsResult,
    snapshotsResult,
    runsResult,
  ] = await Promise.all([
    supabase
      .from("paper_accounts_v13")
      .select("*")
      .eq("account_name", accountName)
      .maybeSingle(),
    supabase
      .from("paper_positions_v13")
      .select("*")
      .eq("account_name", accountName)
      .order("market_value", { ascending: false }),
    supabase
      .from("trade_orders_v13")
      .select("*")
      .eq("account_name", accountName)
      .order("created_at", { ascending: false })
      .limit(50),
    supabase
      .from("paper_fills_v13")
      .select("*")
      .eq("account_name", accountName)
      .order("filled_at", { ascending: false })
      .limit(50),
    supabase
      .from("paper_equity_snapshots_v13")
      .select("*")
      .eq("account_name", accountName)
      .order("snapshot_date", { ascending: true })
      .limit(180),
    supabase
      .from("paper_engine_runs_v13")
      .select("*")
      .eq("account_name", accountName)
      .order("started_at", { ascending: false })
      .limit(30),
  ]);

  const firstError =
    accountResult.error ??
    positionsResult.error ??
    ordersResult.error ??
    fillsResult.error ??
    snapshotsResult.error ??
    runsResult.error;

  if (firstError) throw firstError;

  const account = accountResult.data
    ? (mapNumbers(accountResult.data as Record<string, unknown>, [
        "starting_cash",
        "cash",
        "equity",
        "realized_pnl",
        "unrealized_pnl",
        "total_fees",
        "total_tax",
      ]) as unknown as PaperAccountV14)
    : null;

  const positions = (positionsResult.data ?? []).map((row) =>
    mapNumbers(row as Record<string, unknown>, [
      "quantity",
      "average_price",
      "last_price",
      "market_value",
      "unrealized_pnl",
      "realized_pnl",
      "holding_days",
    ]),
  ) as unknown as PaperPositionV14[];

  const orders = (ordersResult.data ?? []).map((row) =>
    mapNumbers(row as Record<string, unknown>, [
      "quantity",
      "reference_price",
      "fill_price",
      "notional",
      "score",
      "risk_score",
      "confidence",
    ]),
  ) as unknown as PaperOrderV14[];

  const fills = (fillsResult.data ?? []).map((row) =>
    mapNumbers(row as Record<string, unknown>, [
      "quantity",
      "fill_price",
      "gross_amount",
      "commission",
      "transaction_tax",
      "realized_pnl",
    ]),
  ) as unknown as PaperFillV14[];

  const snapshots = (snapshotsResult.data ?? []).map((row) =>
    mapNumbers(row as Record<string, unknown>, [
      "cash",
      "market_value",
      "equity",
      "realized_pnl",
      "unrealized_pnl",
      "total_return",
      "positions_count",
    ]),
  ) as unknown as EquitySnapshotV14[];

  const runs = (runsResult.data ?? []).map((row) =>
    mapNumbers(row as Record<string, unknown>, [
      "buy_orders",
      "sell_orders",
      "fills",
    ]),
  ) as unknown as EngineRunV14[];

  return { account, positions, orders, fills, snapshots, runs };
}

export function moneyV14(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "TWD",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

export function percentV14(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  const normalized = Math.abs(number) <= 2 ? number * 100 : number;
  return `${normalized.toFixed(2)}%`;
}
