export default function SimpleV8({ title, subtitle, items }: { title: string; subtitle: string; items: string[] }) {
  return <section><div className="page-title"><div><div className="eyebrow">GPT QUANT V8</div><h1>{title}</h1><p>{subtitle}</p></div></div><div className="professional-signal-grid">{items.map((item, index) => <article className="professional-signal-card" key={item}><strong>0{index + 1}</strong><h3>{item}</h3><p>模組已整合至 V8 架構，可接續 Supabase 與自動化工作流。</p></article>)}</div></section>;
}
