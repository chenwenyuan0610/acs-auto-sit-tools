# SIT Browser-Based Test Case Progress

## Current Scope

Browser-based SIT currently tracks 43 active cases. The following cases were removed from the active catalog per current test planning:

- `case05`, `case06`, `case15`, `case16`, `case17`, `case21`, `case22`

Case IDs are not renumbered in the current committed state. Renumbering the active catalog to a contiguous `case01` to `case43` sequence is a pending follow-up decision because OOB cases may be tracked separately as `oob01`, `oob02`, and so on.

## Implementation Status

| Area | Status |
| --- | --- |
| Active browser cases | 43 |
| `direct_otp` implementation | 43 / 43 completed |
| `selection_sms_otp` implementation | 43 / 43 completed |
| `selection_sms_oob` implementation | Pending |
| `direct_oob` implementation | Pending |
| `default_oob_can_switch_otp` implementation | Pending |

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

Cases from `case23` onward are UI wording and page-format validation cases. Because wording can differ by issuer, the expected validation should be driven by issuer-specific wording profiles instead of a single global expected string.

The generated workbook `outputs/challenge-ui-wording-work/acs_challenge_ui_wording_import.xlsx` is the current staging format for future wording import. It contains:

- Issuer settings and issuer mode defaults.
- Normalized wording rows keyed by issuer, issuer mode, device channel, message category, code, language, and field key.
- UI case mapping for `case23` onward.
- Field dictionary and source sheet summary.

When an issuer profile exists, the runner should compare the returned challenge UI against the issuer's normalized wording rows. When no issuer profile exists, the case should be reported as needing a wording profile rather than failing against another issuer's copy.

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
