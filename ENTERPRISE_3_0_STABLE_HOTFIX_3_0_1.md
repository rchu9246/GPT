# GPT Quant Enterprise 3.0 Stable Hotfix 3.0.1

## 修正內容

- 新增根目錄 `requirements.txt`
- 修正 `actions/setup-python@v5` 找不到依賴檔的問題
- Stable Workflow 明確設定 `cache-dependency-path: requirements.txt`
- 統一以 `pip install -r requirements.txt` 安裝 Python 套件
- 新增 `Enterprise 3.0 Stable Validation` Workflow
- Stable Daily Cycle 增加必要檔案檢查
- 保留 PAPER ONLY 與 Fail-Closed 設計

## 部署順序

1. 覆蓋專案、Commit、Push。
2. 確認 `Enterprise 3.0 Stable Validation` 成功。
3. 再執行 `Enterprise 3.0 Stable Daily Cycle`。
4. 已執行過 Stable SQL 時，不需要重跑資料庫 SQL。
