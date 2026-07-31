export default function Sparkline({
  values,
  height = 220,
  label,
}: {
  values: number[];
  height?: number;
  label?: string;
}) {
  const clean = values.filter((value) => Number.isFinite(value));
  if (clean.length < 2) return <div className="empty-chart">資料不足</div>;

  const width = 760;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  const range = max - min || 1;
  const points = clean
    .map((value, index) => {
      const x = (index / (clean.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 20) - 10;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="sparkline-shell">
      {label && <div className="chart-label">{label}</div>}
      <svg className="sparkline" viewBox={`0 0 ${width} ${height}`}>
        <polyline
          points={points}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="chart-range"><span>{min.toFixed(2)}</span><span>{max.toFixed(2)}</span></div>
    </div>
  );
}
