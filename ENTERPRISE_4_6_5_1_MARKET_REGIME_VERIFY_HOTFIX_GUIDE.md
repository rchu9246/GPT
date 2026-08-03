# Enterprise 4.6.5.1 Market Regime Verification Hotfix

## 問題

Market Regime AI 主程式成功，但 Workflow 最後驗證時出現：

`ModuleNotFoundError: No module named 'enterprise2'`

原因是行內 Python 從專案根目錄執行，未包含 `automation` 模組路徑。

## 修正

在驗證步驟加入：

```yaml
PYTHONPATH: ${{ github.workspace }}/automation
```

## 安裝

1. 解壓並覆蓋目前 GPT 專案。
2. Commit：
   `Enterprise 4.6.5.1 Market Regime Verification Hotfix`
3. Push origin。
4. 重新執行：
   `Enterprise 4.6.5 Market Regime AI`

不需要重新執行 SQL。
