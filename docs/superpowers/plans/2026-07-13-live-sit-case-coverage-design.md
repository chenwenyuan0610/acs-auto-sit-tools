# Live SIT Case Coverage Design

## Scope

Run the Browser SIT cases against the supplied CUP AReq endpoint with card
`4771048901645588`. Invalid-card cases use `4771048901645589`, changing only
the final digit.

Excel-imported expectations remain authoritative. Prompt text, ARes, CRes,
RReq, and error assertions are not relaxed to match current ACS output.

## Included Behavior

- Apply case-specific AReq values for PA, NPA, 3RI, and purchase currency.
- Keep OTP lookup through the SIT OTP API and submit the six-digit OTP suffix.
- Run resend cases with `resend=true` through the form field discovered on the
  challenge page.
- Wait 30 seconds before successful resend cases (`case35`-`case38`).
- Submit immediately for resend-too-early cases (`case39`-`case42`).
- Wait 30 seconds before each resend-limit attempt (`case43`-`case46`).
- Forward the case browser language as `Accept-Language` on challenge requests.
- Submit the actual cancel control for `case14` and retain strict CRes/RReq
  validation.

## Excluded Behavior

- `case15`-`case17` and `case22`: removed from the active Browser SIT catalog.
- `case47`-`case50`: require OTP expiration waits.

The removed cases are no longer visible in the active catalog. `case47`-`case50`
remain visible and are skipped by the live runner with a clear reason.

## Verification

Unit tests cover payload mutation, invalid-card derivation, skip reasons,
challenge language headers, cancel submission, and resend timing without real
sleep. Live verification reruns included cases against the supplied endpoint
and records strict Excel-based pass/fail results.
