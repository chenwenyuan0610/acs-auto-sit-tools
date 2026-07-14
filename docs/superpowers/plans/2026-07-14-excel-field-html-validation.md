# Excel Field HTML Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate every imported Excel wording field against challenge HTML, send the generated locale in AReq, and keep full HTML only in collapsed technical details.

**Architecture:** Generated wording cases carry an explicit `excel_fields` validation mode. The runner compares each `expected.uiFields` value with normalized visible challenge text and returns compact field results, while parsed challenge pages retain `rawHtml` for the existing collapsed raw-result section. The frontend renders field-level expected and actual summaries instead of full protocol objects.

**Tech Stack:** Python 3 standard library, pytest, vanilla JavaScript, HTML, CSS.

## Global Constraints

- Every non-empty Excel wording field is required.
- HTML tags, entities, repeated whitespace, and numbered placeholders do not cause false mismatches.
- Legacy fixed-case prompt matching remains unchanged.
- `zh_TW`, `en_US`, and `zh_CN` map to `zh-TW`, `en-US`, and `zh-CN` in AReq.
- Full challenge HTML is shown only in collapsed technical details.

---

### Task 1: Generated Case Validation Contract

**Files:**
- Modify: `acs_auto_sit/wording_profiles.py`
- Test: `tests/test_wording_profiles.py`

**Interfaces:**
- Produces: `case["expected"]["validationMode"] == "excel_fields"` on generated workbook cases.

- [ ] **Step 1: Write failing tests** asserting normalized and raw workbook cases include `validationMode: excel_fields` and preserve all `uiFields` values.
- [ ] **Step 2: Run** `python -m pytest tests/test_wording_profiles.py -q` and confirm the new assertions fail.
- [ ] **Step 3: Add the validation mode** in both generated-case builders without changing legacy source cases.
- [ ] **Step 4: Re-run** `python -m pytest tests/test_wording_profiles.py -q` and confirm it passes.

### Task 2: Strict Excel Field Matching and HTML Retention

**Files:**
- Modify: `acs_auto_sit/challenge.py`
- Modify: `acs_auto_sit/server.py`
- Test: `tests/test_challenge_parser.py`
- Test: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces: parsed challenge `rawHtml: str`.
- Produces: `details.prompt.fields`, a list of `{name, expected, found}` records.

- [ ] **Step 1: Write failing tests** for raw HTML retention, tags/entities/whitespace/placeholders, Merchant and Help fields being required, missing-field reporting, and locale propagation into AReq.
- [ ] **Step 2: Run the focused tests** and verify failures are caused by the missing behavior.
- [ ] **Step 3: Implement strict matching** for `excel_fields` while retaining `_missing_prompt_text` for legacy cases.
- [ ] **Step 4: Include field records** in prompt details and keep original expected text for red difference output.
- [ ] **Step 5: Re-run focused tests** and confirm they pass.

### Task 3: Compact Result UI

**Files:**
- Modify: `static/app.js`
- Modify: `static/index.html`
- Modify: `static/styles.css`
- Test: `tests/test_frontend_error_handling.py`

**Interfaces:**
- Consumes: `details.prompt.fields` and parsed `rawHtml` in the raw result.
- Produces: compact expected/actual field summaries and collapsed `技術細節`.

- [ ] **Step 1: Write failing frontend source tests** asserting compact field-summary functions exist, `rawHtml` is excluded from the main summary, and the technical details element remains collapsed by default.
- [ ] **Step 2: Run the frontend tests** and confirm they fail.
- [ ] **Step 3: Render important information only** in the main comparison: field name, expected wording, and found/missing state.
- [ ] **Step 4: Keep raw execution output** under the closed `details` element labeled `技術細節`.
- [ ] **Step 5: Run frontend tests** and confirm they pass.

### Task 4: Verification and Progress

**Files:**
- Modify: `docs/sit-case-progress.md`

**Interfaces:**
- Produces: documented validation behavior and verification evidence.

- [ ] **Step 1: Run** `python -m pytest -q` and require a clean full-suite pass.
- [ ] **Step 2: Start the app on port 8000** after stopping the existing listener, then verify the API and result page.
- [ ] **Step 3: Check desktop and mobile layouts** for overflow, readable field summaries, red missing text, and collapsed technical details.
- [ ] **Step 4: Update progress documentation** with behavior and test counts.
- [ ] **Step 5: Commit and push** the completed implementation to `codex/sit-sidebar-progress`.
