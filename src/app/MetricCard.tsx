export default function MetricCard({ label, value, note }: { label: string; value: string | number; note: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}
