# Enterprise 5.6.2 Evolution Score Optimizer v2.0

## 主要修正

Enterprise 5.6.1 遇到資料欄位缺失時，會把缺失資料視為極差，
導致所有候選的 Evolution Score 幾乎相同且接近零。

5.6.2 改為：

- 缺失資料使用保守中性值
- 保留原始 Evolution 與 Confidence 作為部分評分依據
- 加入 Rank Score
- 加入 Data Completeness
- 只有完整證據不足時才施加 Completeness Penalty
- 不會為了通過 5.7 而任意灌高分

## 分數組成

Evolution Score：

- Return Score 22%
- Risk Score 20%
- Stability Score 17%
- Robustness Score 16%
- Rank Score 10%
- 原始 Evolution Score 15%
- 扣除資料完整度懲罰

Confidence Score：

- Robustness 30%
- Stability 20%
- Risk 15%
- Data Completeness 15%
- 原始 Confidence 20%

## 晉升條件

- Rank = 1
- Evolution Score >= 70
- Confidence Score >= 60
- Max Drawdown <= 20（若資料存在）
- Simulation 有資料時必須 PASS
- Stress Test 有資料時必須 PASS
- Data Completeness >= 40

缺少 Simulation 或 Stress Test 時只會產生 Warning，
不會自動視為失敗；但仍需滿足分數與資料完整度門檻。

## 部署

1. 解壓 ZIP。
2. 覆蓋到 GPT 專案根目錄。
3. Commit：
   `Enterprise 5.6.2 Evolution Score Optimizer v2.0`
4. Push origin。
5. GitHub Actions 執行：
   `Enterprise 5.6.2 Evolution Score Optimizer`

第一次：

- ranking_id 留空
- limit = 20

## 後續流程

1. Enterprise 5.6.2 Optimizer
2. Enterprise 5.7 Baseline Promotion
3. Enterprise 5.7.2 Promotion Eligibility Engine
4. Enterprise 5.7.1 Human Approval
