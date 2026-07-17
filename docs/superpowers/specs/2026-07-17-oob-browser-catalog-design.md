# OOB Browser Catalog Design

## Goal

Keep the existing legacy Browser cases OTP-specific and expose a separate OOB test catalog when the effective preferred challenge is OOB. The first OOB catalog contains `oob01` through `oob13` and is stored in `sit_cases/oob_browser_cases.json`.

## Scope

The first OOB set covers challenge success with CAVV verification, cancel, reject, PA and NPA valid/invalid card paths, 3RI valid/invalid card paths, transaction interruption, and English PA/NPA OOB UI states. Timeout cases, ACS Admin configuration changes, and currency scenarios are excluded.

## Architecture

The OTP and OOB catalogs remain separate repository artifacts. The server resolves issuer mode and preferred challenge first, then passes the effective preferred challenge into catalog loading. An effective value of `oob` selects `sit_cases/oob_browser_cases.json`; all other supported values select the existing OTP Browser catalog.

Catalog selection is authoritative. A missing or malformed OOB catalog raises a clear catalog error and never falls back to OTP cases. This prevents an OOB configuration from displaying or executing OTP-only cases.

Each OOB case declares `challengeType: "oob"` and uses an `oobNN` identifier. OOB progress is keyed independently from `case01` through `case20`. Existing OOB action execution and transaction-result lookup are reused rather than duplicated.

## Initial Cases

1. `oob01`: OOB challenge success and CAVV verification.
2. `oob02`: User cancellation.
3. `oob03`: User rejection.
4. `oob04`: PA valid card.
5. `oob05`: PA invalid card.
6. `oob06`: NPA valid card.
7. `oob07`: NPA invalid card.
8. `oob08`: 3RI valid card.
9. `oob09`: 3RI invalid card.
10. `oob10`: Transaction interruption.
11. `oob11`: English PA OOB authentication page.
12. `oob12`: English PA OOB uncompleted page.
13. `oob13`: English NPA OOB authentication and uncompleted-page coverage.

The implementation plan may refine expected protocol fields to match existing runner interfaces, but it must not add excluded scenario categories.

## Data Flow

The browser sends `issuerMode` and `preferredChallenge` to the Browser cases API. The backend resolves `auto` through the selected issuer mode's default challenge. Catalog loading returns only the selected challenge family. The frontend renders the returned cases without a second filtering layer, and live execution resolves cases from the same selected catalog so display and execution cannot diverge.

For selection modes, choosing OOB returns only OOB cases. Choosing SMS or Email returns the current OTP catalog. Direct OOB always resolves to the OOB catalog. Switching the control reloads the list through the existing API request flow.

## Error Handling

- Reject unsupported preferred challenges through existing validation.
- Report missing, malformed, or structurally invalid OOB catalog data explicitly.
- Reject duplicate IDs and cases whose `challengeType` is not `oob`.
- Do not silently return OTP cases after an OOB catalog error.
- Preserve current errors for the existing OTP catalog.

## Testing

Focused tests will verify direct OOB, selection-mode OOB, SMS after switching back, and `auto` default resolution. Contract tests will assert that OOB responses contain exactly `oob01` through `oob13`, OTP responses do not contain OOB IDs, and list/run APIs resolve the same catalog. Invalid OOB catalog fixtures will prove that no OTP fallback occurs.

The full automated suite will run with a workspace-local pytest base temp. Existing OTP behavior and generated wording cases must remain green.
