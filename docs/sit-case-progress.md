# SIT Browser-Based Test Case Progress

## Current Scope

Browser-based SIT currently tracks 43 active cases. The following cases were removed from the active catalog per current test planning:

- `case05`, `case06`, `case15`, `case16`, `case17`, `case21`, `case22`

Case IDs are not renumbered in the current committed state. Renumbering the active catalog to a contiguous `case01` to `case43` sequence is a pending follow-up decision because OOB cases may be tracked separately as `oob01`, `oob02`, and so on.

## Implementation Status

| Area | Status |
| --- | --- |
| Active browser cases | 43 |
| `sms_otp` | Implemented; `direct_otp` remains a server-side compatibility alias |
| `email_otp` | Implemented |
| `direct_oob` | Implemented |
| `selection_sms_oob` | Implemented with separate SMS and OOB branches |
| `selection_sms_email` | Implemented with separate SMS and Email branches |
| `selection_sms_email_oob` | Implemented with separate SMS, Email, and OOB branches |
| `selection_email_oob` | Implemented with separate Email and OOB branches |
| `default_oob_can_switch_otp` | Implemented as OOB -> switch CReq -> SMS OTP |

## Live Runner Coverage

The live runner supports the active OTP/SMS browser paths for:

- `case01` to `case04`
- `case07` to `case12`
- `case14`
- `case18` to `case20`
- `case24` to `case26`
- `case28` to `case30`
- `case32` to `case46`

The remaining active manual or slow cases are still skipped in live mode until their flow is automated:

- `case13`
- `case47` to `case50`

## UI Wording Validation

Cases from `case23` onward are UI wording and page-format validation cases. Issuer-specific wording import is now implemented. The default supported locales are `zh_TW`, `en_US`, and `zh_CN`.

The settings page now auto-detects both supported workbook formats:

- The normalized workbook `outputs/challenge-ui-wording-work/acs_challenge_ui_wording_import.xlsx`.
- The original `challenge_ui_info.xlsx` workbook with `SMS`, `Email`, `OOB`, and `Single Select` source sheets.

The normalized workbook contains:

- Issuer settings and issuer mode defaults.
- Normalized wording rows keyed by issuer, issuer mode, device channel, message category, code, language, and field key.
- UI case mapping for `case23` onward.
- Field dictionary and source sheet summary.

The settings panel stores the normalized runtime profile in `data/wording_profiles.json`. That generated file is local runtime data and is excluded from Git. Import failures preserve the last valid profile.

After import, the previous 28 language-specific cases (`case23` to `case50`) are represented by seven scenario templates and expanded for each supported issuer locale:

- Initial PA OTP page.
- Initial NPA OTP page.
- Incorrect OTP.
- Successful OTP resend.
- OTP resend gap limit.
- OTP resend count limit.
- Expired OTP.

The normalized profile continues exposing 21 localized UI cases for backward compatibility. The original workbook generates cases by selected issuer mode, source sheet, message category, wording code, and locale. Issuer-specific rows override shared default wording. A missing code/locale combination remains visible but cannot be selected or executed, and its reason is shown in the case list.

Every non-empty imported Excel wording field is now validated. Matching decodes HTML entities, removes tags, normalizes whitespace, and accepts dynamic numbered placeholders such as `{0}`. Generated locales are sent in AReq `browserLanguage` as `zh-TW`, `en-US`, or `zh-CN`. The main result comparison shows only field names, expected wording, and found/missing status; missing wording remains red. Full challenge HTML for each stage is retained only in the collapsed `技術細節` result.

Available APIs:

- `GET /api/sit/wording-profiles?issuerId=default&issuerMode=sms_otp`
- `POST /api/sit/wording-profiles/import`
- `GET /api/sit/browser-cases?issuerId=default&issuerMode=sms_otp`

Verification on 2026-07-16: the full automated suite passed with 159 tests. Generated UI case implementation status is now derived from reusable action capability instead of legacy `baseCaseId` progress. Normalized generated cases without `flow` metadata are classified as pending and skipped before legacy live-runner fallback, so an unsupported generated case cannot be reported as implemented.

Stage-aware Excel wording validation is shared across generated actions and the legacy result comparison. It validates only the fields assigned to the current challenge stage, supports runtime placeholders, excludes `script`, `style`, `template`, and `noscript` content from visible text, and keeps the legacy `_excel_field_results()` response shape compatible.

The supplied `challenge_ui_info.xlsx` imported as one issuer, three locales, 228 source rows, and 1,752 normalized wording fields. Generated case counts were:

| Issuer mode | Generated UI cases | Disabled |
| --- | ---: | ---: |
| `sms_otp` | 48 | 0 |
| `email_otp` | 48 | 0 |
| `direct_oob` | 12 | 0 |
| `selection_sms_oob` | 66 | 0 |
| `selection_sms_email` | 102 | 0 |
| `selection_sms_email_oob` | 114 | 0 |
| `selection_email_oob` | 66 | 0 |
| `default_oob_can_switch_otp` | 12 | 0 |

Playwright verification passed at 1440px desktop and 390px mobile widths with no horizontal overflow, console errors, or failed network responses. It also verified compact Excel field output, no `rawHtml` in the main comparison, and collapsed technical details. The local server is kept on `http://127.0.0.1:8000/`.

## OOB Planning

The first OOB Browser active set is planned separately from the OTP catalog. The current recommendation is to keep OOB cases in a separate catalog, using IDs such as `oob01` through `oob13`, instead of mixing them into the existing OTP `caseXX` list.

The first OOB active set should include:

- OOB success, cancel, reject, PA/NPA valid and invalid card, 3RI valid and invalid card, interrupt, and English PA/NPA OOB UI cases.
- The CAVV verification case, because it can be automated by looking up transaction results by `acsTransID`.

The first OOB active set should exclude or defer:

- Long timeout cases, such as ACS maximum challenge timeout.
- Cases requiring ACS Admin state changes, such as payment-network or ISO currency minor-unit changes.
- Currency display and wrong-currency-code cases until the UI wording/profile and environment-setting model is mature.

## Simulated Transaction Result Lookup

The local app now provides a simulated transaction-result lookup for OOB development:

```http
POST /api/transaction-result/simulated
Content-Type: application/json

{
  "acsTransID": "acs-trans-1"
}
```

The response includes a deterministic simulated CAVV, `transStatus = "Y"`, `eci = "02"`, and pass/fail check objects. This lets the OOB CAVV case be automated before the real transaction-result API is available.

## Source of Truth

Per-case implementation progress is maintained in `data/browser_case_progress.json`. The active case catalog is maintained in `sit_cases/pipay_cup_browser_cases.json`.
