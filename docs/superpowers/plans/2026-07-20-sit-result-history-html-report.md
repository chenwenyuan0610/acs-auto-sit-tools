# SIT Result History and HTML Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first SIT result dashboard that manually saves completed runs as JSON, reopens saved history, downloads standalone HTML reports, and exposes per-case AReq time, transaction result, and click-to-copy `acsTransID`.

**Architecture:** Introduce three focused backend modules: a normalizer for the versioned run model, a filesystem repository for atomic JSON persistence, and a self-contained HTML renderer. Extend the current HTTP handler with save/history/report endpoints, then add a result view to the existing single-page frontend. The current `/api/sit/run` response remains compatible while gaining run context and per-case timing fields.

**Tech Stack:** Python 3 standard library (`pathlib`, `json`, `datetime`, `html`, `urllib.parse`), existing `ThreadingHTTPServer`, vanilla JavaScript, HTML/CSS, pytest.

## Global Constraints

- Save only after the user clicks **Save locally**; never auto-save a completed run.
- Store saved runs as UTF-8 JSON under `data/sit-runs/`; do not add SQLite or another dependency.
- Generate HTML only on **Download HTML report** and make it self-contained with no external assets, scripts, API calls, or local-file dependencies.
- Saving JSON and downloading HTML are separate operations.
- Treat a run as complete when every selected case is in `pass`, `fail`, `skipped`, or `error`; this includes a one-case run.
- Copy only one `acsTransID` at a time by clicking the displayed ID; do not add bulk copy.
- Do not display or persist a wording-profile issuer label in the report header.
- Parse card scheme and Issuer OID from `/auth/{cardScheme}/{version}/{issuerOid}/{routeId}/areq`; unsupported URL shapes yield empty parsed values without failing the run.
- Escape all report content; never execute ACS-returned HTML.
- Preserve existing `/api/sit/run`, manual runner, wording import, and case-detail behavior.

---

## File Structure

- Create `acs_auto_sit/run_results.py`: normalized schema, AReq URL parser, terminal-state validation, summary and transaction normalization.
- Create `acs_auto_sit/run_repository.py`: atomic local JSON save, newest-first list, exact-ID load.
- Create `acs_auto_sit/run_report.py`: safe standalone HTML rendering and deterministic filename creation.
- Modify `acs_auto_sit/server.py`: timestamps, run context, endpoint routing, binary HTML responses, configured runs directory.
- Modify `static/index.html`: result/history view and action controls.
- Modify `static/app.js`: current-run state, renderers, save/history/report/copy interactions.
- Modify `static/styles.css`: responsive summary, result table, history, copy feedback.
- Modify `.gitignore`: ignore `data/sit-runs/` and `.superpowers/` runtime/design artifacts.
- Create `tests/test_run_results.py`, `tests/test_run_repository.py`, `tests/test_run_report.py`.
- Modify `tests/test_sit_runner_api.py`, `tests/test_frontend_error_handling.py`, and `docs/sit-case-progress.md`.

---

### Task 1: Normalize Completed Run Data

**Files:**
- Create: `acs_auto_sit/run_results.py`
- Create: `tests/test_run_results.py`

**Interfaces:**
- Produces: `parse_areq_route(url: str) -> dict[str, str]`
- Produces: `acs_trans_id_for_result(result: dict[str, Any]) -> str`
- Produces: `normalize_completed_run(payload: dict[str, Any]) -> dict[str, Any]`
- Produces: `TERMINAL_STATUSES = {"pass", "fail", "skipped", "error"}`
- Consumed by: repository, HTML renderer, and HTTP handlers in later tasks.

- [ ] **Step 1: Write failing parser and normalization tests**

```python
from acs_auto_sit.run_results import normalize_completed_run, parse_areq_route


def test_parse_areq_route_extracts_card_scheme_and_issuer_oid():
    parsed = parse_areq_route(
        "https://acs.example/acs-auth-v3/auth/V/220/"
        "eff82784-e641-8477-3b5b-f14c2ed2ee10/123/areq"
    )
    assert parsed == {
        "cardScheme": "V",
        "issuerOid": "eff82784-e641-8477-3b5b-f14c2ed2ee10",
    }


def test_parse_areq_route_returns_empty_values_for_unknown_shape():
    assert parse_areq_route("https://acs.example/not-an-areq") == {
        "cardScheme": "",
        "issuerOid": "",
    }


def test_normalize_completed_single_case_run():
    normalized = normalize_completed_run({
        "runId": "20260720T001530000Z-a1b2c3d4",
        "startedAt": "2026-07-20T00:15:30.000+08:00",
        "finishedAt": "2026-07-20T00:15:32.614+08:00",
        "execution": {
            "issuerMode": "default_oob_can_switch_otp",
            "effectivePreferredChallenge": "otp",
            "wordingLocale": "zh_TW",
            "areqUrl": "https://acs.example/auth/V/220/eff82784-e641-8477-3b5b-f14c2ed2ee10/123/areq",
            "selectedCaseIds": ["case01"],
        },
        "results": [{
            "caseId": "case01",
            "status": "pass",
            "areqSentAt": "2026-07-20T00:15:30.214+08:00",
            "finishedAt": "2026-07-20T00:15:32.614+08:00",
            "durationMs": 2400,
            "details": {
                "ares": {"acsTransID": "acs-1"},
                "transactionResult": {
                    "actual": {"transStatus": "Y", "eci": "02", "cavv": "value"},
                    "mismatches": {},
                    "lookup": {"ok": True},
                },
            },
        }],
    })
    assert normalized["schemaVersion"] == 1
    assert normalized["execution"]["cardScheme"] == "V"
    assert normalized["execution"]["issuerOid"].startswith("eff82784")
    assert normalized["summary"] == {
        "total": 1, "completed": 1, "pass": 1, "fail": 0, "skipped": 0, "error": 0
    }
    assert normalized["results"][0]["acsTransID"] == "acs-1"
    assert normalized["results"][0]["transactionResult"] == {
        "lookupStatus": "succeeded",
        "transStatus": "Y",
        "eci": "02",
        "cavvPresent": True,
        "validationStatus": "pass",
        "raw": {"transStatus": "Y", "eci": "02", "cavv": "value"},
    }
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_run_results.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-results-red"
```

Expected: FAIL during import because `acs_auto_sit.run_results` does not exist.

- [ ] **Step 3: Implement the normalized model**

```python
# acs_auto_sit/run_results.py
from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

TERMINAL_STATUSES = {"pass", "fail", "skipped", "error"}


def parse_areq_route(url: str) -> dict[str, str]:
    parts = [part for part in urlsplit(str(url or "")).path.split("/") if part]
    try:
        auth_index = parts.index("auth")
    except ValueError:
        return {"cardScheme": "", "issuerOid": ""}
    tail = parts[auth_index + 1:]
    if len(tail) < 5 or tail[-1].lower() != "areq":
        return {"cardScheme": "", "issuerOid": ""}
    return {"cardScheme": tail[0], "issuerOid": tail[2]}


def acs_trans_id_for_result(result: dict[str, Any]) -> str:
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    transactions = details.get("transactions") if isinstance(details.get("transactions"), list) else []
    candidates: list[Any] = [
        (details.get("ares") or {}).get("acsTransID"),
        (details.get("cres") or {}).get("acsTransID"),
        ((details.get("notification") or {}).get("notification") or {}).get("cres", {}).get("acsTransID"),
        (details.get("notification") or {}).get("cres", {}).get("acsTransID"),
    ]
    for transaction in transactions:
        if isinstance(transaction, dict):
            candidates.extend([
                (transaction.get("ares") or {}).get("acsTransID"),
                (transaction.get("cres") or {}).get("acsTransID"),
            ])
    return next((str(value).strip() for value in candidates if str(value or "").strip()), "")


def _normalize_transaction_result(details: dict[str, Any]) -> dict[str, Any]:
    source = details.get("transactionResult") if isinstance(details.get("transactionResult"), dict) else {}
    actual = source.get("actual") if isinstance(source.get("actual"), dict) else {}
    lookup = source.get("lookup") if isinstance(source.get("lookup"), dict) else {}
    if not source:
        lookup_status = "not_requested"
    elif source.get("error") or lookup.get("error") or lookup.get("ok") is False:
        lookup_status = "failed"
    else:
        lookup_status = "succeeded"
    mismatches = source.get("mismatches") if isinstance(source.get("mismatches"), dict) else {}
    return {
        "lookupStatus": lookup_status,
        "transStatus": str(actual.get("transStatus") or ""),
        "eci": str(actual.get("eci") or ""),
        "cavvPresent": actual.get("cavv") not in (None, "", "null"),
        "validationStatus": "fail" if mismatches else ("pass" if actual else "not_checked"),
        "raw": deepcopy(actual),
    }


def normalize_completed_run(payload: dict[str, Any]) -> dict[str, Any]:
    execution = deepcopy(payload.get("execution") or {})
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    selected = execution.get("selectedCaseIds") if isinstance(execution.get("selectedCaseIds"), list) else []
    if not selected:
        raise ValueError("A completed run requires at least one selected case.")
    if len(results) != len(selected) or any(item.get("status") not in TERMINAL_STATUSES for item in results):
        raise ValueError("All selected cases must have terminal results before saving or reporting.")
    execution.update(parse_areq_route(str(execution.get("areqUrl") or "")))
    normalized_results = []
    for item in results:
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        normalized_results.append({
            **deepcopy(item),
            "acsTransID": acs_trans_id_for_result(item),
            "transactionResult": _normalize_transaction_result(details),
        })
    summary = {"total": len(results), "completed": len(results), "pass": 0, "fail": 0, "skipped": 0, "error": 0}
    for item in normalized_results:
        summary[item["status"]] += 1
    return {
        "schemaVersion": 1,
        "runId": str(payload.get("runId") or "").strip(),
        "startedAt": str(payload.get("startedAt") or ""),
        "finishedAt": str(payload.get("finishedAt") or ""),
        "execution": execution,
        "summary": summary,
        "results": normalized_results,
    }
```

- [ ] **Step 4: Add validation tests for empty, incomplete, and multi-case runs**

```python
import pytest


@pytest.mark.parametrize("selected,results,message", [
    ([], [], "at least one selected case"),
    (["case01"], [{"caseId": "case01", "status": "running"}], "terminal results"),
])
def test_normalize_completed_run_rejects_invalid_completion(selected, results, message):
    with pytest.raises(ValueError, match=message):
        normalize_completed_run({
            "runId": "run-1",
            "execution": {"selectedCaseIds": selected, "areqUrl": ""},
            "results": results,
        })
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
python -m pytest tests/test_run_results.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-results-green"
```

Expected: all `tests/test_run_results.py` tests PASS.

```powershell
git add acs_auto_sit/run_results.py tests/test_run_results.py
git commit -m "feat: normalize completed SIT runs"
```

---

### Task 2: Record Run and Per-Case Timing

**Files:**
- Modify: `acs_auto_sit/server.py:280-340,548-830`
- Modify: `static/app.js:1010-1060`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Produces in `/api/sit/run`: `runId`, `startedAt`, `finishedAt`, `execution`, and per-result `areqSentAt`, `finishedAt`, `durationMs`.
- Consumed by: `normalize_completed_run()` and the frontend current-run state.

- [ ] **Step 1: Write failing API timing tests**

```python
def test_live_result_records_areq_sent_time_and_duration(monkeypatch):
    times = iter([100.000, 100.214, 102.614])
    monkeypatch.setattr(server_module.time, "time", lambda: next(times))
    monkeypatch.setattr(server_module, "_run_live_sit_case", lambda *args, **kwargs: {
        "caseId": "case01", "status": "pass", "details": {"ares": {"acsTransID": "acs-1"}}
    })
    results = server_module._run_live_sit_cases(
        ["case01"], {"url": "https://acs.example/auth/V/220/issuer/123/areq", "payload": {}},
        "http://127.0.0.1/notification", server_module.resolve_issuer_mode("sms_otp"), "auto"
    )
    assert results[0]["areqSentAt"]
    assert results[0]["finishedAt"]
    assert results[0]["durationMs"] == 2400
```

Also extend the `/api/sit/run` integration test to assert:

```python
assert result["runId"]
assert result["startedAt"]
assert result["finishedAt"]
assert result["execution"]["issuerMode"] == "sms_otp"
assert result["execution"]["wordingLocale"] == "zh_TW"
assert result["execution"]["selectedCaseIds"] == ["case01"]
```

- [ ] **Step 2: Run the focused tests and verify the new fields are absent**

Run:

```powershell
python -m pytest tests/test_sit_runner_api.py -k "timing or sit_run_api" -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-timing-red"
```

Expected: FAIL on missing timing and execution-context keys.

- [ ] **Step 3: Add timestamps around each live case and the entire request**

Use a single formatter so all timestamps are timezone-aware ISO 8601:

```python
def _iso_timestamp(epoch_seconds: float | None = None) -> str:
    value = time.time() if epoch_seconds is None else epoch_seconds
    return datetime.fromtimestamp(value, timezone.utc).astimezone().isoformat(timespec="milliseconds")
```

Inside `_run_live_sit_cases`, wrap the existing per-case call without changing its business logic:

```python
case_started_epoch = time.time()
result = _run_live_sit_case(...)
case_finished_epoch = time.time()
result["areqSentAt"] = _iso_timestamp(case_started_epoch)
result["finishedAt"] = _iso_timestamp(case_finished_epoch)
result["durationMs"] = max(0, round((case_finished_epoch - case_started_epoch) * 1000))
```

In `_handle_sit_run`, read `runId`, `startedAt`, and `wordingLocale` from the request with safe defaults, record `finishedAt`, and return:

```python
"runId": run_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:8]}",
"startedAt": started_at or _iso_timestamp(),
"finishedAt": _iso_timestamp(),
"execution": {
    "issuerMode": issuer_mode["id"],
    "effectivePreferredChallenge": (
        issuer_mode.get("defaultPreferredChallenge") if preferred_challenge == "auto" else preferred_challenge
    ),
    "wordingLocale": wording_locale,
    "areqUrl": str(transaction.get("url") or ""),
    "selectedCaseIds": list(case_ids),
},
```

- [ ] **Step 4: Send client-generated run identity and context**

At the beginning of `runSitCases(caseIds)`:

```javascript
const startedAt = new Date().toISOString();
const runId = `${startedAt.replaceAll(/[-:.]/g, "")}-${crypto.randomUUID().slice(0, 8)}`;
```

Add these request keys:

```javascript
runId,
startedAt,
wordingLocale: wordingLocaleInput?.value || "all",
```

Store the successful response in a new `currentSitRun` variable.

- [ ] **Step 5: Run timing tests and commit**

Run:

```powershell
python -m pytest tests/test_sit_runner_api.py -k "timing or sit_run_api" -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-timing-green"
```

Expected: focused tests PASS.

```powershell
git add acs_auto_sit/server.py static/app.js tests/test_sit_runner_api.py
git commit -m "feat: record SIT run timing context"
```

---

### Task 3: Persist Saved Runs Atomically

**Files:**
- Create: `acs_auto_sit/run_repository.py`
- Create: `tests/test_run_repository.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: normalized run dictionaries from `normalize_completed_run()`.
- Produces: `RunRepository(root: Path)`, `.save(run)`, `.list()`, and `.load(run_id)`.

- [ ] **Step 1: Write failing repository tests**

```python
import json
import pytest
from acs_auto_sit.run_repository import RunRepository


def _run(run_id="run-1", started_at="2026-07-20T00:15:30+08:00"):
    return {
        "schemaVersion": 1, "runId": run_id, "startedAt": started_at,
        "finishedAt": started_at,
        "execution": {"cardScheme": "V", "issuerMode": "sms_otp"},
        "summary": {"total": 1, "pass": 1}, "results": [],
    }


def test_repository_saves_updates_and_lists_newest_first(tmp_path):
    repository = RunRepository(tmp_path)
    repository.save(_run("older", "2026-07-19T00:00:00+08:00"))
    repository.save(_run("newer", "2026-07-20T00:00:00+08:00"))
    repository.save({**_run("newer", "2026-07-20T00:00:00+08:00"), "summary": {"total": 1, "pass": 0}})
    assert [item["runId"] for item in repository.list()] == ["newer", "older"]
    assert repository.load("newer")["summary"]["pass"] == 0


def test_repository_rejects_path_like_run_id(tmp_path):
    with pytest.raises(ValueError, match="Invalid runId"):
        RunRepository(tmp_path).load("../secret")
```

- [ ] **Step 2: Run tests and verify import failure**

Run:

```powershell
python -m pytest tests/test_run_repository.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-repository-red"
```

Expected: FAIL because `run_repository.py` does not exist.

- [ ] **Step 3: Implement safe atomic persistence**

```python
# acs_auto_sit/run_repository.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class RunRepository:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(str(run_id or "")):
            raise ValueError("Invalid runId.")
        return self.root / f"{run_id}.json"

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        path = self._path(str(run.get("runId") or ""))
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return run

    def load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.is_file():
            raise FileNotFoundError(run_id)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schemaVersion") != 1:
            raise ValueError(f"Unsupported saved run: {run_id}")
        return value

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        items = []
        for path in self.root.glob("*.json"):
            try:
                run = self.load(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            items.append({
                "runId": run["runId"], "startedAt": run.get("startedAt", ""),
                "finishedAt": run.get("finishedAt", ""),
                "execution": run.get("execution", {}), "summary": run.get("summary", {}),
            })
        return sorted(items, key=lambda item: item.get("startedAt", ""), reverse=True)
```

- [ ] **Step 4: Ignore runtime artifacts**

Append exactly:

```gitignore
data/sit-runs/
.superpowers/
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
python -m pytest tests/test_run_repository.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-repository-green"
```

Expected: repository tests PASS.

```powershell
git add .gitignore acs_auto_sit/run_repository.py tests/test_run_repository.py
git commit -m "feat: persist local SIT run history"
```

---

### Task 4: Render Standalone HTML Reports

**Files:**
- Create: `acs_auto_sit/run_report.py`
- Create: `tests/test_run_report.py`

**Interfaces:**
- Consumes: normalized completed-run dictionary.
- Produces: `html_report_filename(run) -> str` and `render_html_report(run) -> bytes`.

- [ ] **Step 1: Write failing escaping and offline-report tests**

```python
from acs_auto_sit.run_report import html_report_filename, render_html_report


def test_render_html_report_is_self_contained_and_escaped():
    run = {
        "runId": "run-1", "startedAt": "2026-07-20T00:15:30+08:00",
        "finishedAt": "2026-07-20T00:16:00+08:00",
        "execution": {
            "cardScheme": "V", "issuerOid": "issuer-1", "issuerMode": "sms_otp",
            "effectivePreferredChallenge": "sms", "wordingLocale": "zh_TW",
            "selectedCaseIds": ["case01"],
        },
        "summary": {"total": 1, "completed": 1, "pass": 0, "fail": 1, "skipped": 0, "error": 0},
        "results": [{
            "caseId": "case01", "status": "fail", "reason": "<script>alert(1)</script>",
            "areqSentAt": "2026-07-20T00:15:30.214+08:00", "durationMs": 2400,
            "acsTransID": "acs-1", "transactionResult": {
                "lookupStatus": "succeeded", "transStatus": "N", "eci": "",
                "cavvPresent": False, "validationStatus": "fail", "raw": {},
            }, "details": {},
        }],
    }
    report = render_html_report(run).decode("utf-8")
    assert "<!doctype html>" in report.lower()
    assert "Issuer OID" in report and "issuer-1" in report
    assert "acs-1" in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "<script>alert(1)</script>" not in report
    assert "https://" not in report and "<script" not in report.lower()
    assert html_report_filename(run) == "sit-report-V-case01-20260720-001530.html"
```

- [ ] **Step 2: Run test and verify import failure**

Run:

```powershell
python -m pytest tests/test_run_report.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-report-red"
```

Expected: FAIL because `run_report.py` does not exist.

- [ ] **Step 3: Implement deterministic safe HTML output**

Implement `run_report.py` using only `html.escape`, `json.dumps`, and `datetime.fromisoformat`. Required rendering rules:

```python
def html_report_filename(run: dict[str, Any]) -> str:
    execution = run.get("execution") or {}
    case_ids = execution.get("selectedCaseIds") or []
    scope = case_ids[0] if len(case_ids) == 1 else f"{len(case_ids)}-cases"
    scheme = re.sub(r"[^A-Za-z0-9_-]+", "-", str(execution.get("cardScheme") or "unknown"))
    started = datetime.fromisoformat(str(run["startedAt"]).replace("Z", "+00:00"))
    return f"sit-report-{scheme}-{scope}-{started:%Y%m%d-%H%M%S}.html"
```

The renderer must build a complete document with embedded CSS, a run-context definition list, summary table, case table, and one native `<details>` block per case. Use one helper for every dynamic value:

```python
def _text(value: Any) -> str:
    return escape(str(value if value not in (None, "") else "—"), quote=True)
```

Return `document.encode("utf-8")` and include no `<script>`, `src=`, `href=http`, `fetch`, or external font declaration.

- [ ] **Step 4: Add multi-case filename and Unicode tests**

```python
def test_multi_case_filename_and_unicode_are_stable():
    run = _valid_run()
    run["execution"]["selectedCaseIds"] = ["case01", "case02"]
    run["results"][0]["reason"] = "驗證失敗"
    assert "2-cases" in html_report_filename(run)
    assert "驗證失敗" in render_html_report(run).decode("utf-8")
```

- [ ] **Step 5: Run tests and commit**

Run:

```powershell
python -m pytest tests/test_run_report.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-report-green"
```

Expected: report tests PASS.

```powershell
git add acs_auto_sit/run_report.py tests/test_run_report.py
git commit -m "feat: render standalone SIT HTML reports"
```

---

### Task 5: Expose Save, History, and Report APIs

**Files:**
- Modify: `acs_auto_sit/server.py:60-115,280-405`
- Modify: `tests/test_sit_runner_api.py`

**Interfaces:**
- Consumes: `normalize_completed_run`, `RunRepository`, `render_html_report`, `html_report_filename`.
- Produces: `POST /api/sit/runs`, `GET /api/sit/runs`, `GET /api/sit/runs/{runId}`, `POST /api/sit/reports/html`, `GET /api/sit/runs/{runId}/report.html`.

- [ ] **Step 1: Write failing end-to-end API tests**

Create a server with `runs_path=tmp_path / "runs"`, post a completed one-case payload, and assert:

```python
saved = post_json(f"http://127.0.0.1:{port}/api/sit/runs", completed_run)
assert saved["ok"] is True
assert saved["run"]["runId"] == completed_run["runId"]

history = get_json(f"http://127.0.0.1:{port}/api/sit/runs")
assert history["runs"][0]["runId"] == completed_run["runId"]

loaded = get_json(f"http://127.0.0.1:{port}/api/sit/runs/{completed_run['runId']}")
assert loaded["run"]["results"][0]["acsTransID"] == "acs-1"
```

Request both HTML endpoints and assert status `200`, `Content-Type: text/html; charset=utf-8`, a filename-bearing `Content-Disposition`, and escaped content. Add `400` tests for incomplete and empty runs plus `404` and traversal tests for unknown/invalid run IDs.

- [ ] **Step 2: Run focused tests and verify endpoint failures**

Run:

```powershell
python -m pytest tests/test_sit_runner_api.py -k "saved_run or html_report or run_history" -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-api-red"
```

Expected: new endpoints return `404`.

- [ ] **Step 3: Configure the repository and routes**

Extend `create_server`:

```python
def create_server(host: str, port: int, *, wording_profiles_path: Path | None = None,
                  runs_path: Path | None = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), AcsAutoSitHandler)
    server.wording_profiles_path = wording_profiles_path
    server.runs_path = runs_path or (PROJECT_ROOT / "data" / "sit-runs")
    return server
```

Add handler helpers:

```python
def _run_repository(self) -> RunRepository:
    return RunRepository(Path(getattr(self.server, "runs_path")))

def _html_response(self, data: bytes, filename: str) -> None:
    self.send_response(HTTPStatus.OK)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    self.send_header("Content-Length", str(len(data)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(data)
```

Route exact paths before generic static handling. Parse saved-run paths with a compiled regex or exact segment count; never translate a `runId` into a caller-provided path.

- [ ] **Step 4: Implement endpoint handlers**

Use these exact data transformations:

```python
def _handle_save_sit_run(self) -> None:
    run = normalize_completed_run(self._read_json_body())
    self._run_repository().save(run)
    self._json_response({"ok": True, "run": run})

def _handle_current_html_report(self) -> None:
    run = normalize_completed_run(self._read_json_body())
    self._html_response(render_html_report(run), html_report_filename(run))
```

Saved report handlers load through the repository and render the loaded normalized model. Convert `FileNotFoundError` to `404`; let normalization `ValueError` use the existing `400` response path.

- [ ] **Step 5: Run API and full backend tests, then commit**

Run:

```powershell
python -m pytest tests/test_run_results.py tests/test_run_repository.py tests/test_run_report.py tests/test_sit_runner_api.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-api-green"
```

Expected: all selected tests PASS.

```powershell
git add acs_auto_sit/server.py tests/test_sit_runner_api.py
git commit -m "feat: add SIT result history APIs"
```

---

### Task 6: Build the Current Result and History UI

**Files:**
- Modify: `static/index.html:180-330`
- Modify: `static/app.js:1-1200`
- Modify: `static/styles.css`
- Modify: `tests/test_frontend_error_handling.py`

**Interfaces:**
- Consumes: run response and APIs from Tasks 2 and 5.
- Produces: `currentSitRun`, `renderSitRunDashboard(run)`, `loadSavedRuns()`, `saveCurrentRun()`, `downloadRunReport(runId?)`, and `copyAcsTransId(value, element)`.

- [ ] **Step 1: Write failing frontend contract tests**

```python
def test_result_dashboard_has_context_actions_history_and_no_bulk_copy():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    for element_id in (
        'id="sitRunContext"', 'id="sitRunMetrics"', 'id="sitResultRows"',
        'id="saveSitRun"', 'id="downloadSitReport"', 'id="savedSitRuns"',
    ):
        assert element_id in index_html
    assert "copyAllAcsTransIds" not in index_html
    assert "function copyAcsTransId" in app_js
    assert 'navigator.clipboard.writeText(value)' in app_js
    assert 'postApi("/api/sit/runs"' in app_js
    assert 'getApi("/api/sit/runs")' in app_js
    assert '"/api/sit/reports/html"' in app_js
```

- [ ] **Step 2: Run the frontend test and verify missing elements**

Run:

```powershell
python -m pytest tests/test_frontend_error_handling.py -k "result_dashboard" -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-ui-red"
```

Expected: FAIL on missing result-dashboard elements.

- [ ] **Step 3: Add semantic result and history markup**

Add a `caseResultsPanel` tab/view next to the existing execution/settings views. Its essential structure is:

```html
<section id="caseResultsPanel" class="case-control-view" role="tabpanel" hidden>
  <div id="sitRunContext" class="run-context"></div>
  <div id="sitRunMetrics" class="run-metrics" aria-label="Run summary"></div>
  <div class="toolbar">
    <button id="saveSitRun" type="button" disabled>儲存到本機</button>
    <button id="downloadSitReport" type="button" disabled>下載 HTML 報告</button>
  </div>
  <p id="sitResultActionStatus" role="status"></p>
  <div class="table-responsive">
    <table class="result-table">
      <thead><tr><th>案例</th><th>狀態</th><th>AReq 發送時間</th><th>acsTransID</th><th>交易結果</th><th>耗時</th></tr></thead>
      <tbody id="sitResultRows"></tbody>
    </table>
  </div>
  <section><h3>已儲存紀錄</h3><div id="savedSitRuns"></div></section>
</section>
```

- [ ] **Step 4: Render current-run context, metrics, rows, and direct copy**

Use `textContent` for every server value. Do not interpolate case data into `innerHTML`. The copy control must be a button whose visible text may be shortened but whose clipboard value is complete:

```javascript
async function copyAcsTransId(value, button) {
  try {
    await navigator.clipboard.writeText(value);
    sitResultActionStatusEl.textContent = `已複製 ${value}`;
  } catch (error) {
    sitResultActionStatusEl.textContent = `無法自動複製，請選取 ID：${value}`;
    button.focus();
  }
}
```

`renderSitRunDashboard(run)` must show issuer mode label, effective preferred challenge, wording locale, card scheme, Issuer OID, timestamps, selected count, existing summary counts, and per-case transaction summary. It enables both actions only when `run.results.length === run.execution.selectedCaseIds.length` and every status is terminal.

- [ ] **Step 5: Add save, history, reopen, and binary HTML download behavior**

Use a binary-download helper instead of `postApi`, because the response is HTML:

```javascript
async function downloadHtml(path, body, fallbackName) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const matched = disposition.match(/filename="([^"]+)"/);
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = matched?.[1] || fallbackName;
  link.click();
  URL.revokeObjectURL(link.href);
}
```

Wire actions exactly:

```javascript
saveSitRunButton.addEventListener("click", async () => {
  await postApi("/api/sit/runs", currentSitRun);
  await loadSavedRuns();
});

downloadSitReportButton.addEventListener("click", () =>
  downloadHtml("/api/sit/reports/html", currentSitRun, "sit-report.html")
);
```

Each history item opens `GET /api/sit/runs/{encodeURIComponent(runId)}` and rerenders it. Its download button uses `/api/sit/runs/{runId}/report.html`.

- [ ] **Step 6: Add responsive styles**

Add a wrapping context row, four-to-six equal metric tiles, a horizontally contained result table below narrow widths, compact history rows, and existing theme variables. Requirements:

```css
.run-context { display: flex; flex-wrap: wrap; gap: .75rem 1.25rem; }
.run-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); gap: .75rem; }
.result-table { width: 100%; border-collapse: collapse; }
.result-table th, .result-table td { padding: .65rem; border-bottom: 1px solid var(--border); text-align: left; }
.acs-trans-id-copy { font-family: ui-monospace, monospace; }
@media (max-width: 720px) { .table-responsive { overflow-x: auto; } }
```

- [ ] **Step 7: Run frontend tests and commit**

Run:

```powershell
python -m pytest tests/test_frontend_error_handling.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-run-ui-green"
```

Expected: all frontend contract tests PASS.

```powershell
git add static/index.html static/app.js static/styles.css tests/test_frontend_error_handling.py
git commit -m "feat: add SIT result dashboard and history"
```

---

### Task 7: Document and Verify the Complete Feature

**Files:**
- Modify: `docs/sit-case-progress.md`
- Test: all files under `tests/`

**Interfaces:**
- Consumes: completed backend and frontend feature.
- Produces: verified release evidence and updated project status documentation.

- [ ] **Step 1: Update progress documentation with exact behavior**

Add a `Local Result History and HTML Reports` section that states:

```markdown
Completed Browser SIT runs can be saved manually under `data/sit-runs/` and reopened from the Results view. Saving history and downloading a standalone HTML report are separate user actions. Single-case and multi-case runs expose the same summary, AReq timestamp, clickable per-case `acsTransID`, transaction-result summary, card scheme, and Issuer OID parsed from the actual AReq URL. Runtime history is excluded from Git.
```

- [ ] **Step 2: Run focused feature tests**

Run:

```powershell
python -m pytest tests/test_run_results.py tests/test_run_repository.py tests/test_run_report.py tests/test_sit_runner_api.py tests/test_frontend_error_handling.py -v -p no:cacheprovider --basetemp "$env:TEMP\acs-result-feature"
```

Expected: all focused tests PASS with no errors.

- [ ] **Step 3: Run the complete automated suite**

Run:

```powershell
python -m pytest -p no:cacheprovider --basetemp "$env:TEMP\acs-result-all"
```

Expected: all tests PASS; the baseline is 213 tests before adding this feature.

- [ ] **Step 4: Perform local browser verification**

Start the application:

```powershell
python -m acs_auto_sit --host 127.0.0.1 --port 8000
```

Verify at desktop and 390px widths:

1. A one-case run enables both actions after the case terminates.
2. The header shows mode, effective challenge, locale, card scheme `V`, and the parsed Issuer OID.
3. Clicking one displayed `acsTransID` copies its full value and no bulk-copy action exists.
4. Save the run, refresh, reopen it from history, and confirm identical counts and case details.
5. Download current and saved HTML reports.
6. Stop the application and open both downloaded files; confirm they remain readable and contain no failed external requests.
7. Repeat with a multi-case run and confirm summary totals match the result rows.

- [ ] **Step 5: Commit documentation and final verification state**

```powershell
git add docs/sit-case-progress.md
git commit -m "docs: record SIT result reporting coverage"
```

---

## Final Review Checklist

- [ ] Every confirmed design requirement maps to a task above.
- [ ] A one-case run and multi-case run follow the same terminal-state rule.
- [ ] The frontend never saves automatically.
- [ ] Current-run HTML can download without first saving JSON.
- [ ] Saved-run HTML can regenerate from history.
- [ ] Card scheme and Issuer OID come from the actual AReq URL, not the wording profile.
- [ ] Individual IDs copy directly; no bulk-copy control exists.
- [ ] Report rendering escapes ACS content and works with the server stopped.
- [ ] Runtime history and `.superpowers/` are ignored by Git.
- [ ] Full tests and responsive browser verification pass before completion is claimed.
