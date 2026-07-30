export type Bar = { date:string; open:number; high:number; low:number; close:number };
export type Position = { entryDate:string; entryPrice:number; shares:number };

export type BacktestParams = {
  takeProfit:number; stopLoss:number; maxHoldingDays:number;
  commissionRate:number; taxRate:number; slippageRate:number;
};

export function simulatePosition(
  bars: Bar[],
  entryIndex: number,
  shares: number,
  p: BacktestParams
) {
  const entryBar = bars[entryIndex];
  const entryPrice = entryBar.open * (1 + p.slippageRate);
  const tp = entryPrice * (1 + p.takeProfit);
  const sl = entryPrice * (1 - p.stopLoss);

  for (let i=entryIndex; i<Math.min(bars.length, entryIndex+p.maxHoldingDays); i++) {
    const b = bars[i];
    if (b.low <= sl) return closeTrade(entryPrice, sl, shares, b.date, "STOP_LOSS", p);
    if (b.high >= tp) return closeTrade(entryPrice, tp, shares, b.date, "TAKE_PROFIT", p);
  }

  const last = bars[Math.min(bars.length-1, entryIndex+p.maxHoldingDays-1)];
  return closeTrade(entryPrice, last.close*(1-p.slippageRate), shares, last.date, "TIME_EXIT", p);
}

function closeTrade(entry:number, exit:number, shares:number, date:string, reason:string, p:BacktestParams) {
  const gross = (exit-entry)*shares;
  const buyCost = entry*shares*p.commissionRate;
  const sellCost = exit*shares*(p.commissionRate+p.taxRate);
  return {
    exitDate: date, exitPrice: exit, reason,
    grossPnl: gross, netPnl: gross-buyCost-sellCost,
    netReturn: (exit-entry)/entry - p.commissionRate*2 - p.taxRate - p.slippageRate*2
  };
}

export function summarizeReturns(returns:number[], initialCapital:number) {
  if (!returns.length) return {
    totalReturn:0, winRate:0, profitFactor:0, maxDrawdown:0,
    finalCapital:initialCapital
  };
  let equity=initialCapital, peak=equity, maxDD=0, grossWin=0, grossLoss=0, wins=0;
  for (const r of returns) {
    const pnl=equity*r;
    equity+=pnl;
    peak=Math.max(peak,equity);
    maxDD=Math.max(maxDD,(peak-equity)/peak);
    if (pnl>0) { wins++; grossWin+=pnl; } else grossLoss+=Math.abs(pnl);
  }
  return {
    totalReturn: equity/initialCapital-1,
    winRate: wins/returns.length,
    profitFactor: grossLoss ? grossWin/grossLoss : Infinity,
    maxDrawdown:maxDD,
    finalCapital:equity
  };
}
