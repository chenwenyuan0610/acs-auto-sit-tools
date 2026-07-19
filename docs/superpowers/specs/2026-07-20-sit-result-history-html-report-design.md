# SIT Result History and HTML Report Design

## Goal

Add a local-first result workflow for Browser SIT runs. After the selected cases finish, the user can review the complete run, save it locally on demand, reopen saved runs, and download a standalone HTML report. A run may contain one case or many cases.

The feature must make `acsTransID` easy to copy into another tool such as Excel while also presenting the overall result of the run.

## Confirmed Product Decisions

- Saving is manual. Finishing a run does not write history automatically.
- Local history uses JSON files rather than a database.
- HTML is generated only when the user clicks **Download HTML report**.
- Saving JSON and downloading HTML remain separate operations.
- A run is complete when every selected case reaches a terminal status, including a one-case run.
- Each displayed `acsTransID` is directly clickable to copy its complete value.
- There is no bulk-copy action for transaction IDs.
- Result surfaces do not display the wording-profile issuer ID.
- Card scheme and Issuer OID are parsed from the actual AReq URL used by the run.

## User Experience

### Current Run Header

The result view shows the execution context before the aggregate result:

- Issuer mode, such as `default_oob_can_switch_otp` with its user-facing label.
- Effective preferred challenge, such as `otp`.
- Wording locale.
- Card scheme parsed from the AReq URL, such as `V`.
- Issuer OID parsed from the AReq URL, such as `eff82784-e641-8477-3b5b-f14c2ed2ee10`.
- Run start and finish timestamps.
- Selected case count and IDs.

For the known URL shape:

```text
/auth/{cardScheme}/{version}/{issuerOid}/{routeId}/areq
```

the parser extracts `cardScheme` and `issuerOid`. If the URL does not match this shape, the run remains valid and both values display as unavailable. The original AReq URL remains in the saved execution context for diagnostics.

### Aggregate Result

The current run displays:

- Total selected cases.
- Completed cases.
- Passed cases.
- Failed cases.
- Skipped cases.
- Error cases.
- Completion percentage.
- Pass percentage.

The aggregate counts use the same status classification as the existing `/api/sit/run` summary so the case list and summary cannot disagree.

### Per-Case Result

Each result row shows:

- Case ID and function point.
- Terminal status.
- AReq sent timestamp with millisecond precision.
- `acsTransID`, when available.
- Transaction-result summary.
- Elapsed duration.
- A way to open the existing detailed expected/actual, action, and technical evidence.

The transaction summary includes:

- Lookup state: not requested, succeeded, or failed.
- `transStatus`.
- ECI.
- Whether CAVV is present.
- Overall transaction validation outcome when checks are available.

Clicking an `acsTransID` copies the complete untruncated value. The UI may visually truncate a long value, but its accessible label exposes the full ID and makes the copy action explicit. A short non-blocking confirmation appears after a successful copy. Clipboard failure shows an actionable error and leaves the value selectable.

### Actions

The result actions are disabled while any selected case is still running. They become available as soon as all selected cases reach terminal states, whether the run contains one case or many.

**Save locally** writes the current run as JSON and adds it to local history. Repeated clicks for the same run update the same file rather than creating duplicates.

**Download HTML report** generates a standalone read-only snapshot from the current run. It does not require the run to have been saved first. A saved historical run can also be reopened and downloaded as HTML later.

Suggested report names are deterministic and filesystem-safe:

```text
sit-report-{cardScheme}-{case-or-count}-{YYYYMMDD-HHmmss}.html
```

For example:

```text
sit-report-V-case01-20260720-001530.html
sit-report-V-43-cases-20260720-001530.html
```

### History

The history list shows only manually saved runs. Each item includes:

- Start time.
- Card scheme.
- Issuer mode or compact flow label.
- Passed count and total count.

Opening an item renders the same aggregate and per-case result components in read-only historical mode. The user can download its HTML report. History deletion is outside the first implementation scope.

## Persistence Model

Saved runs live under a runtime-data directory excluded from Git:

```text
data/sit-runs/{runId}.json
```

The directory is created on first save. Files are UTF-8 JSON and use an explicit schema version.

Top-level shape:

```json
{
  "schemaVersion": 1,
  "runId": "20260720T001530000Z-a1b2c3d4",
  "startedAt": "2026-07-20T00:15:30.000+08:00",
  "finishedAt": "2026-07-20T00:16:12.420+08:00",
  "execution": {
    "issuerMode": "default_oob_can_switch_otp",
    "effectivePreferredChallenge": "otp",
    "wordingLocale": "zh_TW",
    "areqUrl": "https://example/auth/V/220/eff82784-e641-8477-3b5b-f14c2ed2ee10/123/areq",
    "cardScheme": "V",
    "issuerOid": "eff82784-e641-8477-3b5b-f14c2ed2ee10",
    "selectedCaseIds": ["case01"]
  },
  "summary": {
    "total": 1,
    "completed": 1,
    "pass": 1,
    "fail": 0,
    "skipped": 0,
    "error": 0
  },
  "results": []
}
```

Each case result retains the existing result payload and adds normalized report fields rather than requiring the report renderer to search multiple nested response shapes:

```json
{
  "caseId": "case01",
  "status": "pass",
  "areqSentAt": "2026-07-20T00:15:30.214+08:00",
  "finishedAt": "2026-07-20T00:15:32.614+08:00",
  "durationMs": 2400,
  "acsTransID": "acs-trans-id",
  "transactionResult": {
    "lookupStatus": "succeeded",
    "transStatus": "Y",
    "eci": "02",
    "cavvPresent": true,
    "validationStatus": "pass",
    "raw": {}
  },
  "details": {}
}
```

Sensitive request headers and secrets are not added to the report model. Existing technical evidence is retained only where it is already part of a case result; HTML rendering escapes every value and does not execute returned challenge markup.

## Backend Components and APIs

### Result Normalizer

A focused result-normalization module converts current runner output into the versioned saved/report model. It owns:

- Stable `acsTransID` extraction.
- Timestamp and duration normalization.
- Transaction-result normalization.
- AReq URL context parsing.
- Summary calculation.

Both local persistence and HTML rendering consume this normalized model.

### Local Repository

A local run repository owns filesystem access:

- Atomic save using a temporary file followed by replace.
- Validation of schema version and required fields when loading.
- Newest-first history listing using metadata from each file.
- Exact lookup by server-generated `runId` only; callers cannot supply paths.

Malformed files are skipped from the history response and reported as warnings rather than preventing valid history from loading.

### HTML Renderer

The renderer produces one self-contained UTF-8 HTML document with embedded CSS and no external assets, scripts, API calls, or local-file dependencies. It includes the execution context, aggregate counts, and complete per-case table. Case details use native expandable sections. Transaction IDs are plain selectable text in the report; clipboard interaction remains an application UI feature.

### API Surface

Add local endpoints following the existing server style:

```text
POST /api/sit/runs
GET  /api/sit/runs
GET  /api/sit/runs/{runId}
POST /api/sit/reports/html
GET  /api/sit/runs/{runId}/report.html
```

- `POST /api/sit/runs` accepts the completed current-run payload, normalizes it on the server, saves it, and returns saved metadata.
- `GET /api/sit/runs` returns lightweight newest-first history entries.
- `GET /api/sit/runs/{runId}` returns one saved normalized run.
- `POST /api/sit/reports/html` renders an unsaved completed run for immediate download.
- `GET /api/sit/runs/{runId}/report.html` renders a saved run for download.

The server rejects saving or reporting a run whose selected cases are not all terminal. It also rejects an empty selection.

## Data Flow

1. The frontend creates a run ID and records `startedAt` before calling `/api/sit/run`.
2. The runner records `areqSentAt` immediately before each outbound AReq and `finishedAt` when the case reaches a terminal state.
3. Existing execution and transaction-result data return to the frontend.
4. The frontend renders the current run without writing a file.
5. **Save locally** posts the completed run to the local repository API.
6. **Download HTML report** posts the current completed run to the renderer, or requests the renderer for a saved run ID.
7. The browser downloads the returned HTML file.

## Error Handling

- An unsupported AReq URL shape produces unavailable card-scheme/OID fields, not a failed test run.
- Missing `acsTransID` displays an em dash and disables copy behavior for that row.
- Transaction lookup failure remains distinct from a transaction validation failure and includes a concise reason.
- Save failure leaves the current result visible and allows retry.
- HTML generation failure does not alter saved history.
- Loading a missing run returns not found without exposing filesystem paths.
- All filenames and response headers use sanitized values.

## Testing Strategy

### Unit Tests

- Parse card scheme `V` and the expected Issuer OID from the current AReq URL shape.
- Return unavailable values for malformed or unsupported URLs.
- Normalize `acsTransID` from every currently supported result location.
- Normalize AReq timestamps, durations, transaction results, and all terminal statuses.
- Save atomically and reload the versioned JSON shape.
- Ignore malformed history files while returning valid entries.
- Render escaped, self-contained HTML containing run context and case details.

### API Tests

- Save and retrieve a one-case run.
- Save and retrieve a multi-case run.
- Reject empty or incomplete runs.
- List history newest first.
- Download HTML for unsaved current results and saved history.
- Prevent path traversal through `runId`.

### Frontend Tests

- Actions remain disabled during a run and enable after all selected cases terminate.
- A one-case run enables the actions when that case finishes.
- Clicking the displayed ID copies the complete value and shows feedback.
- There is no bulk-copy control.
- Mode, preferred challenge, locale, card scheme, and Issuer OID render in the header.
- History loads and reopens a saved result.

### Regression Verification

- Run the complete automated suite.
- Verify the result view at desktop and mobile widths.
- Save, reopen, and export both a single-case and a multi-case run.
- Open downloaded HTML with the SIT server stopped and confirm that all report content remains readable.

## Out of Scope

- Automatic saving after every run.
- SQLite or an external database.
- Bulk-copying transaction IDs.
- Editing a saved result.
- Deleting history in the first release.
- Cross-run trend charts or comparisons.
- Displaying the wording-profile issuer ID.
