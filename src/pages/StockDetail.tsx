export default function StockDetail({
  symbol,
  onBack,
}: {
  symbol: string;
  onBack: () => void;
}) {
  return (
    <section>
      <button className="nav active" onClick={onBack}>← 返回</button>
      <div className="page-title">
        <h1>{symbol} 個股中心</h1>
        <p>技術指標、訊號、風險與歷史績效。</p>
      </div>
      <div className="panel">個股詳細資料將從 Supabase 載入。</div>
    </section>
  );
}
