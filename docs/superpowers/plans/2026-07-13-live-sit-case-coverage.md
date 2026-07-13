# Live SIT Case Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the live Browser SIT runner execute the user-approved cases with the correct card, AReq fields, challenge language, cancel action, and resend timing while preserving strict Excel expectations.

**Architecture:** Keep case interpretation in `server.py` and support gating in `sit_runner.py`. Pass explicit challenge headers and resend delay values through the existing AReq/CReq flow; use the existing HTTP client and challenge parser rather than adding a parallel runner.

**Tech Stack:** Python 3.11+, standard-library HTTP client, pytest-style tests, static HTML/JavaScript configuration.

## Global Constraints

- Valid card: `4771048901645588`.
- Invalid card: `4771048901645589`.
- Excel expectations remain strict and authoritative.
- Do not automate ACS Admin state changes.
- Do not run long timeout or OTP-expiry cases.
- Resend wait is 30 seconds where a successful resend is required.

---

### Task 1: Case Payloads And Scope

**Files:**
- Modify: `static/index.html`
- Modify: `tools/run_live_sit.py`
- Modify: `acs_auto_sit/server.py`
- Modify: `acs_auto_sit/sit_runner.py`
- Test: `tests/test_default_areq_payload.py`
- Test: `tests/test_sit_runner_api.py`

**Interfaces:**
- Consumes: Excel-derived case dictionaries and the transaction envelope.
- Produces: `_transaction_for_case(case, transaction)` with card, channel, 3RI, currency, language, and resend-delay overrides.

- [ ] Add failing tests asserting invalid card `4771048901645589`, 3RI fields for `case11`/`case12`, currencies for `case18`-`case21`, and skip reasons for Admin/timeout/expiry cases.
- [ ] Run focused tests and confirm failures identify missing defaults and payload overrides.
- [ ] Implement the smallest case-specific mapping and supported-case changes.
- [ ] Run focused tests and confirm they pass.

### Task 2: Challenge Headers And Cancel

**Files:**
- Modify: `acs_auto_sit/server.py`
- Test: `tests/test_sit_runner_api.py`

**Interfaces:**
- Consumes: `browserLanguage` from the case-mutated AReq payload.
- Produces: challenge form POSTs with `Accept-Language` and the page-discovered cancel field.

- [ ] Add failing tests for the `Accept-Language` header on initial and follow-up challenge POSTs and for cancel control submission.
- [ ] Run focused tests and confirm the expected missing-header or wrong-form failures.
- [ ] Thread a challenge header dictionary through the existing CReq helpers and preserve parsed form controls.
- [ ] Run focused tests and confirm they pass.

### Task 3: Resend Timing

**Files:**
- Modify: `acs_auto_sit/server.py`
- Test: `tests/test_sit_runner_api.py`

**Interfaces:**
- Consumes: `resendDelaySeconds` set by `_transaction_for_case`.
- Produces: a single delayed resend or delayed resend-limit loop, with zero delay for resend-too-early cases.

- [ ] Add failing tests that monkeypatch `time.sleep` and assert delays: 30 seconds for `case35`-`case38`, zero for `case39`-`case42`, and 30 seconds per `case43`-`case46` attempt.
- [ ] Run focused tests and confirm delay assertions fail.
- [ ] Pass the delay through `_run_areq_flow`, `_run_creq_flow`, `_advance_challenge_response`, and `_resend_until_limit` and sleep only immediately before a resend request.
- [ ] Run focused tests and confirm they pass without real waiting.

### Task 4: Regression And Live Verification

**Files:**
- Modify only if a failing regression demonstrates a scoped defect.
- Record: live JSON result artifacts (not source-controlled).

**Interfaces:**
- Consumes: the supplied AReq endpoint and OTP lookup endpoint.
- Produces: strict per-case pass/fail/skip evidence.

- [ ] Run all available automated tests and Python compilation checks.
- [ ] Start or refresh the local server and verify its HTTP health endpoint/page.
- [ ] Rerun the included live cases at a conservative transaction cadence.
- [ ] Summarize passes, strict Excel mismatches, ACS errors, and intentional skips without converting failures into passes.
