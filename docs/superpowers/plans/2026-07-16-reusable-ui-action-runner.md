# Reusable UI Action Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Excel-generated browser UI cases with reusable, locale-independent actions and stage-specific HTML wording validation.

**Architecture:** Keep the legacy case runner intact and add a generated-case path selected by `flow` metadata. `case_plan.py` produces semantic actions from `flow.kind`, `wordingScenario`, and `destination`; `ui_action_runner.py` executes those actions against challenge pages; `ui_validation.py` validates only the Excel fields assigned to each stage. Catalog capability status comes from whether a complete generated plan can be built, not from legacy `baseCaseId` progress.

**Tech Stack:** Python 3.13, standard-library HTTP/HTML parsing, pytest, existing `acs_auto_sit` modules, vanilla HTML/JavaScript.

## Global Constraints

- Reuse one action plan across locales; locale may change only `browserLanguage` and expected stage fields.
- Do not route pending generated cases through legacy `baseCaseId` support.
- Preserve legacy case behavior and response compatibility.
- Treat Excel placeholders `{0}` through `{4}` as non-empty runtime wildcards.
- Ignore script and style contents during user-visible wording validation.
- Slow expiration cases are skipped unless `includeSlowCases=true`.
- `otpExpiryWaitSeconds` is configurable and must be positive when slow cases are enabled.
- Use TDD for every behavior change and commit each completed slice independently.
- Preserve unrelated uncommitted changes in `acs_auto_sit/challenge.py` and `tests/test_challenge_parser.py`; incorporate them without reverting them.

---

### Task 1: Generated Action Registry

**Files:**
- Modify: `acs_auto_sit/case_plan.py`
- Modify: `tests/test_selection_sms_otp_case_plan.py`

**Interfaces:**
- Consumes: generated cases containing `flow.kind`, `flow.destination`, `flow.stages`, and `wordingScenario`.
- Produces: `build_case_plan(case, issuer_mode) -> dict` with `coverage`, `classification`, `preferredChallenge`, `autoSelectAuthenticationMode`, and ordered `actions`.

- [ ] **Step 1: Write parameterized failing tests for locale-independent plans**

Add a helper and parameterized cases to `tests/test_selection_sms_otp_case_plan.py`:

```python
def _generated_case(locale, scenario, destination="sms", kind="selection_branch"):
    return {
        "id": f"ui_{destination}_{scenario}_{locale}",
        "browserLanguage": locale.replace("_", "-"),
        "wordingScenario": scenario,
        "expected": {
            "stageUiFields": {
                "single_select": {"challenge_title": f"select-{locale}"},
                destination: {"challenge_title": f"challenge-{locale}"},
            }
        },
        "flow": {
            "kind": kind,
            "destination": destination,
            "stages": [{"type": "single_select"}, {"type": destination}],
        },
    }


@pytest.mark.parametrize(
    ("scenario", "expected_types"),
    (
        ("initial_challenge", ["send_areq", "assert_authentication_mode_page", "assert_stage_ui", "choose_authentication_mode", "assert_otp_page", "assert_stage_ui"]),
        ("incorrect_otp", ["send_areq", "assert_authentication_mode_page", "assert_stage_ui", "choose_authentication_mode", "assert_otp_page", "submit_otp", "assert_stage_ui"]),
        ("resend_success", ["send_areq", "assert_authentication_mode_page", "assert_stage_ui", "choose_authentication_mode", "assert_otp_page", "resend_otp", "assert_stage_ui"]),
        ("resend_gap_limit", ["send_areq", "assert_authentication_mode_page", "assert_stage_ui", "choose_authentication_mode", "assert_otp_page", "resend_otp", "assert_stage_ui"]),
        ("resend_count_limit", ["send_areq", "assert_authentication_mode_page", "assert_stage_ui", "choose_authentication_mode", "assert_otp_page", "resend_until_limit", "assert_stage_ui"]),
        ("expired_otp", ["send_areq", "assert_authentication_mode_page", "assert_stage_ui", "choose_authentication_mode", "assert_otp_page", "wait_otp_expiry", "submit_otp", "assert_stage_ui"]),
    ),
)
def test_generated_action_registry_maps_scenario_to_reusable_actions(scenario, expected_types):
    plan = build_case_plan(
        _generated_case("en_US", scenario),
        resolve_issuer_mode("selection_sms_email_oob"),
    )

    assert plan["coverage"] == "implemented"
    assert plan["classification"] == "generated"
    assert [action["type"] for action in plan["actions"]] == expected_types


def test_generated_action_plan_does_not_change_with_locale():
    english = build_case_plan(_generated_case("en_US", "incorrect_otp"), resolve_issuer_mode("selection_sms_email_oob"))
    chinese = build_case_plan(_generated_case("zh_CN", "incorrect_otp"), resolve_issuer_mode("selection_sms_email_oob"))

    assert english["actions"] == chinese["actions"]
```

Add tests for `selection_page`, Email (`challengeValue="2"`), OOB (`challengeValue="3"`), and an unknown scenario returning `coverage="pending"` with no mutation actions.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest tests/test_selection_sms_otp_case_plan.py -q
```

Expected: failures because generated scenarios currently reuse `build_direct_otp_case_plan()` and report every flow as implemented.

- [ ] **Step 3: Implement the semantic registry in `case_plan.py`**

Add explicit scenario constants and builders:

```python
GENERATED_SCENARIOS = {
    "initial_challenge",
    "incorrect_otp",
    "resend_success",
    "resend_gap_limit",
    "resend_count_limit",
    "expired_otp",
}


def _generated_destination_actions(destination: str, scenario: str) -> list[dict[str, Any]] | None:
    if destination == "oob":
        if scenario != "initial_challenge":
            return None
        return [
            {"type": "assert_oob_page"},
            {"type": "assert_stage_ui", "stage": "oob"},
        ]

    actions: list[dict[str, Any]] = [
        {"type": "assert_otp_page"},
    ]
    if scenario == "incorrect_otp":
        actions.append({"type": "submit_otp", "otpPurpose": "failure"})
    elif scenario == "resend_success":
        actions.append({"type": "resend_otp", "delayMode": "configured"})
    elif scenario == "resend_gap_limit":
        actions.append({"type": "resend_otp", "delaySeconds": 0})
    elif scenario == "resend_count_limit":
        actions.append({"type": "resend_until_limit"})
    elif scenario == "expired_otp":
        actions.extend([
            {"type": "wait_otp_expiry"},
            {"type": "submit_otp", "otpPurpose": "expired"},
        ])
    elif scenario != "initial_challenge":
        return None
    actions.append({"type": "assert_stage_ui", "stage": destination})
    return actions
```

Implement `_build_generated_case_plan()` so `selection_page` stops after asserting `single_select`, `selection_branch` prepends selection actions, `direct` runs destination actions directly, and `oob_switch_sms` produces OOB assertion, switch, SMS assertion actions. Return `coverage="pending"` and a concrete `pendingReason` for unsupported combinations.

- [ ] **Step 4: Run focused plan tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_selection_sms_otp_case_plan.py tests/test_direct_otp_case_plan.py -q
```

Expected: all plan tests pass; legacy plan assertions remain unchanged.

- [ ] **Step 5: Commit the registry slice**

```powershell
git add -- acs_auto_sit/case_plan.py tests/test_selection_sms_otp_case_plan.py
git commit -m "feat: add generated UI action registry"
```

---

### Task 2: Capability-Based Catalog and Skip Status

**Files:**
- Modify: `acs_auto_sit/sit_runner.py`
- Modify: `acs_auto_sit/case_progress.py`
- Modify: `tests/test_case_progress.py`
- Modify: `tests/test_sit_runner_api.py`
- Modify: `tests/test_wording_profiles.py`

**Interfaces:**
- Consumes: generated action plans from Task 1.
- Produces: generated `caseImplementation` based on plan capability and `live_skip_reason(case, issuer_mode=None)` that cannot bypass pending status through `baseCaseId`.

- [ ] **Step 1: Write failing capability and skip tests**

Add tests asserting:

```python
def test_generated_case_progress_comes_from_action_capability():
    case = _generated_case_with_flow_and_scenario("incorrect_otp")
    implementation = generated_case_implementation(case, resolve_issuer_mode("selection_sms_email_oob"))
    assert implementation["status"] == "completed"
    assert implementation["actionCount"] > 0
    assert implementation["actions"][0]["type"] == "send_areq"


def test_pending_generated_case_is_skipped_before_base_case_fallback():
    case = {
        "id": "ui_unknown",
        "baseCaseId": "case23",
        "wordingScenario": "unknown",
        "flow": {"kind": "selection_branch", "destination": "sms", "stages": []},
        "automation": {"status": "manual_or_slow"},
        "availability": {"enabled": True, "reason": ""},
    }
    reason = live_skip_reason(case, resolve_issuer_mode("selection_sms_email_oob"))
    assert "not implemented" in reason.lower()
```

Update the browser catalog fixture assertion so generated cases with complete registry plans report `completed`, while unknown combinations report `pending`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m pytest tests/test_case_progress.py tests/test_wording_profiles.py tests/test_sit_runner_api.py::test_live_runner_skips_unsupported_cases_even_when_action_plan_exists -q
```

Expected: generated cases remain pending from the progress file and supported `baseCaseId` bypasses their own capability.

- [ ] **Step 3: Implement generated capability status**

Add to `case_progress.py`:

```python
def generated_case_implementation(case: dict[str, Any], issuer_mode: dict[str, Any]) -> dict[str, Any]:
    plan = build_case_plan(case, issuer_mode)
    actions = list(plan.get("actions") or [])
    availability = case.get("availability") or {}
    if availability.get("enabled") is False:
        return {
            "caseId": case.get("id", ""),
            "status": "unavailable",
            "completedModes": [],
            "pendingModes": [],
            "note": str(availability.get("reason") or "Required UI wording is unavailable."),
            "actionCount": 0,
            "actions": [],
        }
    completed = plan.get("coverage") == "implemented" and bool(actions)
    return {
        "caseId": case.get("id", ""),
        "status": "completed" if completed else "pending",
        "completedModes": [issuer_mode["id"]] if completed else [],
        "pendingModes": [] if completed else [issuer_mode["id"]],
        "note": "" if completed else str(plan.get("pendingReason") or "Generated UI flow is not implemented."),
        "actionCount": len(actions),
        "actions": actions,
    }
```

In `load_browser_case_catalog()`, replace progress data only for cases containing `flow` and `wording`; leave legacy progress unchanged. Change `live_skip_reason` to accept the resolved issuer mode and check generated plan coverage before any `baseCaseId` lookup.

- [ ] **Step 4: Add structured skip classification in `_run_live_sit_cases`**

For generated pending cases, return:

```python
{
    "caseId": case_id,
    "status": "skipped",
    "classification": "not_implemented",
    "reason": skip_reason,
    "case": case,
    "details": {
        "expected": case.get("expected", {}),
        "issuerMode": issuer_mode,
        "casePlan": case_plan,
        "caseAreq": case_areq,
    },
}
```

Legacy skipped results retain their existing status and gain only a compatible `classification` field.

- [ ] **Step 5: Run capability tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_case_progress.py tests/test_wording_profiles.py tests/test_sit_runner_api.py -q
```

Expected: all tests pass and no pending generated case invokes `_run_areq_flow`.

- [ ] **Step 6: Commit the capability slice**

```powershell
git add -- acs_auto_sit/case_progress.py acs_auto_sit/sit_runner.py acs_auto_sit/server.py tests/test_case_progress.py tests/test_wording_profiles.py tests/test_sit_runner_api.py
git commit -m "feat: derive generated case capability status"
```

---

### Task 3: Stage-Aware UI Validation

**Files:**
- Create: `acs_auto_sit/ui_validation.py`
- Modify: `acs_auto_sit/challenge.py`
- Modify: `acs_auto_sit/server.py`
- Create: `tests/test_ui_validation.py`
- Modify: `tests/test_challenge_parser.py`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces: `validate_stage_fields(stage: str, fields: dict[str, Any], page: dict[str, Any] | None) -> list[dict[str, Any]]` and `stage_page(action_results, stage) -> dict | None`.
- Preserves: `_excel_field_results()` as a compatibility wrapper for legacy tests.

- [ ] **Step 1: Write failing parser and matcher tests**

Create `tests/test_ui_validation.py` with:

```python
from acs_auto_sit.ui_validation import validate_stage_fields


def test_stage_validation_matches_runtime_placeholders_and_visible_attributes():
    page = {
        "visibleText": [
            "Verification code was resent via Email to user@example.test",
            "Submit",
            "Need help",
        ]
    }
    fields = {
        "challenge_message": "Verification code was resent via Email to your email address {0}",
        "submit_button": "Submit",
        "help_label": "Need help",
    }
    results = validate_stage_fields("email", fields, page)
    assert [item["status"] for item in results] == ["matched", "matched", "matched"]
    assert {item["stage"] for item in results} == {"email"}


def test_stage_validation_does_not_match_script_or_style_content():
    page = {"visibleText": ["Visible title"]}
    results = validate_stage_fields("sms", {"challenge_message": "hidden-script-copy"}, page)
    assert results[0]["status"] == "missing"
```

Extend `tests/test_challenge_parser.py` with HTML containing `<style>hidden-style-copy</style>` and `<script>hidden-script-copy</script>`, asserting neither value appears in `visibleText`. Preserve and extend the current uncommitted visible-attribute test.

- [ ] **Step 2: Run validation tests and verify RED**

Run:

```powershell
python -m pytest tests/test_ui_validation.py tests/test_challenge_parser.py -q
```

Expected: `ui_validation` does not exist and parser includes script/style data.

- [ ] **Step 3: Implement `ui_validation.py`**

Implement normalized matching without locale-specific logic:

```python
def validate_stage_fields(stage, fields, page):
    visible_items = (page or {}).get("visibleText") or []
    visible = " ".join(_normalize_text(item) for item in visible_items)
    results = []
    for name, raw_value in fields.items():
        expected = str(raw_value or "").strip()
        if not expected:
            continue
        normalized = _normalize_text(visible_text_from_html(expected))
        matched = bool(normalized) and _placeholder_pattern(normalized).search(visible) is not None
        results.append({
            "name": str(name),
            "stage": stage,
            "expected": expected,
            "status": "matched" if matched else "missing",
            "found": matched,
        })
    return results
```

Build `_placeholder_pattern()` with escaped static tokens joined by `\s+` and `{0}` through `{4}` mapped to `.+?`. Require non-empty wildcard matches.

- [ ] **Step 4: Exclude non-visible parser containers**

Track ignored depth for `script`, `style`, `template`, and `noscript` in `ChallengeHtmlParser`. `handle_data()` must return without appending while ignored depth is non-zero. Keep visible attribute collection for inputs, buttons, and generic elements.

- [ ] **Step 5: Add server compatibility wrappers**

Change `_excel_field_results()` to delegate to `validate_stage_fields("combined", fields, {"visibleText": visible_text})` and strip only the new `stage`/`status` keys from the legacy return shape. Generated action results use the complete shape.

- [ ] **Step 6: Run validation and existing prompt tests**

Run:

```powershell
python -m pytest tests/test_ui_validation.py tests/test_challenge_parser.py tests/test_sit_runner_api.py -q
```

Expected: all tests pass, including existing HTML normalization and placeholder tests.

- [ ] **Step 7: Commit the validation slice**

```powershell
git add -- acs_auto_sit/ui_validation.py acs_auto_sit/challenge.py acs_auto_sit/server.py tests/test_ui_validation.py tests/test_challenge_parser.py tests/test_sit_runner_api.py
git commit -m "feat: validate Excel wording by challenge stage"
```

---

### Task 4: Generated Selection and OTP Action Executor

**Files:**
- Create: `acs_auto_sit/ui_action_runner.py`
- Modify: `acs_auto_sit/server.py`
- Create: `tests/test_ui_action_runner.py`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces: `execute_generated_actions(context: ActionContext, actions: list[dict[str, Any]]) -> dict[str, Any]`.
- Consumes callbacks supplied by `server.py` for form submission, OTP lookup, sleep, and notification, avoiding a circular import.
- Produces test helper: `action_context_factory(pages: list[dict[str, Any]]) -> tuple[ActionContext, list[dict[str, str]], list[float]]` for later action slices.

- [ ] **Step 1: Write failing selection and OTP executor tests**

Create fake challenge pages and callbacks, then assert:

```python
def test_selection_sms_incorrect_otp_executes_actions_in_order():
    result = execute_generated_actions(context, actions)
    assert [item["type"] for item in result["actionResults"]] == [
        "assert_authentication_mode_page",
        "assert_stage_ui",
        "choose_authentication_mode",
        "assert_otp_page",
        "submit_otp",
        "assert_stage_ui",
    ]
    assert submitted_forms == [
        {"challengeValue": "1"},
        {"challengeValue": "000000"},
    ]
    assert result["classification"] == "passed"
```

Add tests that selection branches fail with `classification="assertion_failed"` if ACS returns OTP directly, selection-page-only plans do not mutate the form, and Email uses value `2` with the same executor.

- [ ] **Step 2: Run executor tests and verify RED**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py -q
```

Expected: module and executor are missing.

- [ ] **Step 3: Implement executor context and ordered action loop**

Define:

```python
@dataclass
class ActionContext:
    page: dict[str, Any] | None
    stage_fields: dict[str, dict[str, Any]]
    submit_form: Callable[[dict[str, Any], dict[str, str]], dict[str, Any]]
    resolve_otp: Callable[[str, dict[str, Any]], tuple[str, dict[str, Any]]]
    sleep: Callable[[float], None]
    expiry_wait_seconds: float = 0
    resend_max_attempts: int = 10
```

The executor skips the plan-level `send_areq`, keeps `current_page`, appends one structured result per action, and stops immediately after a failed assertion or missing required form. Implement page assertions, stage assertions, authentication selection, and OTP submission. Preserve the ACS-generated success OTP retry by allowing the server callback to perform the existing lookup/retry policy.

- [ ] **Step 4: Integrate generated plans into `_run_areq_flow`**

Pass `generatedActions` and `stageUiFields` in the SIT transaction envelope. Extend `_post_creq` with keyword-only parameters `generated_actions: list[dict[str, Any]] | None = None` and `stage_ui_fields: dict[str, dict[str, Any]] | None = None`. `_run_areq_flow` passes `list(envelope.get("generatedActions") or [])` and `dict(envelope.get("stageUiFields") or {})`; keep the existing procedural `_post_creq` path when `generated_actions` is empty.

Return generated evidence under:

```python
autoCreq["actionResults"]
autoCreq["classification"]
autoCreq["failedAction"]
```

- [ ] **Step 5: Add generated result mapping**

Add `_generated_ui_result()` in `server.py`. It maps executor classification to top-level status:

```python
status_by_classification = {
    "passed": "pass",
    "assertion_failed": "fail",
    "acs_error": "fail",
    "not_implemented": "skipped",
    "skipped_slow": "skipped",
}
```

Include field results in the primary comparison and ordered action evidence in `details.challengeFlow`.

- [ ] **Step 6: Run generated selection/OTP and legacy suites**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py tests/test_sit_runner_api.py tests/test_server.py -q
```

Expected: generated selection/OTP tests pass and legacy runner tests remain green.

- [ ] **Step 7: Commit the executor slice**

```powershell
git add -- acs_auto_sit/ui_action_runner.py acs_auto_sit/server.py tests/test_ui_action_runner.py tests/test_sit_runner_api.py
git commit -m "feat: execute generated selection and OTP actions"
```

---

### Task 5: Reusable Resend Actions

**Files:**
- Modify: `acs_auto_sit/ui_action_runner.py`
- Modify: `acs_auto_sit/server.py`
- Modify: `tests/test_ui_action_runner.py`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Extends executor actions: `resend_otp` and `resend_until_limit`.

- [ ] **Step 1: Write failing resend scenario tests**

Cover three outcomes with the same locale-independent actions:

```python
@pytest.mark.parametrize(
    ("scenario", "expected_forms", "expected_sleeps"),
    (
        ("resend_success", 1, [30]),
        ("resend_gap_limit", 1, []),
        ("resend_count_limit", 3, [30, 30, 30]),
    ),
)
def test_generated_resend_actions(scenario, expected_forms, expected_sleeps, action_context_factory):
    actions = build_case_plan(
        _generated_case("en_US", scenario),
        resolve_issuer_mode("selection_sms_email_oob"),
    )["actions"]
    pages = _resend_pages_for_scenario(scenario)
    context, submitted_forms, sleeps = action_context_factory(pages)

    result = execute_generated_actions(context, actions)

    resend_forms = [form for form in submitted_forms if form.get("resendCode") == "Y"]
    assert len(resend_forms) == expected_forms
    assert sleeps == expected_sleeps
    assert result["classification"] == "passed"
    assert result["actionResults"][-1]["type"] == "assert_stage_ui"
    assert result["actionResults"][-1]["stage"] == "sms"
```

Assert that the final `assert_stage_ui` reads the page returned by the resend action, not the initial OTP page.

- [ ] **Step 2: Run resend tests and verify RED**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py -k resend -q
```

Expected: executor reports unsupported actions.

- [ ] **Step 3: Implement resend actions**

Use the existing form override logic through callbacks. `resend_otp` sleeps only when its action requests configured delay. `resend_until_limit` records every submission, stops when resend disappears or a final CRes arrives, and fails if the safety maximum is reached while resend remains available.

- [ ] **Step 4: Integrate configurable resend values**

Populate generated context from existing transaction fields `resendDelaySeconds` and `resendMaxAttempts`. Keep legacy `_resend_until_limit()` unchanged.

- [ ] **Step 5: Run resend and full executor tests**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py tests/test_sit_runner_api.py -q
```

Expected: all generated and legacy resend tests pass.

- [ ] **Step 6: Commit the resend slice**

```powershell
git add -- acs_auto_sit/ui_action_runner.py acs_auto_sit/server.py tests/test_ui_action_runner.py tests/test_sit_runner_api.py
git commit -m "feat: reuse resend actions across UI locales"
```

---

### Task 6: OOB and OOB-to-SMS Actions

**Files:**
- Modify: `acs_auto_sit/ui_action_runner.py`
- Modify: `acs_auto_sit/case_plan.py`
- Modify: `tests/test_ui_action_runner.py`
- Modify: `tests/test_selection_sms_otp_case_plan.py`

**Interfaces:**
- Extends actions: `assert_oob_page`, `continue_oob`, and `switch_to_otp`.

- [ ] **Step 1: Write failing OOB action tests**

Add tests for direct OOB, selection-to-OOB, and OOB-to-SMS:

```python
def test_oob_switch_sms_reuses_sms_stage_actions():
    result = execute_generated_actions(context, actions)
    assert submitted_forms == [{"isForceOTP": "true"}, {"challengeValue": "654321"}]
    assert [item.get("stage") for item in result["actionResults"] if item["type"] == "assert_stage_ui"] == ["oob", "sms"]
```

Also assert that unexpected OTP on an OOB assertion fails before submitting any form.

- [ ] **Step 2: Run OOB tests and verify RED**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py -k oob -q
```

Expected: OOB actions are unsupported or do not update the current page correctly.

- [ ] **Step 3: Implement OOB actions**

`assert_oob_page` requires `page.type == "oob"`. `continue_oob` uses `oobContinue=Y`. `switch_to_otp` uses the parsed switch control, requires the returned page to be OTP, and then continues through the existing SMS actions. Record every page transition in action results.

- [ ] **Step 4: Run OOB, executor, and plan tests**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py tests/test_selection_sms_otp_case_plan.py tests/test_challenge_parser.py -q
```

Expected: all OOB variants pass.

- [ ] **Step 5: Commit the OOB slice**

```powershell
git add -- acs_auto_sit/ui_action_runner.py acs_auto_sit/case_plan.py tests/test_ui_action_runner.py tests/test_selection_sms_otp_case_plan.py
git commit -m "feat: add reusable OOB UI actions"
```

---

### Task 7: Configurable Slow Expiration Cases

**Files:**
- Modify: `acs_auto_sit/server.py`
- Modify: `acs_auto_sit/ui_action_runner.py`
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `tests/test_ui_action_runner.py`
- Modify: `tests/test_sit_runner_api.py`
- Modify: `tests/test_frontend_error_handling.py`

**Interfaces:**
- SIT request fields: `includeSlowCases: bool = false`, `otpExpiryWaitSeconds: float > 0`.

- [ ] **Step 1: Write failing default-skip and enabled-wait tests**

Add API-level tests:

```python
def test_generated_expired_otp_is_skipped_by_default(monkeypatch, tmp_path):
    result = _run_generated_expired_case(transaction={}, monkeypatch=monkeypatch, tmp_path=tmp_path)
    assert result["status"] == "skipped"
    assert result["classification"] == "skipped_slow"
    assert not network_calls


def test_generated_expired_otp_waits_when_slow_cases_enabled(monkeypatch, tmp_path):
    sleeps = []
    transaction = {"includeSlowCases": True, "otpExpiryWaitSeconds": 120}
    result = _run_generated_expired_case(transaction, monkeypatch, tmp_path, sleeps=sleeps)
    assert sleeps == [120]
    assert result["status"] == "pass"
```

Add validation tests for zero, negative, and non-numeric waits when `includeSlowCases=true`.

- [ ] **Step 2: Run slow-case tests and verify RED**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py tests/test_sit_runner_api.py -k 'slow or expired' -q
```

Expected: expired cases follow the old exclusion rule and request options are ignored.

- [ ] **Step 3: Implement request parsing and slow skip**

Add:

```python
def _read_slow_case_settings(transaction):
    include = bool(transaction.get("includeSlowCases", False))
    raw_wait = transaction.get("otpExpiryWaitSeconds", 300)
    try:
        wait_seconds = float(raw_wait)
    except (TypeError, ValueError) as exc:
        raise ValueError("otpExpiryWaitSeconds must be a positive number.") from exc
    if include and wait_seconds <= 0:
        raise ValueError("otpExpiryWaitSeconds must be a positive number.")
    return include, wait_seconds
```

Before network execution, generated plans containing `wait_otp_expiry` return `skipped_slow` unless enabled. When enabled, pass the configured wait into `ActionContext`; tests inject the sleep callback.

- [ ] **Step 4: Add frontend controls**

Add an unchecked `includeSlowCases` checkbox and numeric `otpExpiryWaitSeconds` input defaulting to `300`. Include both values in `readCommonEnvelope()`. Disable the wait input while slow cases are unchecked.

- [ ] **Step 5: Run backend and frontend tests**

Run:

```powershell
python -m pytest tests/test_ui_action_runner.py tests/test_sit_runner_api.py tests/test_frontend_error_handling.py -q
```

Expected: all tests pass; normal full runs skip expiration without network calls.

- [ ] **Step 6: Commit the slow-case slice**

```powershell
git add -- acs_auto_sit/server.py acs_auto_sit/ui_action_runner.py static/index.html static/app.js tests/test_ui_action_runner.py tests/test_sit_runner_api.py tests/test_frontend_error_handling.py
git commit -m "feat: make OTP expiration runs configurable"
```

---

### Task 8: Full Catalog Verification and Documentation

**Files:**
- Modify: `docs/sit-case-progress.md`
- Modify: `data/browser_case_progress.json` only if legacy progress needs correction; generated cases must not be enumerated.
- Test: all `tests/` files.

**Interfaces:**
- Verifies all generated catalog cases have a deterministic capability, plan, and default run outcome.

- [ ] **Step 1: Add a catalog contract test**

Add to `tests/test_wording_profiles.py`:

```python
def test_all_raw_generated_cases_have_deterministic_action_capability(tmp_path):
    catalog = load_browser_case_catalog(
        wording_profiles_path=_write_complete_raw_profile(tmp_path),
        issuer_mode="selection_sms_email_oob",
    )
    generated = [case for case in catalog["cases"] if case.get("wording")]
    assert generated
    assert all(case["caseImplementation"]["status"] == "completed" for case in generated)
    assert all(case["caseImplementation"]["actionCount"] > 0 for case in generated)
```

For incomplete workbook fixtures, assert `unavailable` rather than `completed`.

- [ ] **Step 2: Run the complete automated suite**

Use a workspace-local base temp to avoid the known Windows temp permission issue:

```powershell
python -m pytest -q --basetemp .pytest-tmp-ui-actions
```

Expected: all tests pass with zero failures or errors.

- [ ] **Step 3: Run default live catalog verification**

Start/restart the local server, run all cases with the configured test AReq URL and card, `selection_sms_email_oob`, `includeSlowCases=false`, and a non-zero case delay. Save only a sanitized summary. Verify:

- expiration cases are `skipped_slow` without external calls;
- no case is `not_implemented` for a complete imported workbook;
- ACS transient failures are classified separately from UI assertion failures;
- selection, SMS, Email, and OOB action evidence names the correct stages.

- [ ] **Step 4: Review live assertion failures**

For each `assertion_failed`, compare `details.actionResults[*].fieldResults` with the captured stage HTML. Classify it as matcher defect, wrong action/page, workbook expectation mismatch, or ACS configuration mismatch. Fix matcher/action defects with a new RED/GREEN test before repeating only the affected cases.

- [ ] **Step 5: Update progress documentation**

Document the registry-supported flows, capability-derived generated status, slow-case request fields, automated test count, and sanitized live-run summary in `docs/sit-case-progress.md`.

- [ ] **Step 6: Remove test artifacts and verify Git scope**

Resolve `.pytest-tmp-ui-actions` under the workspace before recursively deleting it. Confirm `git status --short` contains only intended documentation changes plus any pre-existing unrelated changes.

- [ ] **Step 7: Commit verification documentation**

```powershell
git add -- docs/sit-case-progress.md
git commit -m "docs: record reusable UI action coverage"
```
