# SIT Browser-Based 測試案例編寫進度

目前先完成 Browser-based 流程中的兩種 OTP 分支。

## 總覽

| 項目 | 狀態 |
| --- | --- |
| Browser sheet 測試案例 | 50 |
| `direct_otp` 案例編寫 | 已完成 50 / 50 |
| `selection_sms_otp` 案例編寫 | 已完成 50 / 50 |
| `selection_sms_oob` 選擇頁 OOB / 綜合分支 | 待完成 |
| `direct_oob` 案例編寫 | 待完成 |
| `default_oob_can_switch_otp` 案例編寫 | 待完成 |

## 已完成

- `direct_otp`: 50 個 Browser SIT case 都已建立 action plan。
- `selection_sms_otp`: 50 個 Browser SIT case 都已建立 action plan；每次 AReq 後先送出驗證方式選擇，固定選 SMS，再依案例送出 OTP / resend / cancel / prompt action。
- 目前 live runner 已支援 `case01` 到 `case12`、`case14` 到 `case21`、`case24` 到 `case26`、`case28` 到 `case30`、`case32` 到 `case46`；`case13` 與其他尚未補完的 manual/slow 類案例會先標記為 skipped，避免尚未完成的 live 驗證分支卡住整批執行。
- 每個 case 的 AReq 會記錄在 run result 的 `details.caseAreq`；其中 `payloadTemplate` 不依 issuer mode 改變，實際送出後會再記錄 `actualRequestBody`。
- OTP 輸入支援兩種模式：
  - ACS 產生 / ACS 驗證：使用本機模擬 OTP provider，依 `acsTransID` 查 OTP。
  - 客戶產生 / 客戶驗證：使用預設成功 OTP 與失敗 OTP。

## 待完成

- `selection_sms_oob`: 補完整 50 個案例的選擇頁 OOB 或 SMS/OOB 綜合分支 action plan 與執行策略。
- `direct_oob`: 補完整 50 個案例的 OOB action plan 與結果判斷。
- `default_oob_can_switch_otp`: 補完整 50 個案例的 OOB 預設與切換 OTP action plan。
- 將 timeout、resend、cancel、UI prompt 等 live 執行結果判斷從 action plan 延伸成更精準的自動驗證。
## Progress Source of Truth

Per-case implementation progress is maintained in `data/browser_case_progress.json`. This document provides explanatory history only; update the JSON file when an issuer-mode implementation status changes.

## Current Development Progress 2026-07-13

- Browser SIT 左側控制區已分成「執行案例」與「設定」兩個側邊分頁；手機版改為水平分頁。
- 案例編寫進度不再顯示於頁面，改由 `data/browser_case_progress.json` 逐案例記錄。
- 全選 checkbox 已放大為 20 x 20 px，個別案例 checkbox 維持原尺寸。
- 預設有效卡號為 `4771048901645588`，無效卡號只變更最後一碼為 `4771048901645589`。
- AReq 測試端點與 ACS OTP lookup 已整合；支援成功 OTP、失敗 OTP 與 resend 流程。
- 案例明細已顯示測試說明、步驟、Excel 預期結果、實際結果及紅色差異。
- 執行完成後顯示 `ACS Trans ID`，供後續交易追蹤。
- 本地服務固定使用 `http://127.0.0.1:8000/`，更新時停止舊程序後在相同 port 重啟。
- 完整自動化測試目前為 91 項通過；桌面 1440 x 1000 與手機 390 x 844 的 Edge 畫面驗證通過。

## Live Run 2026-07-12

- Full live result file: `live_run_result_final.json`
- Full live summary: total 50, pass 8, fail 33, skipped 9, error 0.
- Targeted retry result file: `live_run_403_retry_final.json`
- Targeted retry note: `case24` passed when rerun with 3 second pacing; remaining transient `case40` still returned ACS Erro 403.
- Runner fixes completed: AReq retry with exponential backoff, configurable case delay, per-case browserLanguage mapping, clearer ACS Erro failure reasons, prompt matching ignores dynamic merchant/help text.
- Remaining data/ACS blockers:
  - `case08`, `case10`, `case12`: default invalid card `4000000000000002` is outside the M endpoint card range; need an ACS-configured invalid PAN in the same scheme/range.
  - `case03`, `case04`, `case05`, `case06`, `case32`: ACS accepts or finalizes some invalid OTP inputs instead of returning the expected incorrect-code prompt/status.
  - Thai/Khmer cases: AReq now sends `th-TH`/`km-KH`, but ACS still returns English challenge text for several cases.
  - `case43`-`case46`: resend limit not reached within current automated resend loop.
  - `case14`: cancel flow reaches ARes C but no final CRes is captured; needs challenge HTML/form inspection for the cancel control.
