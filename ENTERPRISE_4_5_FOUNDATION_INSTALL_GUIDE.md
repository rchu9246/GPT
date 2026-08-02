# GPT Quant Enterprise 4.5 Foundation Pack

## 功能

- Decision Memory v45
- Learning Feedback v45
- Strategy Rating v45
- Learning Cycle Status
- Decision Intelligence Dashboard
- Enterprise 4.5 Validation
- Enterprise 4.5 Learning Cycle

## 安裝順序

1. 解壓並覆蓋目前 GPT 專案。
2. Commit：
   `Upgrade to GPT Quant Enterprise 4.5 Foundation`
3. Push 到 main。
4. Supabase 執行：
   `supabase/ENTERPRISE_4_5_FOUNDATION_SETUP.sql`
5. 成功訊息：
   `GPT Quant Enterprise 4.5 Foundation setup complete`
6. 執行：
   `Enterprise 4.5 Validation`
7. 成功後執行：
   `Enterprise 4.5 Learning Cycle`
8. 重新部署 GitHub Pages。
9. 網站按 Ctrl + Shift + R。

## Learning Cycle

Enterprise 4.4 Operational Pipeline
→ Capture Decision Memory
→ Evaluate Learning Outcomes
→ Update Strategy Ratings

## 安全限制

- PAPER ONLY
- Live learning disabled
- Live trading disabled
- 第一版以 portfolio-level equity 評估決策結果
- Strategy rating 使用 portfolio-level evidence 作為 Foundation proxy
- 不自動修改策略程式碼
- 不自動部署或啟用實盤
