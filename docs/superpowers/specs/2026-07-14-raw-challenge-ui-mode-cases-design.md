# Raw Challenge UI Mode Case Generation Design

## Goal

Allow the settings page to import the original `challenge_ui_info.xlsx` workbook and generate localized Challenge UI test cases from the currently selected Issuer Mode.

## Supported Workbook Formats

The existing import endpoint automatically detects both formats:

1. Normalized workbook containing `發卡行設定` and `話術匯入`.
2. Original challenge workbook containing source sheets such as `SMS`, `Email`, `OOB`, and `Single Select`.

The original workbook is treated as the `default` issuer. The uploaded workbook is read-only; normalization is stored only in the local runtime JSON profile. A failed import must not replace the last valid profile.

## Mode Catalog

- Rename the visible `direct_otp` mode to `sms_otp`.
- Add `email_otp`.
- Continue accepting `direct_otp` as a server-side alias for `sms_otp` so existing requests and saved data do not break.
- Do not show `direct_otp` in the settings page.

## Mode-to-Sheet Mapping

| Issuer Mode | Source sheets and flow |
| --- | --- |
| `sms_otp` | `SMS` |
| `email_otp` | `Email` |
| `direct_oob` | `OOB` |
| `selection_sms_oob` | `Single Select`, then test both `SMS` and `OOB` destinations |
| `selection_sms_email` | `Single Select`, then test both `SMS` and `Email` destinations |
| `selection_sms_email_oob` | `Single Select`, then test `SMS`, `Email`, and `OOB` destinations |
| `selection_email_oob` | `Single Select`, then test both `Email` and `OOB` destinations |
| `default_oob_can_switch_otp` | Start with `OOB`, click the switch/send-code control, submit CReq, then validate the returned `SMS` OTP page |

`3RI` is not included in this Challenge UI case generation scope.

## Raw Workbook Normalization

Each source row is identified by:

`source sheet + device channel + message category + wording code + locale`

Non-empty UI columns are converted to normalized field keys, including:

- `驗證訊息標題` -> `challenge_title`
- `驗證訊息欄位文字` -> `challenge_message`
- `驗證訊息欄位標籤` -> `challenge_label`
- `第二組驗證碼標籤` -> `second_challenge_label`
- `下一步標籤` -> `next_button`
- `重送驗證標籤` -> `resend_button`
- `繼續OOB作業標籤` -> `continue_oob_button`
- `是否需要幫助標籤` -> `help_label`
- `幫助文字` -> `help_text`

Additional non-empty UI columns remain available under stable normalized field keys. Placeholder tokens such as `{0}` and HTML line breaks remain in the normalized value for dynamic comparison.

Rows are imported when their channel, category, code, and locale are present. The optional `是否完成` value is retained as metadata but does not suppress otherwise valid default wording.

## Dynamic Case Generation

Cases before the existing UI wording section remain unchanged. Imported UI cases replace the static language copies from case23 onward.

For the selected mode, each unique grouping of:

`flow stage + message category + wording code + locale`

produces one deterministic case. IDs use a stable readable form such as:

`ui_sms_pa_send_sms_otp_zh_TW`

Case names display the source, category, code, and locale. Expected output contains field-level UI values from the workbook. Supported languages are derived from the selected source sheets; the current default workbook produces `zh_TW`, `en_US`, and `zh_CN`.

Selection modes include the selection page and every destination configured by that mode:

1. A `Single Select` page case for each available category, code, and locale.
2. Separate branch cases that choose and validate each configured destination from `SMS`, `Email`, or `OOB`.

The four supported selection combinations are SMS + OOB, SMS + Email, SMS + Email + OOB, and Email + OOB. A mode is incomplete when its `Single Select` wording does not expose every configured destination; its affected cases remain visible but disabled with the missing-option reason.

`default_oob_can_switch_otp` produces compound switch-flow cases per category and locale. Each case validates the initial OOB fields, the switch control, the outgoing CReq transition, and the returned SMS OTP fields.

If required fields for a generated stage are missing, the case remains visible but its checkbox is disabled with a concrete missing-field reason.

## Settings Behavior

Changing Issuer Mode reloads the case catalog immediately using the already imported profile. Import success displays:

- Detected source format.
- Imported source sheets.
- Available languages.
- Normalized wording count.
- Generated case count for the selected mode.

No manual format selector is added.

## Runtime Execution

Generated cases carry explicit metadata for source sheet, category, wording code, locale, and flow stages. Runtime behavior must use this metadata rather than parsing display names.

- SMS and Email OTP cases use OTP submission and resend behavior appropriate to their wording code.
- Single Select cases select each configured destination option in a separate run before validating that destination page.
- OOB cases use the current OOB challenge path.
- OOB-to-SMS cases issue the switch CReq and validate both captured pages.

Existing result output continues showing expected fields, actual visible text, red differences, and `acsTransID` tracking.

## Error Handling

- Reject workbooks that match neither supported format.
- Report missing required source columns with the sheet and column name.
- Reject conflicting duplicate runtime keys while safely deduplicating identical rows.
- Preserve the last valid JSON profile after every failed import.
- Keep unsupported or incomplete generated cases visible and disabled.

## Testing

- Parser tests cover raw-format detection, header mapping, languages, source sheet metadata, identical duplicate handling, and atomic failure behavior.
- Mode tests cover SMS, Email, direct OOB, all four Single Select destination combinations, and OOB-to-SMS switch generation.
- Alias tests prove `direct_otp` resolves to `sms_otp` while the catalog only exposes the new visible value.
- API tests upload a raw workbook and verify generated IDs, source format, language list, and selected-mode case counts.
- Frontend tests verify mode changes reload cases and import summaries display format, languages, and generated count.
- The full regression suite must pass before restart and push.
