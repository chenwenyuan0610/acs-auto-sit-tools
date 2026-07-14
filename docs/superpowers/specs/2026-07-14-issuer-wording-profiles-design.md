# Issuer Wording Profiles Design

## Goal

Allow the SIT runner to import issuer-specific challenge UI wording from Excel and use it to generate and validate the localized UI cases currently represented by case23 through case50.

## Confirmed Behavior

- The default supported locales are `zh_TW`, `en_US`, and `zh_CN`.
- An issuer profile may override the supported locale list.
- Missing wording remains visible in the case list but cannot be selected or executed.
- Imported wording is normalized to JSON and remains available after the service restarts.
- Importing wording changes generated case expectations and availability; it does not rewrite the source case catalog.

## Architecture

The browser reads the selected `.xlsx` file and sends it as base64 JSON to a backend import endpoint. The backend validates the workbook, normalizes enabled issuer settings and wording rows, and atomically writes a runtime JSON profile file under `data/`.

The existing localized cases become seven scenario templates: initial PA page, initial NPA page, incorrect OTP, successful resend, resend gap limit, resend count limit, and expired OTP. The case catalog expands each scenario for the selected issuer's supported locales. Each generated case carries a base case ID, locale, wording code, message category, expected field values, and an availability reason.

Runtime execution uses generated case metadata instead of parsing language from display names. Prompt comparison continues to accept dynamic placeholder values while reporting missing field-level expectations to the existing red difference view.

## Workbook Contract

Required sheets:

- `發卡行設定`: enabled issuer profiles and issuer modes.
- `話術匯入`: enabled wording rows indexed by issuer, issuer mode, channel, message category, wording code, locale, and field key.

Required wording keys:

`issuerId + issuerMode + deviceChannel + messageCategory + wordingCode + locale + fieldKey`

Blank issuer values represent the shared `default` profile. Issuer-specific rows override shared rows. The initial implementation supports the existing `BROWSER` channel and the workbook's normalized field keys.

## Locale Handling

Locale identifiers are stored in underscore form (`zh_TW`) and converted to browser form (`zh-TW`) when building AReq and challenge headers. No cross-language fallback is allowed. If an expected locale or wording code is missing, the generated case is disabled with a concrete reason.

## Case Scenarios

| Template | Wording code | Category | Behavior |
| --- | --- | --- | --- |
| case23 | `SEND_SMS_OTP` | PA | Open the initial OTP page |
| case27 | `SEND_SMS_OTP` | NPA | Open the initial OTP page |
| case31 | `INCORRECT_SMS_OTP` | PA | Submit an incorrect OTP |
| case35 | `RESEND_SMS_OTP` | PA | Resend after the allowed interval |
| case39 | `RESEND_SMS_GAP_LIMIT` | PA | Resend before the allowed interval |
| case43 | `RESEND_SMS_LIMIT_EXCEED` | PA | Resend until the limit is reached |
| case47 | `SMS_PASSCODE_EXPIRED` | PA | Submit an expired OTP |

Generated IDs use `<template>_<locale>`, for example `case23_zh_TW` and `case23_en_US`.

## UI

The settings panel adds an issuer selector, an Excel file picker, an import button, and a compact import summary. Reloading issuer profiles or changing the selected issuer reloads the case catalog. Disabled cases show their reason and are ignored by Select All and Run All.

## Error Handling

- Invalid base64, invalid `.xlsx`, missing sheets, or missing required columns returns HTTP 400 without replacing the last valid profile.
- Duplicate wording keys are rejected so expectations are deterministic.
- Import summaries include issuer count, locale count, wording row count, and validation errors.
- If no runtime JSON exists, the bundled workbook is not implicitly imported; existing static cases remain available until a profile is explicitly imported.

## Testing

- Unit tests cover workbook parsing, defaults, overrides, duplicate detection, persistence, and generated cases.
- API tests cover import, profile listing, issuer selection, and invalid workbook responses.
- Frontend contract tests cover controls, payloads, disabled checkboxes, and catalog reload behavior.
- Existing live runner tests continue to cover legacy static case IDs while new tests cover generated metadata for locale and resend behavior.
