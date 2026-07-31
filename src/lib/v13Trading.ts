import type { SignalRow } from "../types/v9";
import type {
  PaperPosition,
  RiskPolicy,
  TradeOrder,
  TradingMode,
  TradingState,
} from "../types/v13";

const STORAGE_KEY = "gpt-quant-v13-trading-state";

export const DEFAULT_POLICY: RiskPolicy = {
  startingCash: 1_000_000,
  reserveCashPct: 30,
  maxPositions: 5,
  maxPositionPct: 15,
  maxDailyOrders: 5,
  minScore: 40,
  maxRiskScore: 60,
  requireApproval: true,
};

export function defaultTradingState(): TradingState {
  return {
    mode: "PAPER",
    killSwitch: false,
    policy: DEFAULT_POLICY,
    account: {
      cash: DEFAULT_POLICY.startingCash,
      initialEquity: DEFAULT_POLICY.startingCash,
      realizedPnl: 0,
    },
    orders: [],
    positions: [],
  };
}

export function loadTradingState(): TradingState {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as Partial<TradingState> | null;
    if (!parsed) return defaultTradingState();
    const fallback = defaultTradingState();
    return {
      mode: parsed.mode ?? fallback.mode,
      killSwitch: parsed.killSwitch ?? fallback.killSwitch,
      policy: { ...fallback.policy, ...(parsed.policy ?? {}) },
      account: { ...fallback.account, ...(parsed.account ?? {}) },
      orders: Array.isArray(parsed.orders) ? parsed.orders : [],
      positions: Array.isArray(parsed.positions) ? parsed.positions : [],
    };
  } catch {
    return defaultTradingState();
  }
}

export function saveTradingState(state: TradingState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function createId(symbol: string): string {
  return `${Date.now()}-${symbol}-${Math.random().toString(36).slice(2, 8)}`;
}

export function estimateReferencePrice(signal: SignalRow): number {
  const synthetic = Math.max(10, signal.score * 2.2 + signal.confidence * 0.8);
  return Number(synthetic.toFixed(2));
}

export function proposeOrders(
  signals: SignalRow[],
  state: TradingState,
): TradeOrder[] {
  if (state.killSwitch || state.mode === "LIVE_LOCKED") return [];
  const policy = state.policy;
  const existing = new Set(state.positions.map((position) => position.symbol));
  const availableSlots = Math.max(0, policy.maxPositions - state.positions.length);
  const maxOrders = Math.min(policy.maxDailyOrders, availableSlots);
  const investableCash = Math.max(
    0,
    state.account.cash * (1 - policy.reserveCashPct / 100),
  );
  const maxNotional = state.account.initialEquity * (policy.maxPositionPct / 100);

  return signals
    .filter(
      (signal) =>
        !existing.has(signal.symbol) &&
        signal.score >= policy.minScore &&
        signal.risk_score <= policy.maxRiskScore &&
        (signal.rating === "STRONG_BUY" || signal.rating === "BUY" || signal.rating === "WATCH"),
    )
    .slice(0, maxOrders)
    .map((signal, index) => {
      const price = estimateReferencePrice(signal);
      const budget = Math.min(maxNotional, investableCash / Math.max(1, maxOrders - index));
      const quantity = Math.max(1, Math.floor(budget / price));
      const notional = Number((quantity * price).toFixed(2));
      return {
        id: createId(signal.symbol),
        createdAt: new Date().toISOString(),
        symbol: signal.symbol,
        name: signal.name,
        side: "BUY",
        quantity,
        referencePrice: price,
        notional,
        score: signal.score,
        riskScore: signal.risk_score,
        confidence: signal.confidence,
        reason: `Score ${signal.score.toFixed(1)}、Risk ${signal.risk_score.toFixed(1)}、Confidence ${signal.confidence.toFixed(1)}`,
        status: policy.requireApproval ? "PROPOSED" : "APPROVED",
        mode: state.mode,
      } satisfies TradeOrder;
    });
}

export function addProposals(state: TradingState, proposals: TradeOrder[]): TradingState {
  const existingKeys = new Set(
    state.orders
      .filter((order) => order.status === "PROPOSED" || order.status === "APPROVED")
      .map((order) => `${order.symbol}-${order.side}`),
  );
  const unique = proposals.filter((order) => !existingKeys.has(`${order.symbol}-${order.side}`));
  return { ...state, orders: [...unique, ...state.orders] };
}

export function updateOrderStatus(
  state: TradingState,
  orderId: string,
  status: TradeOrder["status"],
): TradingState {
  return {
    ...state,
    orders: state.orders.map((order) =>
      order.id === orderId ? { ...order, status } : order,
    ),
  };
}

function upsertPosition(
  positions: PaperPosition[],
  order: TradeOrder,
): PaperPosition[] {
  const found = positions.find((position) => position.symbol === order.symbol);
  const now = new Date().toISOString();
  if (!found) {
    return [
      ...positions,
      {
        symbol: order.symbol,
        name: order.name,
        quantity: order.quantity,
        averagePrice: order.referencePrice,
        lastPrice: order.referencePrice,
        marketValue: order.notional,
        unrealizedPnl: 0,
        unrealizedPnlPct: 0,
        updatedAt: now,
      },
    ];
  }
  const totalQuantity = found.quantity + order.quantity;
  const totalCost = found.averagePrice * found.quantity + order.referencePrice * order.quantity;
  const averagePrice = totalCost / totalQuantity;
  return positions.map((position) =>
    position.symbol === order.symbol
      ? {
          ...position,
          quantity: totalQuantity,
          averagePrice,
          lastPrice: order.referencePrice,
          marketValue: totalQuantity * order.referencePrice,
          unrealizedPnl: totalQuantity * (order.referencePrice - averagePrice),
          unrealizedPnlPct: averagePrice === 0 ? 0 : order.referencePrice / averagePrice - 1,
          updatedAt: now,
        }
      : position,
  );
}

export function fillPaperOrder(state: TradingState, orderId: string): TradingState {
  const order = state.orders.find((item) => item.id === orderId);
  if (!order || state.killSwitch || state.mode === "LIVE_LOCKED") return state;
  if (order.status !== "APPROVED" && order.status !== "PROPOSED") return state;
  if (order.side === "BUY" && state.account.cash < order.notional) return state;

  const account = {
    ...state.account,
    cash:
      order.side === "BUY"
        ? state.account.cash - order.notional
        : state.account.cash + order.notional,
  };

  return {
    ...state,
    account,
    positions:
      order.side === "BUY"
        ? upsertPosition(state.positions, order)
        : state.positions,
    orders: state.orders.map((item) =>
      item.id === orderId ? { ...item, status: "FILLED" } : item,
    ),
  };
}

export function accountEquity(state: TradingState): number {
  return state.account.cash + state.positions.reduce((sum, position) => sum + position.marketValue, 0);
}

export function resetPaperAccount(mode: TradingMode = "PAPER"): TradingState {
  return { ...defaultTradingState(), mode };
}
