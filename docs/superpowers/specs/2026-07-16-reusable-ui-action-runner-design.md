# Reusable UI Action Runner Design

## Goal

Complete the pending Excel-generated browser UI cases without duplicating flow logic per locale. A reusable action registry will drive selection, OTP, resend, OOB, and slow expiration flows, while locale-specific case data supplies only `browserLanguage` and expected UI wording.

## Scope

- Complete action planning and execution for the 68 generated cases in `selection_sms_email_oob` mode.
- Reuse the same action sequence across `en_US`, `zh_CN`, and `zh_TW` when those locales are present in the imported workbook.
- Validate the Excel fields at the challenge stage where each field is expected.
- Keep OTP expiration configurable and excluded from normal full runs by default.
- Distinguish unimplemented behavior, UI assertion failures, ACS failures, and passing results.
- Preserve existing legacy case behavior unless a generated-case boundary currently causes incorrect execution.

## Architecture

### Case Inputs

Each generated case has three independent inputs:

1. `flow`: the navigation shape, such as `selection_page`, `selection_branch`, `direct`, or `oob_switch_sms`.
2. `wordingScenario`: the semantic behavior, such as `initial_challenge`, `incorrect_otp`, `resend_success`, `resend_gap_limit`, `resend_count_limit`, or `expired_otp`.
3. Locale data: `browserLanguage` and each stage's `expectedFields` from Excel.

Flow and scenario determine behavior. Locale data never selects runner behavior.

### Action Registry

A registry maps semantic flow inputs to reusable actions. The plan builder composes actions instead of parsing localized function-point text or relying on a legacy `baseCaseId` alone.

Supported actions include:

- `send_areq`
- `assert_authentication_mode_page`
- `choose_authentication_mode`
- `assert_otp_page`
- `lookup_otp`
- `submit_otp`
- `resend_otp`
- `resend_until_limit`
- `assert_oob_page`
- `continue_oob`
- `switch_to_otp`
- `wait_otp_expiry`
- `assert_stage_ui`
- `expect_cres`

An action carries only behavior-specific parameters. For example, `choose_authentication_mode` carries `destination` and `challengeValue`, while `assert_stage_ui` carries a stage name such as `single_select`, `sms`, `email`, or `oob`.

Example selection SMS incorrect-OTP plan:

```text
send_areq
assert_authentication_mode_page
assert_stage_ui(single_select)
choose_authentication_mode(destination=sms, challengeValue=1)
assert_otp_page
submit_otp(purpose=failure)
assert_stage_ui(sms)
```

The same plan is used for every locale.

## Stage UI Validation

Each response page is captured as an action result with its page type, raw HTML, visible text, request/response evidence, and assertion result. `assert_stage_ui` reads only `expected.stageUiFields[stage]`; it does not compare wording from another page in the flow.

Visible wording includes regular text and user-visible HTML attributes such as `placeholder`, relevant input/button `value`, `aria-label`, `title`, and `alt`. Script and style contents are not user-visible and must not participate in matching.

Excel values may contain runtime placeholders such as `{0}`, `{1}`, `{2}`, `{3}`, and `{4}`. Matching treats each placeholder as a non-empty wildcard after normalizing whitespace and HTML text. Static text around placeholders must remain in order. Literal comparison remains the default when no placeholder is present.

The result identifies each Excel field by key and returns its expected value, matched stage, status, and relevant actual text. Raw HTML remains in collapsed technical details.

## Flow Behavior

### Selection Page

When a case expects `selection_page`, the initial challenge must be `authentication_mode`. The runner validates `single_select` fields and stops without selecting a method.

When a `selection_branch` case is executed, the runner requires the initial `authentication_mode` page, validates the `single_select` stage, selects the requested destination, and continues to the destination stage. If ACS skips the selection page, the case fails with a stage/page-type mismatch rather than silently continuing.

For legacy cases that do not declare a generated selection flow, selection remains conditional: a method is submitted only when ACS actually returns `authentication_mode`.

### OTP

SMS and Email use the same OTP actions. Destination changes the selected authentication value and stage name, not the underlying action implementation.

- `send_otp`: validate the first OTP page.
- `incorrect_otp`: submit the configured failure OTP and validate the returned OTP error page.
- `resend_otp`: request a resend and validate the returned resend wording.
- `resend_gap_limit`: resend without the configured interval and validate the gap warning.
- `resend_count_limit`: resend until the configured limit and validate the limit page.
- `expired_otp`: wait for the configured expiration and submit or inspect the expired challenge as required by the ACS response.

ACS-generated successful OTP retains the existing one-second, one-retry behavior when the first submission remains on the OTP page.

### OOB

OOB actions validate the OOB page without reusing OTP submission behavior. Initial and uncompleted OOB scenarios share navigation actions but assert different stage wording. `oob_switch_sms` validates OOB, submits the switch action, then reuses the SMS OTP actions and SMS stage assertion.

## Slow Cases

`expired_otp` plans contain `wait_otp_expiry`, but normal full runs do not execute them. The SIT run request accepts:

- `includeSlowCases`: boolean, default `false`.
- `otpExpiryWaitSeconds`: configurable positive number used only when slow cases are enabled.

With the default configuration, expiration cases return `skipped` with a structured slow-case reason. With `includeSlowCases=true`, they wait and execute normally. Unit and integration tests use an injected sleep function and do not wait in real time.

## Implementation Status

Generated case implementation status is capability-based:

- `completed`: the registry can build a complete plan and all required Excel stages exist.
- `pending`: no action mapping exists for the flow/scenario/destination combination.
- `unavailable`: required wording or a required paired stage is missing.

The legacy progress file remains authoritative for legacy catalog progress. A generated case marked `pending` must never bypass the status through its `baseCaseId`. Conversely, a generated case with a complete registry plan does not require a separate per-locale progress entry.

## Result Classification

Runner results include a machine-readable classification:

- `passed`: all executed actions and assertions passed.
- `not_implemented`: no complete reusable plan exists.
- `assertion_failed`: ACS returned a usable flow, but page type or expected UI wording did not match.
- `acs_error`: ACS returned an Erro message or transport failure.
- `skipped_slow`: the plan is complete but slow execution was not enabled.

The existing top-level `pass`, `fail`, `error`, and `skipped` statuses remain for UI compatibility. The classification explains why that status was assigned.

## Error Handling

- ACS transient 403 retry behavior remains unchanged. Exhausted retries are classified as `acs_error`, not UI assertion failures.
- Missing forms, required inputs, action URLs, or unexpected page types stop the current case and record the failed action.
- A failed action does not trigger later mutation actions, preventing invalid OTP, resend, or OOB submissions against the wrong page.
- Technical details retain ordered action evidence without exposing it in the primary expected/actual wording comparison.

## Testing

### Plan Tests

- Parameterize every supported `flow + wordingScenario + destination` combination.
- Assert that locale changes do not change action types or behavior parameters.
- Assert that only `browserLanguage` and expected stage fields vary by locale.
- Assert that an unsupported combination is `pending` and cannot run through `baseCaseId` fallback.

### UI Assertion Tests

- Match visible element text and supported visible attributes.
- Ignore script and style content.
- Match `{0}` through `{4}` against non-empty runtime values while preserving surrounding static text order.
- Report individual Excel field results against the correct stage.

### Runner Tests

- Selection-page-only validation.
- Selection to SMS and Email OTP flows.
- Selection to OOB flow.
- Incorrect OTP, resend, gap-limit, and resend-limit flows.
- OOB initial, uncompleted, and switch-to-SMS flows.
- Slow cases skipped by default and executed only with `includeSlowCases=true`.
- ACS error classification and prevention of subsequent actions.

### Catalog Tests

- All generated cases in the imported fixture receive capability-based status.
- Completed generated cases have a complete action plan.
- No pending generated case is reported as pass or fail from a live transaction.

### Verification

After unit and integration tests pass, run the current imported workbook against the configured test card and AReq URL. The default full run excludes expiration waits. Failures are reviewed by classification, with external ACS errors separated from action and UI assertion failures.

## Delivery Strategy

Implementation proceeds in independently tested slices:

1. Action registry and capability status.
2. Stage-aware UI matching and placeholder support.
3. Generic action executor for selection and OTP.
4. Resend and limit actions.
5. OOB and switch actions.
6. Configurable slow expiration actions.
7. Full catalog and live verification.
