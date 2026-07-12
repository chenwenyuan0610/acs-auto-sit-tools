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
- OTP 輸入支援兩種模式：
  - ACS 產生 / ACS 驗證：使用本機模擬 OTP provider，依 `acsTransID` 查 OTP。
  - 客戶產生 / 客戶驗證：使用預設成功 OTP 與失敗 OTP。

## 待完成

- `selection_sms_oob`: 補完整 50 個案例的選擇頁 OOB 或 SMS/OOB 綜合分支 action plan 與執行策略。
- `direct_oob`: 補完整 50 個案例的 OOB action plan 與結果判斷。
- `default_oob_can_switch_otp`: 補完整 50 個案例的 OOB 預設與切換 OTP action plan。
- 將 timeout、resend、cancel、UI prompt 等 live 執行結果判斷從 action plan 延伸成更精準的自動驗證。
