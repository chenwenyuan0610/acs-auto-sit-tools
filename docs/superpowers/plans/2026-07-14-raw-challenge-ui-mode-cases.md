# Raw Challenge UI Mode Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the original `challenge_ui_info.xlsx` format and generate executable localized Challenge UI cases for direct and four Single Select issuer-mode combinations.

**Architecture:** Keep workbook detection, normalization, and case projection in `acs_auto_sit.wording_profiles`; keep the public mode catalog and compatibility alias in `acs_auto_sit.issuer_modes`. `sit_runner` replaces legacy UI cases with metadata-driven generated cases, while `server` consumes explicit flow metadata for SMS, Email, OOB, Single Select branches, and OOB-to-SMS switching. The browser remains a thin API client that reloads cases after mode changes and reports import metadata.

**Tech Stack:** Python 3, `openpyxl`, `pytest`, standard-library HTTP server, vanilla HTML/CSS/JavaScript.

## Global Constraints

- Default locales remain exactly `zh_TW`, `en_US`, and `zh_CN`.
- Visible direct modes are `sms_otp`, `email_otp`, and `direct_oob`; `direct_otp` remains only as a server-side alias for `sms_otp`.
- Single Select modes are exactly `selection_sms_oob`, `selection_sms_email`, `selection_sms_email_oob`, and `selection_email_oob`.
- `default_oob_can_switch_otp` starts in OOB and switches to SMS OTP by sending CReq.
- `3RI` is excluded.
- Missing required wording keeps a case visible and disabled with a concrete reason.
- Failed imports never replace the last valid JSON profile.

---

### Task 1: Detect and normalize the original workbook

**Files:**
- Modify: `acs_auto_sit/wording_profiles.py`
- Test: `tests/test_wording_profiles.py`

**Interfaces:**
- Produces: `import_wording_workbook(content: bytes, destination: Path, source_file: str = "") -> dict[str, Any]` with `sourceFormat`, `sourceSheets`, normalized `wordings`, and expanded `summary`.
- Produces normalized wording records containing `sourceSheet`, `messageCategory`, `wordingCode`, `locale`, `fieldKey`, `content`, and optional `completionStatus`.

- [ ] **Step 1: Add failing raw workbook parser tests**

Create a synthetic workbook with `SMS`, `Email`, `OOB`, and `Single Select` sheets and the required Chinese headers. Assert format detection, field-key mapping, source sheets, locale order, placeholder preservation, identical duplicate removal, conflicting duplicate rejection, and preservation of an existing destination after failure.

```python
imported = import_wording_workbook(raw_workbook_bytes(), destination, source_file="challenge_ui_info.xlsx")
assert imported["sourceFormat"] == "challenge_ui_info"
assert imported["sourceSheets"] == ["SMS", "Email", "OOB", "Single Select"]
assert imported["defaultSupportedLocales"] == ["zh_TW", "en_US", "zh_CN"]
assert any(item["sourceSheet"] == "SMS" and item["fieldKey"] == "challenge_title" for item in imported["wordings"])
```

- [ ] **Step 2: Run parser tests and verify RED**

Run: `python -m pytest tests/test_wording_profiles.py -q`

Expected: FAIL because raw sheet detection and `sourceFormat` are not implemented.

- [ ] **Step 3: Implement auto-detection and raw-row normalization**

Add `RAW_SOURCE_SHEETS`, required identifier headers, and a complete Chinese-header-to-field-key map. Detect normalized workbooks by `發卡行設定` + `話術匯入`, otherwise detect raw workbooks by supported source sheet names. Convert each non-empty UI cell into one normalized wording record, retain `{0}` placeholders and HTML breaks unchanged, retain `是否完成`, and reject malformed sheets with sheet-specific errors.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `python -m pytest tests/test_wording_profiles.py -q`

Expected: all wording-profile parser tests pass.

- [ ] **Step 5: Commit the parser increment**

```powershell
git add acs_auto_sit/wording_profiles.py tests/test_wording_profiles.py
git commit -m "feat: import raw challenge UI workbooks"
```

### Task 2: Define mode catalog and compatibility aliases

**Files:**
- Modify: `acs_auto_sit/issuer_modes.py`
- Modify: `acs_auto_sit/case_progress.py`
- Test: `tests/test_sit_runner_api.py`
- Test: `tests/test_case_progress.py`

**Interfaces:**
- Produces: `resolve_issuer_mode("direct_otp")` returning the canonical `sms_otp` mode.
- Produces mode dictionaries with `destinations: list[str]` used by case generation and runtime execution.

- [ ] **Step 1: Add failing catalog and alias tests**

```python
assert [item["id"] for item in issuer_mode_catalog()["issuerModes"]] == [
    "sms_otp", "email_otp", "direct_oob", "selection_sms_oob",
    "selection_sms_email", "selection_sms_email_oob", "selection_email_oob",
    "default_oob_can_switch_otp",
]
assert resolve_issuer_mode("direct_otp")["id"] == "sms_otp"
assert resolve_issuer_mode("selection_sms_email_oob")["destinations"] == ["sms", "email", "oob"]
```

- [ ] **Step 2: Run mode tests and verify RED**

Run: `python -m pytest tests/test_sit_runner_api.py::test_issuer_modes_api_returns_manual_mode_choices tests/test_case_progress.py -q`

Expected: FAIL because the new mode IDs and alias are absent.

- [ ] **Step 3: Implement canonical modes and progress compatibility**

Set `DEFAULT_ISSUER_MODE = "sms_otp"`, add explicit `destinations` to every mode, add `email` to preferred challenges, and canonicalize `direct_otp` before catalog lookup. Treat saved `direct_otp` progress as `sms_otp` while preserving old progress-file readability.

- [ ] **Step 4: Run mode tests and verify GREEN**

Run: `python -m pytest tests/test_sit_runner_api.py::test_issuer_modes_api_returns_manual_mode_choices tests/test_case_progress.py -q`

Expected: selected tests pass.

- [ ] **Step 5: Commit the mode increment**

```powershell
git add acs_auto_sit/issuer_modes.py acs_auto_sit/case_progress.py tests/test_sit_runner_api.py tests/test_case_progress.py
git commit -m "feat: expand challenge issuer modes"
```

### Task 3: Generate mode-specific UI cases from normalized rows

**Files:**
- Modify: `acs_auto_sit/wording_profiles.py`
- Modify: `acs_auto_sit/sit_runner.py`
- Test: `tests/test_wording_profiles.py`

**Interfaces:**
- Produces: `build_localized_wording_cases(..., issuer_mode: str) -> list[dict[str, Any]]` grouped by flow stage, category, code, and locale.
- Generated cases expose `wording.sourceSheet`, `wording.messageCategory`, `wording.code`, `wording.locale`, `flow.stages`, `flow.destination`, and `availability`.

- [ ] **Step 1: Add failing generation tests for every mode**

Assert `sms_otp` only uses `SMS`, `email_otp` only uses `Email`, and each selection mode generates one selection stage plus separate destination branch cases. Assert `selection_sms_email_oob` contains SMS, Email, and OOB branches; `default_oob_can_switch_otp` contains `oob` and `sms` stages with `switchCreq: True`; IDs remain deterministic; and incomplete options are visible but disabled.

```python
cases = build_localized_wording_cases(profiles, templates, issuer_mode="selection_sms_email_oob")
assert {case["flow"]["destination"] for case in cases if case["flow"]["kind"] == "selection_branch"} == {"sms", "email", "oob"}
assert all(case["wording"]["locale"] in {"zh_TW", "en_US", "zh_CN"} for case in cases)
```

- [ ] **Step 2: Run generation tests and verify RED**

Run: `python -m pytest tests/test_wording_profiles.py -q`

Expected: FAIL because generation still uses seven fixed SMS scenarios.

- [ ] **Step 3: Implement metadata-driven projection**

Replace fixed scenario iteration with source-sheet filtering based on canonical mode destinations. Group normalized fields into records keyed by source sheet, category, code, and locale; select the nearest compatible legacy base case by code family; construct stable IDs; merge field-level expected output; and disable rather than remove incomplete records. Preserve normalized-workbook behavior through the compatibility source metadata inferred from wording codes.

- [ ] **Step 4: Run wording and catalog tests and verify GREEN**

Run: `python -m pytest tests/test_wording_profiles.py tests/test_sit_excel.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit the generation increment**

```powershell
git add acs_auto_sit/wording_profiles.py acs_auto_sit/sit_runner.py tests/test_wording_profiles.py
git commit -m "feat: generate UI cases by issuer mode"
```

### Task 4: Execute generated destination flows

**Files:**
- Modify: `acs_auto_sit/case_plan.py`
- Modify: `acs_auto_sit/server.py`
- Test: `tests/test_direct_otp_case_plan.py`
- Test: `tests/test_selection_sms_otp_case_plan.py`
- Test: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces: case plans driven by `case["flow"]` and canonical mode `destinations`.
- Consumes generated `flow.destination`, `flow.stages`, and `flow.switchCreq` without parsing case names.

- [ ] **Step 1: Add failing execution-plan tests**

Add cases proving SMS and Email select distinct challenge values, OOB remains on the current path, every selection destination is chosen in its own plan, and OOB-to-SMS performs the switch action before OTP lookup/submission.

```python
plan = build_case_plan(case_with_flow("selection_branch", "email"), resolve_issuer_mode("selection_sms_email"))
assert plan["actions"][1]["preferredChallenge"] == "email"

switch_plan = build_case_plan(case_with_flow("oob_switch_sms", "sms"), resolve_issuer_mode("default_oob_can_switch_otp"))
assert [action["type"] for action in switch_plan["actions"]].index("switch_to_otp") < [action["type"] for action in switch_plan["actions"]].index("lookup_otp")
```

- [ ] **Step 2: Run execution tests and verify RED**

Run: `python -m pytest tests/test_direct_otp_case_plan.py tests/test_selection_sms_otp_case_plan.py tests/test_sit_runner_api.py -q`

Expected: FAIL because case-plan selection only recognizes the legacy two OTP mode IDs.

- [ ] **Step 3: Implement generic flow-aware case planning and server routing**

Add one canonical plan builder that maps `sms`, `email`, and `oob` to explicit selection preferences, keeps legacy wrappers for current callers, and routes generated cases by flow metadata. Extend challenge-option matching to recognize Email labels/values. Reuse the current OOB switch CReq implementation for `default_oob_can_switch_otp`, then continue through SMS OTP lookup and submission.

- [ ] **Step 4: Run execution tests and verify GREEN**

Run: `python -m pytest tests/test_direct_otp_case_plan.py tests/test_selection_sms_otp_case_plan.py tests/test_sit_runner_api.py -q`

Expected: all execution tests pass.

- [ ] **Step 5: Commit the runtime increment**

```powershell
git add acs_auto_sit/case_plan.py acs_auto_sit/server.py tests/test_direct_otp_case_plan.py tests/test_selection_sms_otp_case_plan.py tests/test_sit_runner_api.py
git commit -m "feat: execute generated challenge UI flows"
```

### Task 5: Update API summaries and settings UI

**Files:**
- Modify: `acs_auto_sit/server.py`
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_server.py`
- Test: `tests/test_frontend_error_handling.py`

**Interfaces:**
- Import API returns `sourceFormat`, `sourceSheets`, `defaultSupportedLocales`, normalized count, and generated count for the requested mode.
- Settings mode changes call `/api/sit/browser-cases` with the selected canonical mode.

- [ ] **Step 1: Add failing API and frontend contract tests**

Upload a synthetic raw workbook through the import endpoint and assert response metadata plus different case IDs/counts for `sms_otp`, `email_otp`, and `selection_sms_email_oob`. Assert static options and labels contain all visible modes, omit `direct_otp`, include Email as a preferred challenge, and reload cases on mode changes.

- [ ] **Step 2: Run API/frontend tests and verify RED**

Run: `python -m pytest tests/test_server.py tests/test_frontend_error_handling.py -q`

Expected: FAIL because import summaries and visible mode labels are still legacy-only.

- [ ] **Step 3: Implement API summary and browser updates**

Return format/sheet/language/count metadata from profile endpoints. Replace static legacy options and JS labels with the canonical modes, render import status as format + sheets + languages + normalized rows + current generated case count, and reload the catalog immediately on mode/profile changes.

- [ ] **Step 4: Run API/frontend tests and verify GREEN**

Run: `python -m pytest tests/test_server.py tests/test_frontend_error_handling.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit the UI/API increment**

```powershell
git add acs_auto_sit/server.py static/index.html static/app.js static/styles.css tests/test_server.py tests/test_frontend_error_handling.py
git commit -m "feat: expose raw workbook modes in settings"
```

### Task 6: Real-workbook, regression, browser, and server verification

**Files:**
- Modify only if verification exposes a requirement defect.
- Update: `docs/sit-case-progress.md` with completed feature and verification evidence.

**Interfaces:**
- Verifies the complete user workflow with `C:\Users\diegochen\Downloads\challenge_ui_info.xlsx` and fixed port `8000`.

- [ ] **Step 1: Import the supplied workbook into a temporary profile and inspect counts**

Run a focused Python command that calls `import_wording_workbook` against the supplied file and prints `sourceFormat`, `sourceSheets`, languages, and normalized count. Then build catalogs for all eight visible modes and assert every generated ID is unique.

- [ ] **Step 2: Run the full regression suite**

Run: `python -m pytest -q`

Expected: all tests pass with no skips introduced by this feature.

- [ ] **Step 3: Restart the fixed local server**

Stop the process currently listening on `127.0.0.1:8000`, start `python -m acs_auto_sit.server --host 127.0.0.1 --port 8000`, and verify `GET /` plus the issuer-mode API return HTTP 200.

- [ ] **Step 4: Verify the settings workflow in a browser**

At desktop and mobile widths, verify the mode list, workbook import summary, mode-driven case reload, disabled-case reason, no overlapping text, and a clean browser console. Capture screenshots as evidence.

- [ ] **Step 5: Record progress, commit, and push**

```powershell
git add docs/sit-case-progress.md
git commit -m "docs: record raw challenge UI mode coverage"
git push origin codex/sit-sidebar-progress
```

Expected: branch push succeeds and `http://127.0.0.1:8000/` remains available.
