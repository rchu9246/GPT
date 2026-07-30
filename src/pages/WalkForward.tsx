const folds=[
  ["Fold 1","2021-01 ~ 2022-12","2023 Q1","+4.8%","🟢"],
  ["Fold 2","2021-04 ~ 2023-03","2023 Q2","+3.2%","🟢"],
  ["Fold 3","2021-07 ~ 2023-06","2023 Q3","-1.1%","🟡"],
  ["Fold 4","2021-10 ~ 2023-09","2023 Q4","+6.3%","🟢"],
];
export default function WalkForward(){
  return <section>
    <div className="page-title"><h1>Walk-forward Lab</h1><p>訓練期最佳化參數，下一段時間只做 Out-of-Sample 測試。</p></div>
    <div className="cards">
      <div className="metric"><span>Stability Score</span><strong>84</strong><small>🟢 PASS</small></div>
      <div className="metric"><span>OOS Fold</span><strong>4</strong><small>可擴充</small></div>
      <div className="metric"><span>OOS 勝率</span><strong>61%</strong><small>示意值</small></div>
      <div className="metric"><span>OOS Max DD</span><strong>-12.6%</strong><small>示意值</small></div>
    </div>
    <div className="panel"><div className="table-wrap"><table><thead><tr><th>Fold</th><th>Training</th><th>Testing</th><th>Return</th><th>Status</th></tr></thead><tbody>{folds.map(f=><tr key={f[0]}>{f.map((x,i)=><td key={i}>{x}</td>)}</tr>)}</tbody></table></div></div>
  </section>
}
