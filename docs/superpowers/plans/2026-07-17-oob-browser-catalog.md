# OOB Browser Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep legacy Browser cases OTP-only and return a separate `oob01` through `oob13` catalog whenever the effective preferred challenge is OOB.

**Architecture:** Add an OOB JSON catalog beside the existing OTP catalog. Centralize effective preferred-challenge resolution and catalog-path selection in `sit_runner.py`, then make Browser list, dry-run, and live-run lookups use that same selection so displayed and executable case IDs cannot diverge.

**Tech Stack:** Python 3.13, standard-library JSON/path handling, pytest, existing HTTP server, vanilla JavaScript frontend.

## Global Constraints

- Store the OOB source at `sit_cases/oob_browser_cases.json`.
- Keep `case01` through `case20` OTP-only and do not reinterpret them as OOB cases.
- OOB responses contain only `oob01` through `oob13`; OTP responses contain no `oobNN` IDs.
- Resolve `preferredChallenge=auto` from `issuerMode.defaultPreferredChallenge` before selecting a catalog.
- Missing or invalid OOB data must not fall back to the OTP catalog.
- Reuse existing OOB action execution and transaction-result lookup; do not duplicate transport code.
- Keep timeout, ACS Admin configuration, and currency cases out of this task.
- Preserve unrelated changes in `acs_auto_sit/wording_profiles.py` and `.pytest-tmp/`.

---

### Task 1: Effective Challenge and Catalog Path Selection

**Files:**
- Modify: `acs_auto_sit/sit_runner.py`
- Modify: `tests/test_case_progress.py`

**Interfaces:**
- Produces: `effective_preferred_challenge(issuer_mode: dict[str, Any], preferred_challenge: str) -> str`.
- Produces: `browser_catalog_path(issuer_mode: dict[str, Any], preferred_challenge: str, otp_path: Path = DEFAULT_BROWSER_CASES_PATH, oob_path: Path = DEFAULT_OOB_BROWSER_CASES_PATH) -> Path`.
- Consumes: canonical issuer mode dictionaries from `resolve_issuer_mode()`.

- [ ] **Step 1: Write failing resolver tests**

Add imports and tests to `tests/test_case_progress.py`:

```python
from pathlib import Path

from acs_auto_sit.sit_runner import (
    DEFAULT_OOB_BROWSER_CASES_PATH,
    browser_catalog_path,
    effective_preferred_challenge,
)


@pytest.mark.parametrize(
    ("mode_id", "preferred", "expected"),
    (
        ("direct_oob", "auto", "oob"),
        ("selection_sms_oob", "oob", "oob"),
        ("selection_sms_oob", "auto", "sms"),
        ("selection_sms_email_oob", "email", "email"),
    ),
)
def test_effective_preferred_challenge_resolves_mode_default(mode_id, preferred, expected):
    assert effective_preferred_challenge(resolve_issuer_mode(mode_id), preferred) == expected


def test_oob_effective_challenge_selects_oob_catalog():
    selected = browser_catalog_path(resolve_issuer_mode("selection_sms_oob"), "oob")
    assert selected == DEFAULT_OOB_BROWSER_CASES_PATH


def test_non_oob_effective_challenge_keeps_requested_otp_catalog(tmp_path):
    otp_path = tmp_path / "otp.json"
    selected = browser_catalog_path(
        resolve_issuer_mode("selection_sms_oob"),
        "sms",
        otp_path=otp_path,
    )
    assert selected == otp_path
```

- [ ] **Step 2: Run resolver tests and verify RED**

Run:

```powershell
python -m pytest tests/test_case_progress.py -k "effective_preferred or catalog_path" -q --basetemp .pytest-tmp-oob-plan
```

Expected: collection fails because the constants and functions do not exist.

- [ ] **Step 3: Implement minimal resolver and path selector**

Add beside `DEFAULT_BROWSER_CASES_PATH` in `acs_auto_sit/sit_runner.py`:

```python
DEFAULT_OOB_BROWSER_CASES_PATH = PROJECT_ROOT / "sit_cases" / "oob_browser_cases.json"


def effective_preferred_challenge(
    issuer_mode: dict[str, Any], preferred_challenge: str
) -> str:
    requested = str(preferred_challenge or "auto")
    if requested == "auto":
        return str(issuer_mode.get("defaultPreferredChallenge") or "sms")
    return requested


def browser_catalog_path(
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
    *,
    otp_path: Path = DEFAULT_BROWSER_CASES_PATH,
    oob_path: Path = DEFAULT_OOB_BROWSER_CASES_PATH,
) -> Path:
    if effective_preferred_challenge(issuer_mode, preferred_challenge) == "oob":
        return oob_path
    return otp_path
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_case_progress.py -k "effective_preferred or catalog_path" -q --basetemp .pytest-tmp-oob-plan
```

Expected: 6 parameterized/standalone cases pass.

- [ ] **Step 5: Commit the resolver slice**

```powershell
git add -- acs_auto_sit/sit_runner.py tests/test_case_progress.py
git commit -m "feat: resolve browser catalog challenge"
```

---

### Task 2: OOB Catalog Contract and Loading

**Files:**
- Create: `sit_cases/oob_browser_cases.json`
- Modify: `acs_auto_sit/sit_runner.py`
- Modify: `tests/test_case_progress.py`

**Interfaces:**
- Extends: `load_browser_case_catalog(..., oob_path: Path = DEFAULT_OOB_BROWSER_CASES_PATH)`.
- Produces: an OOB catalog containing exactly `oob01` through `oob13`, each with `challengeType: "oob"`.
- Preserves: explicit `path` arguments as OTP fixture overrides unless `oob_path` is explicitly supplied.

- [ ] **Step 1: Write failing catalog contract tests**

Add to `tests/test_case_progress.py`:

```python
def test_direct_oob_catalog_contains_only_oob_cases():
    catalog = load_browser_case_catalog(
        issuer_mode="direct_oob",
        preferred_challenge="auto",
    )

    assert catalog["caseCount"] == 13
    assert [case["id"] for case in catalog["cases"]] == [
        f"oob{number:02d}" for number in range(1, 14)
    ]
    assert {case["challengeType"] for case in catalog["cases"]} == {"oob"}


def test_selection_oob_and_sms_return_disjoint_catalogs():
    oob = load_browser_case_catalog(
        issuer_mode="selection_sms_oob",
        preferred_challenge="oob",
    )
    sms = load_browser_case_catalog(
        issuer_mode="selection_sms_oob",
        preferred_challenge="sms",
    )

    assert all(case["id"].startswith("oob") for case in oob["cases"])
    assert all(not case["id"].startswith("oob") for case in sms["cases"])
    assert sms["cases"][0]["id"] == "case01"


def test_invalid_oob_catalog_does_not_fall_back_to_otp(tmp_path):
    invalid = tmp_path / "oob.json"
    invalid.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid OOB Browser catalog"):
        load_browser_case_catalog(
            oob_path=invalid,
            issuer_mode="direct_oob",
            preferred_challenge="oob",
        )
```

- [ ] **Step 2: Run contract tests and verify RED**

Run:

```powershell
python -m pytest tests/test_case_progress.py -k "oob_catalog or disjoint_catalogs" -q --basetemp .pytest-tmp-oob-catalog
```

Expected: tests fail because `oob_path` and the OOB source file do not exist.

- [ ] **Step 3: Create the 13-case OOB source**

Create `sit_cases/oob_browser_cases.json` with top-level keys `sourceWorkbook`, `sheet`, `caseCount`, and `cases`. Each case must include the same summary fields consumed by `_case_summary()`, plus `challengeType`, `flow`, and explicit automation metadata. Use this scenario mapping:

```json
{
  "oob01": "OOB challenge successful / CAVV verification",
  "oob02": "OOB user cancellation",
  "oob03": "OOB user rejection",
  "oob04": "PA valid card",
  "oob05": "PA invalid card",
  "oob06": "NPA valid card",
  "oob07": "NPA invalid card",
  "oob08": "3RI valid card",
  "oob09": "3RI invalid card",
  "oob10": "OOB transaction interruption",
  "oob11": "English PA OOB authentication page",
  "oob12": "English PA OOB uncompleted page",
  "oob13": "English NPA OOB authentication and uncompleted page"
}
```

Use `flow: {"kind": "direct", "destination": "oob"}` for challenge-page cases. Mark cases that the current runner cannot mutate deterministically as `automation.status: "planned"`; do not claim live support merely because they are visible. Set protocol expectations explicitly under `expected.messages` and include `browserLanguage: "en-US"` only for `oob11` through `oob13`.

- [ ] **Step 4: Select and validate the catalog in the loader**

Extend `load_browser_case_catalog()` with keyword-only `oob_path`, resolve the mode once, and select the path before reading JSON:

```python
resolved_issuer_mode = resolve_issuer_mode(issuer_mode)
selected_path = browser_catalog_path(
    resolved_issuer_mode,
    preferred_challenge,
    otp_path=path,
    oob_path=oob_path,
)
catalog_kind = "OOB" if selected_path == oob_path else "OTP"
try:
    data = json.loads(selected_path.read_text(encoding="utf-8"))
except FileNotFoundError as exc:
    raise ValueError(f"{catalog_kind} Browser catalog was not found: {selected_path}") from exc
except json.JSONDecodeError as exc:
    raise ValueError(f"Invalid {catalog_kind} Browser catalog JSON: {exc.msg}") from exc
```

For OOB, validate `caseCount == 13`, exact IDs, unique IDs, and `challengeType == "oob"`. Add `challengeType` and `flow` to `_case_summary()` so execution metadata survives loading. Do not run wording-profile replacement against the OOB catalog.

- [ ] **Step 5: Run catalog and legacy tests**

Run:

```powershell
python -m pytest tests/test_case_progress.py tests/test_selection_sms_otp_case_plan.py tests/test_direct_otp_case_plan.py -q --basetemp .pytest-tmp-oob-catalog
```

Expected: all tests pass; existing OTP catalog counts remain unchanged.

- [ ] **Step 6: Commit the catalog slice**

```powershell
git add -- sit_cases/oob_browser_cases.json acs_auto_sit/sit_runner.py tests/test_case_progress.py
git commit -m "feat: add separate OOB browser catalog"
```

---

### Task 3: API and Live Lookup Consistency

**Files:**
- Modify: `acs_auto_sit/server.py`
- Modify: `acs_auto_sit/sit_runner.py`
- Modify: `tests/test_sit_runner_api.py`
- Modify: `tests/test_frontend_error_handling.py`

**Interfaces:**
- Extends: `dry_run_cases(..., issuer_mode: str, preferred_challenge: str)`.
- Extends: `browser_cases_by_id(..., oob_path: Path = DEFAULT_OOB_BROWSER_CASES_PATH)`.
- Guarantees: `/api/sit/browser-cases` and `/api/sit/run` resolve the same effective challenge and catalog.

- [ ] **Step 1: Write failing API-switch tests**

Add to `tests/test_sit_runner_api.py`:

```python
@pytest.mark.parametrize(
    ("mode", "preferred", "expected_first"),
    (
        ("direct_oob", "auto", "oob01"),
        ("selection_sms_oob", "oob", "oob01"),
        ("selection_sms_oob", "sms", "case01"),
    ),
)
def test_browser_cases_api_switches_catalog_with_effective_challenge(
    mode, preferred, expected_first
):
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()
    try:
        with request.urlopen(
            f"http://127.0.0.1:{app_server.server_port}/api/sit/browser-cases"
            f"?issuerMode={mode}&preferredChallenge={preferred}",
            timeout=5,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        _stop_server(app_server, app_thread)

    assert result["cases"][0]["id"] == expected_first
```

Add a live lookup test that monkeypatches `_run_areq_flow`, requests `oob01` under direct OOB, and asserts the result is not `"Case ID was not found"`. Add the inverse assertion that `case01` is not found while the same OOB catalog is selected.

- [ ] **Step 2: Run API tests and verify RED**

Run:

```powershell
python -m pytest tests/test_sit_runner_api.py -k "switches_catalog or live_lookup_uses_oob" -q --basetemp .pytest-tmp-oob-api
```

Expected: OOB requests still return the OTP catalog or live lookup cannot find `oob01`.

- [ ] **Step 3: Thread catalog selection through all lookups**

Update `_handle_browser_cases()` and `_handle_sit_run()` to use the same canonical mode/preference pair. Extend `dry_run_cases()` so dry run no longer silently uses the default OTP path:

```python
def dry_run_cases(
    case_ids: list[str],
    *,
    issuer_mode: str = "sms_otp",
    preferred_challenge: str = "auto",
) -> list[dict[str, Any]]:
    catalog = load_browser_case_catalog(
        issuer_mode=issuer_mode,
        preferred_challenge=preferred_challenge,
    )
```

Pass `issuer_mode["id"]` and `preferred_challenge` into dry-run and live `browser_cases_by_id()` calls. Return the resolved effective challenge in catalog responses as `effectivePreferredChallenge` so the frontend and tests can verify what was selected.

- [ ] **Step 4: Preserve frontend reload behavior**

Add assertions to `tests/test_frontend_error_handling.py` that the preferred-challenge change handler awaits `loadBrowserCases()` and clears stale selection/results before rendering the new catalog. If the existing code already meets the contract, no production frontend edit is needed.

- [ ] **Step 5: Run API, frontend, and server suites**

Run:

```powershell
python -m pytest tests/test_sit_runner_api.py tests/test_frontend_error_handling.py tests/test_server.py -q --basetemp .pytest-tmp-oob-api
```

Expected: all tests pass; list, dry-run, and live-run APIs agree on catalog IDs.

- [ ] **Step 6: Commit the API consistency slice**

```powershell
git add -- acs_auto_sit/server.py acs_auto_sit/sit_runner.py tests/test_sit_runner_api.py tests/test_frontend_error_handling.py
git commit -m "feat: switch Browser cases by preferred challenge"
```

---

### Task 4: Progress, Documentation, and Full Verification

**Files:**
- Modify: `data/browser_case_progress.json`
- Modify: `docs/sit-case-progress.md`
- Modify: `AI_PROGRESS.md`
- Test: all files under `tests/`

**Interfaces:**
- Records: independent `oob01` through `oob13` progress without modifying OTP case completion data.
- Documents: selected-catalog behavior and the exact first OOB scope.

- [ ] **Step 1: Add independent OOB progress records**

Add `oob01` through `oob13` to `data/browser_case_progress.json` with empty `completedModes` and note `OOB catalog defined; scenario-specific live automation is pending.` The catalog-selection task does not claim completion of scenario-specific mutation flows. Do not add OOB completion to `case01` through `case20`.

- [ ] **Step 2: Run focused progress tests**

Run:

```powershell
python -m pytest tests/test_case_progress.py tests/test_sit_runner_api.py -q --basetemp .pytest-tmp-oob-final
```

Expected: all focused tests pass and progress summaries use only the selected catalog.

- [ ] **Step 3: Run the complete automated suite**

Run:

```powershell
python -m pytest -q --basetemp .pytest-tmp-oob-final
```

Expected: zero failures and zero errors. Copy the numeric passed-test count printed by pytest into `AI_PROGRESS.md` and `docs/sit-case-progress.md`.

- [ ] **Step 4: Update durable documentation**

Replace the pending OOB-planning note in `docs/sit-case-progress.md` with the implemented behavior: source path, `oob01` through `oob13` scope, effective challenge rules, error behavior, automated test count, and any OOB cases still marked planned.

Update `AI_PROGRESS.md`:

```markdown
## Done

- Added the independent OOB Browser catalog.
- Switched list and run APIs using the effective preferred challenge.
- Verified with the passed-test count printed by the final pytest run.

## Next Step

Task complete. The next OOB automation slice should target only cases still marked planned.
```

- [ ] **Step 5: Verify Git scope**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Expected: only planned files plus pre-existing `acs_auto_sit/wording_profiles.py`, `.pytest-tmp/`, and local AI workflow files appear. Do not delete or stage unrelated paths.

- [ ] **Step 6: Commit verification documentation**

```powershell
git add -- data/browser_case_progress.json docs/sit-case-progress.md
git commit -m "docs: record preferred OOB catalog coverage"
```
