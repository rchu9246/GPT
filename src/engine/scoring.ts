export type FeatureVector = {
  close: number; ma20: number; ma60: number; ma120: number;
  ma20Slope: number; ma60Slope: number; rsi14: number;
  macd: number; macdSignal: number; volumeRatio20: number;
  return5d: number; return20d: number; marketReturn20d: number;
  foreignNet5d: number; trustNet5d: number;
  distanceHigh20d: number; distanceHigh60d: number;
  marketScore: number; volatility20d: number;
};

const clamp = (n:number,min=0,max=100) => Math.max(min, Math.min(max,n));
const scale = (x:number, lo:number, hi:number) => clamp((x-lo)/(hi-lo)*100);

export function scoreTrend(f: FeatureVector) {
  return clamp(
    (f.ma20 > f.ma60 ? 35 : 0) +
    (f.ma60 > f.ma120 ? 25 : 0) +
    (f.close > f.ma20 ? 20 : 0) +
    (f.ma20Slope > 0 ? 20 : 0)
  );
}

export function scoreMomentum(f: FeatureVector) {
  const rsi = f.rsi14 >= 50 && f.rsi14 <= 70 ? 100 :
    f.rsi14 < 50 ? scale(f.rsi14, 30, 50) : scale(90-f.rsi14, 20, 40);
  const macd = f.macd > f.macdSignal ? 100 : 20;
  const r5 = scale(f.return5d, -0.08, 0.08);
  const r20 = scale(f.return20d, -0.20, 0.30);
  return clamp(rsi*0.35 + macd*0.20 + r5*0.20 + r20*0.25);
}

export function scoreVolume(f: FeatureVector) {
  if (f.volumeRatio20 < 0.5) return 25;
  if (f.volumeRatio20 < 1.0) return 50;
  if (f.volumeRatio20 <= 1.5) return 75;
  if (f.volumeRatio20 <= 2.5) return 100;
  return 65;
}

export function scoreInstitutional(f: FeatureVector) {
  const foreign = scale(f.foreignNet5d, -1e7, 1e7);
  const trust = scale(f.trustNet5d, -5e6, 5e6);
  return clamp(foreign*0.65 + trust*0.35);
}

export function scoreBreakout(f: FeatureVector) {
  const near20 = scale(-Math.abs(f.distanceHigh20d), -0.15, 0);
  const near60 = scale(-Math.abs(f.distanceHigh60d), -0.25, 0);
  return clamp(near20*0.55 + near60*0.45);
}

export function scoreRelativeStrength(f: FeatureVector) {
  return scale(f.return20d - f.marketReturn20d, -0.15, 0.20);
}

export function scoreRisk(f: FeatureVector) {
  if (f.volatility20d <= 0.02) return 95;
  if (f.volatility20d <= 0.035) return 80;
  if (f.volatility20d <= 0.05) return 60;
  if (f.volatility20d <= 0.08) return 40;
  return 20;
}

export function calculateScore(f: FeatureVector) {
  const trend = scoreTrend(f);
  const momentum = scoreMomentum(f);
  const volume = scoreVolume(f);
  const institutional = scoreInstitutional(f);
  const breakout = scoreBreakout(f);
  const relativeStrength = scoreRelativeStrength(f);
  const market = clamp(f.marketScore);
  const risk = scoreRisk(f);

  const total =
    trend*0.20 + momentum*0.15 + volume*0.15 + institutional*0.15 +
    breakout*0.10 + relativeStrength*0.10 + market*0.10 + risk*0.05;

  const signal = total >= 90 ? "S級強多" :
    total >= 80 ? "A級多頭" :
    total >= 70 ? "B級觀察" :
    total >= 60 ? "C級中性" : "D級避開";

  return {
    total: Math.round(total*100)/100,
    trend, momentum, volume, institutional, breakout,
    relativeStrength, market, risk, signal
  };
}
