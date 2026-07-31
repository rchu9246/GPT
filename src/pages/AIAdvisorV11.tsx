import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  loadLatestSignals,
  marketIntelligence,
  optimizePortfolio,
  ratingLabel,
  regimeLabel,
} from "../lib/v9Data";
import type { SignalRow } from "../types/v9";

type Message = { role: "user" | "assistant"; text: string };

function answerQuestion(question: string, signals: SignalRow[]): string {
  const intelligence = marketIntelligence(signals);
  const top = signals.slice(0, 5);
  const normalized = question.trim().toLowerCase();

  const matched = signals.find((row) =>
    normalized.includes(row.symbol.toLowerCase()) ||
    (row.name ? normalized.includes(row.name.toLowerCase()) : false),
  );

  if (matched) {
    return `${matched.symbol} ${matched.name ?? ""}：Score ${matched.score.toFixed(
      1,
    )}、評級「${ratingLabel(matched.rating)}」、趨勢 ${matched.trend_score.toFixed(
      1,
    )}、動能 ${matched.momentum_score.toFixed(
      1,
    )}、風險 ${matched.risk_score.toFixed(
      1,
    )}。目前較適合「${
      matched.rating === "STRONG_BUY" || matched.rating === "BUY"
        ? "分批觀察，等待價格確認"
        : matched.rating === "WATCH"
          ? "保持觀察，不追價"
          : "降低曝險並檢查停損"
    }」。`;
  }

  if (normalized.includes("風險") || normalized.includes("市場")) {
    return `目前市場狀態為「${regimeLabel(
      intelligence.regime,
    )}」，系統健康度 ${intelligence.health.toFixed(
      0,
    )}/100，平均風險 ${intelligence.averageRisk.toFixed(
      1,
    )}。偏多標的 ${intelligence.bullishCount} 檔、警示標的 ${
      intelligence.warningCount
    } 檔。`;
  }

  if (
    normalized.includes("推薦") ||
    normalized.includes("哪") ||
    normalized.includes("買")
  ) {
    return top.length
      ? `依目前量化訊號，優先研究：${top
          .map(
            (row, index) =>
              `${index + 1}. ${row.symbol} ${row.name ?? ""}（${ratingLabel(
                row.rating,
              )}，Score ${row.score.toFixed(1)}）`,
          )
          .join("；")}。這是研究排序，不是保證報酬的買進指示。`
      : "目前沒有可用訊號。";
  }

  return `你可以問我「今天市場風險」、「推薦哪幾檔」或直接輸入股票代號。所有回答都由目前 Supabase 量化訊號生成，不會假裝使用尚未接入的即時新聞或外部模型。`;
}

export default function AIAdvisorV11({
  onOpenStock,
}: {
  onOpenStock: (symbol: string) => void;
}) {
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "我是 V11 AI 投資助理。可詢問市場風險、候選股票或特定代號。",
    },
  ]);

  useEffect(() => {
    loadLatestSignals().then(setSignals).catch(() => setSignals([]));
  }, []);

  const allocations = useMemo(() => optimizePortfolio(signals, 5), [signals]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text) return;
    const response = answerQuestion(text, signals);
    setMessages((current) => [
      ...current,
      { role: "user", text },
      { role: "assistant", text: response },
    ]);
    setQuestion("");
  }

  return (
    <section>
      <div className="page-title">
        <div>
          <div className="eyebrow">V11 EXPLAINABLE AI COPILOT</div>
          <h1>AI 投資助理</h1>
          <p>以目前量化訊號回答問題，不在前端暴露模型金鑰。</p>
        </div>
      </div>

      <div className="grid2">
        <div className="panel ai-chat-panel">
          <div className="panel-title">研究對話</div>
          <div className="chat-log">
            {messages.map((message, index) => (
              <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <strong>{message.role === "assistant" ? "V11 AI" : "你"}</strong>
                <p>{message.text}</p>
              </div>
            ))}
          </div>
          <form className="chat-form" onSubmit={submit}>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="例如：今天市場風險？或輸入 2330"
            />
            <button type="submit">分析</button>
          </form>
        </div>

        <div className="panel">
          <div className="panel-title">AI 建議配置</div>
          <div className="allocation-list">
            {allocations.map((row) => (
              <button
                className="allocation-row clickable"
                key={row.symbol}
                onClick={() => onOpenStock(row.symbol)}
              >
                <div>
                  <strong>{row.symbol}</strong>
                  <small>{row.name ?? ""}</small>
                </div>
                <div className="allocation-bar">
                  <i style={{ width: `${Math.min(100, row.weight * 100)}%` }} />
                </div>
                <b>{(row.weight * 100).toFixed(1)}%</b>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
