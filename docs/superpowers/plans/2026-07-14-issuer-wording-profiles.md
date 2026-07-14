# Issuer Wording Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import issuer challenge wording from Excel and dynamically expose localized, executable case23+ UI scenarios.

**Architecture:** A focused `wording_profiles` module parses and persists normalized workbook data. The SIT catalog expands seven scenario templates from the active issuer profile, while the server and frontend pass the selected issuer through catalog loading and live execution.

**Tech Stack:** Python 3.12, `openpyxl`, `http.server`, vanilla JavaScript, pytest.

## Global Constraints

- Default locales are exactly `zh_TW`, `en_US`, and `zh_CN`.
- Missing wording cases remain visible but disabled.
- Imported profiles persist as JSON across service restarts.
- The source case JSON is not rewritten during import.
- Existing case01 through case22 behavior remains unchanged.

---

### Task 1: Parse and persist wording profiles

**Files:**
- Create: `acs_auto_sit/wording_profiles.py`
- Create: `tests/test_wording_profiles.py`

**Interfaces:**
- Produces: `import_wording_workbook(content: bytes, destination: Path) -> dict[str, Any]`
- Produces: `load_wording_profiles(path: Path = DEFAULT_WORDING_PROFILES_PATH) -> dict[str, Any] | None`

- [ ] **Step 1: Write failing parser tests** for required sheets, the three default locales, normalized wording keys, duplicate rejection, and atomic persistence.
- [ ] **Step 2: Run `python -m pytest tests/test_wording_profiles.py`** and verify failures are caused by the missing module.
- [ ] **Step 3: Implement workbook validation and normalization** using `openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)` and write JSON through a same-directory temporary file followed by `Path.replace`.
- [ ] **Step 4: Run `python -m pytest tests/test_wording_profiles.py`** and verify all parser tests pass.

### Task 2: Generate issuer-aware localized cases

**Files:**
- Modify: `acs_auto_sit/wording_profiles.py`
- Modify: `acs_auto_sit/sit_runner.py`
- Modify: `tests/test_wording_profiles.py`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces: `wording_profile_catalog(profiles, issuer_id) -> dict[str, Any]`
- Changes: `load_browser_case_catalog(..., issuer_id: str = "")`
- Changes: `browser_cases_by_id(..., issuer_id: str = "")`

- [ ] **Step 1: Write failing generation tests** proving seven templates expand to 21 available cases for the default three locales, carry field-level expectations, and disable only missing wording combinations.
- [ ] **Step 2: Run the focused tests** and verify they fail because profile expansion is absent.
- [ ] **Step 3: Implement the seven explicit scenario definitions**, exact issuer/shared fallback, locale metadata, generated IDs, and availability metadata.
- [ ] **Step 4: Integrate generated cases into the catalog** only when a persisted wording profile exists; retain the legacy catalog otherwise.
- [ ] **Step 5: Run `python -m pytest tests/test_wording_profiles.py tests/test_sit_runner_api.py`** and restore green.

### Task 3: Add profile APIs and runtime selection

**Files:**
- Modify: `acs_auto_sit/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Adds: `GET /api/sit/wording-profiles`
- Adds: `POST /api/sit/wording-profiles/import` with `{fileName, contentBase64}`
- Changes: `GET /api/sit/browser-cases?issuerId=<id>`
- Changes: `POST /api/sit/run` to accept `issuerId`

- [ ] **Step 1: Write failing handler and runtime tests** for successful import, invalid workbook HTTP 400, issuer-filtered catalog loading, unknown/disabled case rejection, locale headers, and scenario behavior.
- [ ] **Step 2: Run the focused server tests** and verify the new endpoints are missing.
- [ ] **Step 3: Implement query parsing, import decoding, profile listing, issuer-aware case lookup, and availability checks.**
- [ ] **Step 4: Replace generated-case name parsing** with `locale`, `wordingScenario`, and `baseCaseId` metadata while preserving legacy behavior.
- [ ] **Step 5: Run `python -m pytest tests/test_server.py tests/test_sit_runner_api.py`** and restore green.

### Task 4: Add settings controls and disabled case states

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_error_handling.py`

**Interfaces:**
- Consumes: wording profile list/import APIs and issuer-filtered case catalog.
- Produces: issuer selection, Excel import, import summary, and disabled case checkboxes.

- [ ] **Step 1: Write failing frontend contract tests** for `issuerProfile`, `wordingWorkbook`, `importWordingWorkbook`, import status, base64 upload, issuer query parameter, and disabled selection logic.
- [ ] **Step 2: Run `python -m pytest tests/test_frontend_error_handling.py`** and verify the controls are absent.
- [ ] **Step 3: Add compact settings controls** using a select, file input, icon/text import command, and status region consistent with the existing settings layout.
- [ ] **Step 4: Implement profile loading/import and catalog reload**, pass `issuerId` into live runs, and ensure Select All/Run All ignore disabled cases.
- [ ] **Step 5: Run the frontend contract tests** and restore green.

### Task 5: Verify, document, and restart

**Files:**
- Modify: `docs/sit-case-progress.md`
- Modify: `AI_PROGRESS.md` if present

**Interfaces:**
- Records the workbook import workflow and current coverage.

- [ ] **Step 1: Run `python -m pytest`** and resolve regressions without weakening assertions.
- [ ] **Step 2: Import the bundled workbook through the API** and verify the default issuer exposes three locales per scenario.
- [ ] **Step 3: Inspect the settings and case list at desktop and mobile widths** and verify controls do not overlap and disabled reasons are readable.
- [ ] **Step 4: Update progress documentation** with completed behavior, remaining limitations, and test evidence.
- [ ] **Step 5: Restart the local server on port 8000** and verify `GET /` returns HTTP 200.
