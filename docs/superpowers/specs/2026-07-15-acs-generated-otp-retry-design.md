# ACS-generated OTP Retry Design

## Goal

Make Browser SIT challenge execution reliable when the ACS-generated OTP is not yet verifiable on the first submission, while preserving the difference between selection and direct OTP flows.

## Flow Rules

- Send an authentication-method selection only when the first challenge page is parsed as `authentication_mode` and the case plan enables automatic selection.
- When the first challenge page is already `otp`, skip authentication-method selection and proceed directly to OTP lookup and submission.
- Keep the case plan's preferred destination behavior for selection pages. `auto` continues to use the issuer mode's default destination.

## OTP Retry

- Apply retry only to a `success` OTP purpose with `otpSourceMode=acs_generated`.
- Submit the looked-up OTP once.
- If the response has no CRes and is another `otp` page, wait one second, perform a fresh OTP lookup for the same ACS transaction, and submit once more.
- Stop immediately when either submission returns CRes.
- Never apply this retry to configured/customer-generated OTP, failure OTP, empty/alpha/special input cases, cancel, resend, or OOB actions.
- Retain both submissions in `otpSubmissions`; `otpSubmission` points to the latest attempt so existing result extraction remains compatible.

## Failure Handling

- After the second unsuccessful submission, keep the final OTP page and return no CRes. The SIT result remains failed rather than looping indefinitely.
- Preserve lookup and HTTP evidence for both attempts in technical details.

## Tests

- A selection page submits the selected authentication method before OTP.
- A direct OTP page does not submit an authentication method.
- ACS-generated success OTP retries once when the first submission returns another OTP page and accepts the second CRes.
- Customer-generated and failure OTP paths do not receive the new retry.

