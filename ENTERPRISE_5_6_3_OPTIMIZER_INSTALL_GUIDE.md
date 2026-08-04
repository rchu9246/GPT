# Enterprise 5.6.3 Evolution Score Optimizer v3.0

## 目標

解決 Enterprise 5.6.2 的兩個問題：

1. Evolution Score 有排序，但整體仍集中在較低區間。
2. Confidence Score 幾乎相同，無法區分候選品質。

## v3.0 評分架構

Evolution Score 使用：

- Absolute Evidence Score：72%
- Relative Distribution Score：28%

Absolute Evidence 包含：

- Return
- Risk
- Stability
- Robustness
- Rank
- 原始 Evolution Score

Relative Score 只用來校準候選之間的相對差異，
不會單獨把低品質候選推升為合格。

Confidence Score 使用每個候選自己的：

- Robustness
- Data Completeness
- Stability
- Risk
- Relative Evidence
- 原始 Confidence
- Uncertainty Penalty

因此 Confidence 不再預期全部相同。

## 晉升條件

- Rank = 1
- Evolution Score >= 70
- Confidence Score >= 60
- Max Drawdown <= 20（若資料存在）
- Simulation 有資料時，Pass Rate >= 60%
- Stress Test 有資料時，Pass Rate >= 60%
- Data Completeness >= 40

資料不足時只會產生 Warning 或 Uncertainty Penalty，
不會自動視為通過，也不會強制灌高分。

## 部署

1. 解壓 ZIP。
2. 覆蓋到 GPT 專案根目錄。
3. Commit：
   `Enterprise 5.6.3 Evolution Score Optimizer v3.0`
4. Push origin。
5. 執行 GitHub Actions：
   `Enterprise 5.6.3 Evolution Score Optimizer`

第一次：

- ranking_id 留空
- limit = 20

## 執行後順序

1. Enterprise 5.6.3 Optimizer
2. Enterprise 5.7 Baseline Promotion
3. Enterprise 5.7.2 Promotion Eligibility Engine
4. Enterprise 5.7.1 Human Approval
