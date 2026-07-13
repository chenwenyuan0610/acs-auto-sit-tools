# SIT Result Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present each SIT case's description and steps before a readable expected-versus-actual comparison, with mismatches highlighted in red.

**Architecture:** Keep the existing API unchanged. Build a normalized actual-result view and difference list in `static/app.js`, render them into semantic HTML in `static/index.html`, and use responsive flat sections in `static/styles.css`.

**Tech Stack:** Vanilla HTML, CSS, JavaScript, Python static-asset tests.

## Global Constraints

- Excel-imported expected results remain authoritative.
- Red indicates only mismatches or execution errors; skipped cases remain neutral.
- Full raw execution details remain available below the comparison.
- The local server remains fixed at `http://127.0.0.1:8000/`.

---

### Task 1: Detail Layout

**Files:**
- Modify: `static/index.html`
- Modify: `static/styles.css`
- Modify: `static/app.js`
- Test: `tests/test_frontend_error_handling.py`

- [ ] Add failing assertions for description fields, ordered steps, expected and actual outputs, and DOM order.
- [ ] Replace the textarea detail layout with description, steps, comparison, differences, and collapsible raw details.
- [ ] Populate the new elements when a case is selected.
- [ ] Run focused frontend tests.

### Task 2: Actual Results And Differences

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_frontend_error_handling.py`

- [ ] Add failing assertions for actual-result extraction and red difference rendering.
- [ ] Normalize ARes, CRes, notification, prompt, error, transaction, and resend-limit output.
- [ ] Render mismatch reasons and field-level differences in red without injecting untrusted HTML.
- [ ] Run the complete test suite and verify desktop/mobile rendering.
