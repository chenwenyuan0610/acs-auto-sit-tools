# ACS Auto SIT Browser Flow Design

Date: 2026-07-10

## Goal

Build the first version of an ACS automated SIT tool for 3DS browser-based transactions.
The tool starts from AReq, follows the challenge flow through one or more CReq/CRes exchanges, records evidence, and validates results against test-case expectations.

The first version prioritizes reliable automation and evidence capture over a full management dashboard.

## Decisions

- Backend: Python FastAPI.
- Authentication: none.
- Deployment: local machine by default, with optional intranet access by binding to `0.0.0.0`.
- Storage: local files under `data/`.
- Transport: all ACS/3DS transaction calls use POST.
- TLS: normal HTTPS only; no client certificate, custom CA, or insecure TLS option in v1.
- Main automation path: backend POSTs AReq and backend POSTs CReq, so the tool can reliably capture CRes response bodies.
- Browser helper path: a simulator page can auto-submit a hidden POST form to ACS for visual/browser behavior checks, but v1 does not rely on it to capture CRes.
- Test-case source: import the existing Excel test case workbook, with v1 focused on Browser cases and data fields preserved for later app flows.

## Inputs Observed

The provided AReq sample is a 3DS 2.2 browser AReq sent as JSON:

- `messageType = "AReq"`
- `messageVersion = "2.2.0"`
- `deviceChannel = "02"`
- includes browser fields such as `browserAcceptHeader`, `browserIP`, `browserLanguage`, `browserUserAgent`, `browserJavascriptEnabled`
- includes transaction identifiers such as `threeDSServerTransID` and `dsTransID`
- includes a `notificationURL`, which v1 should allow overriding for local or intranet callbacks

The provided Excel workbook has sheets for Browser and app flows. V1 imports Browser rows first, while keeping channel and module fields so app flows can be added later.

## Architecture

### FastAPI Backend

The backend owns:

- test-case import and persistence
- AReq template rendering
- AReq POST execution
- ARes parsing
- CReq generation
- CReq/CRes loop execution
- callback/notification capture as auxiliary evidence
- JSONPath-like validation
- evidence persistence
- static serving for the thin simulator UI

### Simulator UI

The UI is a flow control page, not a full dashboard.

It supports:

- selecting an imported Browser case
- viewing the human test steps and expected results
- editing AReq template values before starting a run
- starting AReq automation
- viewing ARes and extracted fields
- continuing the CReq/CRes loop automatically or step by step
- viewing each CReq/CRes exchange
- opening a browser form auto-submit helper for visual ACS behavior checks
- viewing validation results and run evidence

## Transaction Flow

### 1. Start Run

The user selects a Browser test case and starts a run. The backend creates a run id and renders the AReq template.

Template variables may include:

- `{{callback_url}}`
- `{{threeDSServerTransID}}`
- `{{purchaseDate}}`
- `{{purchaseAmount}}`
- fields copied from the selected case or user overrides

### 2. Send AReq

FastAPI sends a POST request to the configured AReq endpoint with `Content-Type: application/json`.

The run records:

- endpoint
- headers
- rendered AReq body
- HTTP status
- response headers
- raw response body
- parsed JSON body when possible
- elapsed time
- error details, if any

### 3. Parse ARes

The backend extracts flow fields from ARes:

- `messageType`
- `messageVersion`
- `threeDSServerTransID`
- `acsTransID`
- `transStatus`
- `acsURL`, when present

If `transStatus` is final, the run moves to validation. If `transStatus = "C"`, the backend creates a challenge session.

### 4. Run CReq/CRes Loop

V1 treats challenge as a loop, not a single CReq.

The first CReq is generated from ARes:

- `messageType = "CReq"`
- `messageVersion` from ARes, falling back to the AReq message version
- `threeDSServerTransID` from ARes or the original AReq
- `acsTransID` from ARes
- `challengeWindowSize` from the case setting, defaulting to `05`

Later CReq messages are generated from the previous CRes plus case settings. V1 must keep this generation rule explicit and editable because some ACS flows require an action, OTP, resend choice, cancel choice, or other challenge data before the next CReq can be sent.

For each exchange:

1. Generate a CReq draft using ARes and the previous CRes, if any.
2. POST the CReq to the ACS challenge endpoint from ARes `acsURL`.
3. Capture the HTTP response body as CRes.
4. Parse CRes.
5. Decide whether the challenge is complete.

The run stores challenge exchanges as an array:

```json
[
  {
    "sequence": 1,
    "creq": {},
    "cres": {},
    "raw_response": "",
    "status_code": 200,
    "elapsed_ms": 0
  }
]
```

The loop stops when:

- CRes has a final `transStatus`
- CRes has `challengeCompletionInd = "Y"`
- validation or parsing determines the challenge is complete
- the maximum exchange count is reached
- a request error or timeout occurs

The default maximum exchange count is 5.

If a later CReq cannot be generated automatically because the previous CRes requires user input or ACS-specific fields, the run enters a waiting state and shows the editable next-CReq draft in the simulator UI.

### 5. Callback/Notification Capture

V1 provides a POST callback endpoint for auxiliary evidence:

- `POST /api/callback/{run_id}`

The callback stores:

- request headers
- query parameters
- form body
- JSON body, when present
- raw body
- timestamp

Because the current expected CRes source is the CReq HTTP response body, callback data is not the primary completion signal in v1.

## API Shape

Internal tool APIs prefer POST to match the user's operating model and avoid confusion with 3DS transaction calls.

- `POST /api/cases/search`
- `POST /api/cases/save`
- `POST /api/import/excel`
- `POST /api/runs/start`
- `POST /api/runs/detail`
- `POST /api/runs/creq/continue`
- `POST /api/callback/{run_id}`

Simulator pages may be opened in the browser, but every ACS transaction request is POST.

## Local Storage Layout

```text
data/
  cases/
    <case_id>.json
  runs/
    <run_id>.json
  imports/
    <import_id>.json
```

`data/cases/*.json` stores:

- case id
- title
- channel
- module
- test point
- steps
- expected results
- AReq endpoint
- headers
- AReq template
- CReq settings
- validation rules
- imported metadata

`data/runs/*.json` stores:

- run id
- case id
- status
- timestamps
- rendered AReq
- ARes
- extracted fields
- challenge exchanges
- callback records
- validation results
- error records

## Excel Import

V1 imports the Browser sheet first.

Column mapping:

- `ID` -> case id
- `System` -> version hint
- `Module` -> channel/module
- `Function Point` -> title
- `Test Points` -> scheme or test group
- `Steps` -> human-readable procedure
- `Expected Results` -> expected result text and validation-rule draft source
- `Actual Result`, `Test Date`, `Testers`, `Remarks` -> imported metadata

The importer should preserve original text. It may generate validation-rule drafts, but users can edit them before running cases.

## Validation Rules

V1 supports JSONPath-like assertions:

- `exists`
- `not_exists`
- `equals`
- `not_equals`
- `in`
- `not_null`
- `is_null`
- `contains`

Examples:

```json
[
  {
    "target": "cres",
    "path": "$.transStatus",
    "operator": "equals",
    "expected": "Y"
  },
  {
    "target": "callback",
    "path": "$.eci",
    "operator": "equals",
    "expected": "05"
  },
  {
    "target": "callback",
    "path": "$.authenticationValue",
    "operator": "not_null"
  }
]
```

The tool should not over-trust natural-language parsing of Excel expected results. Drafted rules are helpers, not hidden truth.

## Browser Auto-Submit Helper

The helper page generates a hidden form and automatically calls `form.submit()`.

It is useful for checking ACS browser behavior, but it is not the primary automated path in v1 because browser cross-origin navigation can prevent the tool from reliably reading the response body.

The primary automated CReq/CRes path remains backend POST.

## Error Handling

- Timeout: mark run `error`, save last request and timeout details.
- Non-JSON response: save raw body, mark the exchange failed, and stop the automated loop.
- Missing ARes fields: mark run failed with the missing field list.
- Missing ARes `acsURL` when `transStatus = "C"`: mark run failed.
- CReq loop exceeds max exchanges: mark run failed with `max_exchanges_exceeded`.
- Validation failure: mark run completed with failed validation.

## Run Statuses

- `created`
- `areq_sent`
- `challenge_required`
- `challenge_running`
- `waiting_callback`
- `passed`
- `failed`
- `error`

## Out of Scope for V1

- login and authorization
- mTLS or custom TLS certificate configuration
- production database
- multi-user permissions
- full reporting dashboard
- fully automated OTP input and ACS page button clicking
- app native flow automation

## Future Extensions

- Playwright or Selenium automation for OTP entry and ACS page submit.
- App flow support using the imported app sheets.
- Batch execution.
- Evidence export to CSV, ZIP, or HTML report.
- More advanced validation rule editor.
- Environment profiles for multiple ACS endpoints.
