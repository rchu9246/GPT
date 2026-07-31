# GPT Quant Enterprise 2.0 遷移計畫

## Phase 1：Foundation
- 建立固定核心資料表
- 建立 Module SDK
- 建立 Legacy Bridge
- 建立單一 Daily Master Workflow
- 建立 Enterprise 2.0 Dashboard

## Phase 2：Native Engines
逐一將舊引擎改寫成 Enterprise 2.0 Module：
- Signal Module
- Risk Module
- Council Module
- Director Module
- Order Module
- Portfolio Module
- Reporting Module

## Phase 3：Data Migration
- 轉移歷史 decisions
- 轉移 positions
- 轉移 portfolio snapshots
- 轉移 reports
- 保留 legacy source reference

## Phase 4：Legacy Freeze
- 停止新增 `_vXX` 資料表
- 舊資料表只讀
- 所有新結果只寫入 Enterprise 2.0 Core

## Phase 5：Legacy Retirement
- 驗證至少 30 個交易日
- 確認數據一致
- 封存舊 Workflow
- 保留回復方案
