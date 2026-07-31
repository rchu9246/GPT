export default function SystemOpsV9() {
  const modules = [{title:"FinMind 行情",status:"自動更新",note:"GitHub Actions 定時下載台股行情"},{title:"Supabase",status:"即時連線",note:"行情、特徵、訊號與回測資料"},{title:"Signal Engine",status:"V3.1 MULTI",note:"趨勢、動能、量能與風險因子"},{title:"GitHub Pages",status:"自動部署",note:"main 分支建置完成後發布"}];
  return <section><div className="page-title"><div><div className="eyebrow">SYSTEM OPERATIONS</div><h1>資料與系統管線</h1><p>追蹤資料來源、策略引擎與部署架構。</p></div></div><div className="professional-signal-grid">{modules.map((item, index) => <article className="professional-signal-card" key={item.title}><strong>0{index + 1}</strong><h3>{item.title}</h3><span className="status-pill">{item.status}</span><p>{item.note}</p></article>)}</div></section>;
}
