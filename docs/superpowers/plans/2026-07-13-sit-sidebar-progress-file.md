# SIT Sidebar and Case Progress File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate SIT execution and settings with a responsive sidebar, persist case-writing progress in JSON without displaying it in the page, and enlarge the select-all checkbox.

**Architecture:** `acs_auto_sit.case_progress` will load and normalize a repository-owned JSON progress file while preserving the existing catalog API shape. The browser will use an internal tab pattern inside the left case panel, with execution and settings panels sharing the existing controls and request IDs.

**Tech Stack:** Python 3.13, standard-library `json` and `pathlib`, static HTML/CSS/JavaScript, pytest, Playwright with installed Microsoft Edge.

## Global Constraints

- Do not change SIT request field IDs or request payload behavior.
- Do not display case-writing progress or implementation status in the browser.
- `執行案例` is the default left-panel view.
- At widths at or below 980 px, the sidebar becomes a horizontal tab row.
- `#selectAllCases` is exactly 20 by 20 px; `.case-check` remains compact.
- Missing progress files produce pending progress; malformed JSON raises a clear error.
- Do not revert unrelated changes in the dirty worktree.

---

### Task 1: File-Backed Case Progress

**Files:**
- Create: `data/browser_case_progress.json`
- Modify: `acs_auto_sit/case_progress.py`
- Modify: `acs_auto_sit/sit_runner.py`
- Modify: `docs/sit-case-progress.md`
- Modify: `tests/test_case_progress.py`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces: `DEFAULT_CASE_PROGRESS_PATH: Path`
- Produces: `load_case_progress_records(path: Path = DEFAULT_CASE_PROGRESS_PATH) -> dict[str, dict[str, Any]]`
- Produces: `build_browser_case_progress(cases: list[dict[str, Any]], records: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]`
- Changes: `load_browser_case_catalog(path: Path = DEFAULT_BROWSER_CASES_PATH, progress_path: Path = DEFAULT_CASE_PROGRESS_PATH) -> dict[str, Any]`

- [ ] **Step 1: Write failing progress-file tests**

Add tests that create temporary JSON files and assert file-driven normalization:

```python
import json

import pytest

from acs_auto_sit.case_progress import (
    TRACKED_ISSUER_MODES,
    build_browser_case_progress,
    load_case_progress_records,
)


def test_load_case_progress_records_reads_case_modes_and_ignores_unknown_modes(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text(
        json.dumps({
            "version": 1,
            "trackedIssuerModes": TRACKED_ISSUER_MODES,
            "cases": {
                "case01": {
                    "completedModes": ["direct_otp", "not_a_mode"],
                    "note": "direct flow complete",
                }
            },
        }),
        encoding="utf-8",
    )

    records = load_case_progress_records(path)

    assert records == {
        "case01": {
            "completedModes": ["direct_otp"],
            "note": "direct flow complete",
        }
    }


def test_load_case_progress_records_returns_empty_for_missing_file(tmp_path):
    assert load_case_progress_records(tmp_path / "missing.json") == {}


def test_load_case_progress_records_reports_invalid_json(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid case progress JSON"):
        load_case_progress_records(path)


def test_build_browser_case_progress_defaults_missing_cases_to_pending():
    progress = build_browser_case_progress(
        [{"id": "case01"}, {"id": "case02"}],
        {"case01": {"completedModes": ["direct_otp"]}},
    )

    assert progress["cases"][0]["completedModes"] == ["direct_otp"]
    assert progress["cases"][1]["status"] == "pending"
    assert progress["summary"]["directOtpCompleted"] == 1
```

Add a catalog test using a temporary progress file:

```python
def test_browser_case_catalog_uses_progress_file(tmp_path):
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(
        json.dumps({
            "version": 1,
            "trackedIssuerModes": TRACKED_ISSUER_MODES,
            "cases": {"case01": {"completedModes": ["direct_otp"], "note": ""}},
        }),
        encoding="utf-8",
    )

    catalog = load_browser_case_catalog(progress_path=progress_path)

    assert catalog["cases"][0]["caseImplementation"]["directOtp"]["status"] == "completed"
    assert catalog["cases"][0]["caseImplementation"]["selectionSmsOtp"]["status"] == "pending"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\acs-auto-sit-pytest'; python -m pytest tests\test_case_progress.py tests\test_sit_runner_api.py -q
```

Expected: failures because `load_case_progress_records` and `progress_path` do not exist and progress is still inferred from case plans.

- [ ] **Step 3: Implement the JSON loader and record normalization**

Replace plan-derived progress in `case_progress.py` with file-derived records:

```python
import json
from pathlib import Path
from typing import Any


DEFAULT_CASE_PROGRESS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "browser_case_progress.json"
)


def load_case_progress_records(
    path: Path = DEFAULT_CASE_PROGRESS_PATH,
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid case progress JSON in {path}: {error.msg}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), dict):
        raise ValueError(f"Invalid case progress structure in {path}: cases must be an object")

    records: dict[str, dict[str, Any]] = {}
    for case_id, record in payload["cases"].items():
        if not isinstance(case_id, str) or not isinstance(record, dict):
            continue
        completed_modes = [
            mode
            for mode in record.get("completedModes") or []
            if mode in TRACKED_ISSUER_MODES
        ]
        records[case_id] = {
            "completedModes": completed_modes,
            "note": str(record.get("note") or ""),
        }
    return records
```

Build every case from its record, preserving the existing `directOtp` and `selectionSmsOtp` status objects with `actionCount: 0` and `actions: []`. Include the record's normalized `note` on each case progress object. Missing records use an empty completed-mode list. Update `sit_runner.load_browser_case_catalog` to load records from `progress_path` and pass them into `build_browser_case_progress`.

- [ ] **Step 4: Create the initial progress source file**

Create `data/browser_case_progress.json` with `version: 1`, all five tracked modes, and explicit `case01` through `case50` entries. Each current entry records:

```json
{
  "completedModes": ["direct_otp", "selection_sms_otp"],
  "note": ""
}
```

This preserves the current 50/50 direct OTP and 50/50 selection SMS OTP progress while making future updates explicit per case.

Update `docs/sit-case-progress.md` to state that `data/browser_case_progress.json` is the authoritative per-case progress record and that the Markdown file is explanatory history only.

- [ ] **Step 5: Run backend tests and verify GREEN**

Run the Task 1 command again. Expected: all progress and API tests pass.

- [ ] **Step 6: Commit the backend increment**

```powershell
git add data\browser_case_progress.json acs_auto_sit\case_progress.py acs_auto_sit\sit_runner.py docs\sit-case-progress.md tests\test_case_progress.py tests\test_sit_runner_api.py
git commit -m "feat: record SIT case progress in JSON"
```

---

### Task 2: Execution and Settings Sidebar

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_error_handling.py`

**Interfaces:**
- Produces DOM IDs: `caseExecutionPanel`, `caseSettingsPanel`
- Produces selectors: `[data-case-view]`, `.case-sidebar-button`, `.case-control-view`
- Produces: `setCaseControlView(viewId: string) -> void`

- [ ] **Step 1: Write failing frontend structure tests**

Update the SIT control test and add sidebar assertions:

```python
def test_sit_controls_use_execution_and_settings_sidebar():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'data-case-view="caseExecutionPanel"' in index_html
    assert 'data-case-view="caseSettingsPanel"' in index_html
    assert 'id="caseExecutionPanel"' in index_html
    assert 'id="caseSettingsPanel"' in index_html
    assert 'id="caseProgressSummary"' not in index_html
    assert "caseImplementation" not in app_js
    assert "function setCaseControlView" in app_js
    assert ".case-sidebar" in styles
    assert ".case-control-view:not(.active)" in styles


def test_select_all_checkbox_is_larger_than_case_checkboxes():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert "#selectAllCases" in styles
    assert "height: 20px" in styles
    assert "width: 20px" in styles
    assert ".case-check" in styles
```

Remove old assertions that require `caseProgressSummary`, `caseImplementation`, implementation labels, and visible case-writing progress copy.

- [ ] **Step 2: Run frontend tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\acs-auto-sit-pytest'; python -m pytest tests\test_frontend_error_handling.py -q
```

Expected: failures because the sidebar DOM and behavior are absent and progress remains visible.

- [ ] **Step 3: Restructure the left panel HTML**

Inside `.case-panel`, add an internal shell with this semantic structure:

```html
<div class="case-panel-shell">
  <nav class="case-sidebar" role="tablist" aria-label="SIT 控制">
    <button class="case-sidebar-button active" type="button" role="tab"
      aria-selected="true" aria-controls="caseExecutionPanel"
      data-case-view="caseExecutionPanel">執行案例</button>
    <button class="case-sidebar-button" type="button" role="tab"
      aria-selected="false" aria-controls="caseSettingsPanel"
      data-case-view="caseSettingsPanel">設定</button>
  </nav>
  <div class="case-panel-content">
    <section id="caseExecutionPanel" class="case-control-view active" role="tabpanel">
      <div class="toolbar">
        <button id="runSelectedCases" class="primary" type="button">執行選取案例</button>
        <button id="runAllCases" type="button">全部執行</button>
      </div>
      <div class="case-tools">
        <label class="check-label"><input id="selectAllCases" type="checkbox" />全選</label>
        <span id="caseCount" class="case-count">0 個案例</span>
      </div>
      <div id="sitRunSummary" class="progress-box">
        <strong>執行結果</strong><span>尚未執行</span>
      </div>
      <div id="caseList" class="case-list"></div>
    </section>
    <section id="caseSettingsPanel" class="case-control-view" role="tabpanel" hidden>
      <div class="sit-options"></div>
    </section>
  </div>
</div>
```

Move the current `.sit-options` element, including `sitAreqUrl`, `validCardNumber`, `invalidCardNumber`, `otpFailureMaxAttempts`, `caseDelaySeconds`, `issuerMode`, `preferredChallenge`, `otpSourceMode`, `otpLookupUrl`, `successOtp`, and `failureOtp`, intact into `caseSettingsPanel`. Delete the case-writing progress box. Keep `sitRunSummary` in the execution panel.

- [ ] **Step 4: Implement sidebar switching and remove progress rendering**

Add:

```javascript
const caseViewButtons = document.querySelectorAll("[data-case-view]");
const caseViewPanels = document.querySelectorAll(".case-control-view");

function setCaseControlView(viewId) {
  caseViewButtons.forEach((button) => {
    const active = button.dataset.caseView === viewId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  caseViewPanels.forEach((panel) => {
    const active = panel.id === viewId;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

caseViewButtons.forEach((button) => {
  button.addEventListener("click", () => setCaseControlView(button.dataset.caseView));
});
```

Remove `caseProgressSummaryEl`, its `loadSitCases` rendering block, `implementationStatusLabel`, and `.case-implementation` creation from case rows.

- [ ] **Step 5: Add responsive sidebar and checkbox styles**

Use a stable desktop grid and mobile tab row:

```css
.case-panel-shell {
  display: grid;
  gap: 14px;
  grid-template-columns: 104px minmax(0, 1fr);
}

.case-sidebar {
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 12px;
}

.case-sidebar-button {
  border-radius: 6px;
  min-width: 0;
  padding: 0 10px;
  text-align: left;
  width: 100%;
}

.case-sidebar-button.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #ffffff;
}

.case-control-view:not(.active) {
  display: none;
}

#selectAllCases {
  height: 20px;
  min-height: 20px;
  width: 20px;
}
```

Within the existing 980 px media query, switch `.case-panel-shell` to one column and `.case-sidebar` to a horizontal row with a bottom border and no right border. Give each sidebar button equal width without changing font size based on viewport width.

- [ ] **Step 6: Run frontend tests and JavaScript syntax check**

Run:

```powershell
$env:PYTHONPATH='C:\tmp\acs-auto-sit-pytest'; python -m pytest tests\test_frontend_error_handling.py -q
node --check static\app.js
```

Expected: all frontend tests pass and Node reports no syntax errors.

- [ ] **Step 7: Commit the frontend increment**

```powershell
git add static\index.html static\app.js static\styles.css tests\test_frontend_error_handling.py
git commit -m "feat: separate SIT execution and settings"
```

---

### Task 3: End-to-End Verification

**Files:**
- Modify only if verification reveals a defect in Task 1 or Task 2 files.

**Interfaces:**
- Consumes the fixed local URL `http://127.0.0.1:8000/`.

- [ ] **Step 1: Run the complete test suite**

```powershell
$env:PYTHONPATH='C:\tmp\acs-auto-sit-pytest'; python -m pytest -q
git diff --check
```

Expected: all tests pass and `git diff --check` reports no errors.

- [ ] **Step 2: Restart the existing project server on port 8000**

Verify the listener belongs to `python -m acs_auto_sit`, stop only that PID, then restart:

```powershell
Start-Process -FilePath 'python' -ArgumentList '-m','acs_auto_sit','--host','127.0.0.1','--port','8000' -WorkingDirectory 'C:\Users\diegochen\Documents\acs-auto-sit-tools' -WindowStyle Hidden
```

Expected: `http://127.0.0.1:8000/` returns HTTP 200 and port 8000 has one listener.

- [ ] **Step 3: Verify desktop behavior with Edge and Playwright**

At 1440 by 1000, assert:

- `執行案例` is visible by default and `設定` is hidden.
- Clicking `設定` hides execution and shows all settings.
- Clicking `執行案例` restores the case list.
- `#selectAllCases` computes to 20 by 20 px.
- No `caseProgressSummary` or `.case-implementation` exists.
- The page has no horizontal overflow.

- [ ] **Step 4: Verify mobile behavior with Edge and Playwright**

At 390 by 844, assert the same visibility behavior and checkbox dimensions, plus:

- Sidebar buttons are arranged horizontally.
- Buttons and labels do not overlap.
- The document width does not exceed 390 px.

Capture the left panel in both viewports and inspect both images.

- [ ] **Step 5: Record final verification**

Report the test count, HTTP 200 on fixed port 8000, desktop/mobile viewport results, and the progress-file path. Do not claim completion unless all checks succeeded.
