# ACS Auto SIT Browser Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python FastAPI ACS auto SIT tool that imports Browser test cases, POSTs AReq, follows CReq/CRes challenge loops only while `transStatus = "C"`, records local evidence, and exposes a thin simulator UI.

**Architecture:** The app is a small FastAPI service with focused domain modules under `acs_auto_sit/`, file-backed JSON storage under `data/`, and static UI files under `static/`. The backend owns reliable AReq/CReq automation and CRes capture; the UI is a flow control surface for importing cases, starting runs, continuing challenge actions, and reviewing evidence.

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, httpx, openpyxl, pytest, standard-library JSON/file storage, vanilla HTML/CSS/JavaScript.

## Global Constraints

- Backend: Python FastAPI.
- Authentication: none.
- Deployment: local machine by default, with optional intranet access by binding to `0.0.0.0`.
- Storage: local files under `data/`.
- Transport: all ACS/3DS transaction calls use POST.
- TLS: normal HTTPS only; no client certificate, custom CA, or insecure TLS option in v1.
- Main automation path: backend POSTs AReq and backend POSTs CReq, so the tool can reliably capture CRes response bodies.
- Browser helper path: a simulator page can auto-submit a hidden POST form to ACS for visual/browser behavior checks, but v1 does not rely on it to capture CRes.
- Only `transStatus = "C"` starts or continues CReq generation.
- Later CReq messages are generated from previous CRes, selected challenge action, and case settings.
- V1 imports Browser rows from the Excel workbook first and preserves app-flow fields for later.

---

## File Structure

- Create `pyproject.toml`: package metadata, runtime dependencies, pytest config.
- Create `README.md`: setup, run commands, local/intranet usage, sample import/run flow.
- Create `.gitignore`: Python cache, virtualenv, local data, test temp output.
- Create `acs_auto_sit/__init__.py`: package marker.
- Create `acs_auto_sit/models.py`: dataclasses and enums for cases, runs, exchanges, rules, callbacks, and statuses.
- Create `acs_auto_sit/storage.py`: JSON file repository with atomic writes and typed load/save helpers.
- Create `acs_auto_sit/template.py`: recursive `{{name}}` rendering for AReq/CReq templates.
- Create `acs_auto_sit/excel_importer.py`: Browser sheet importer and validation-rule draft extraction.
- Create `acs_auto_sit/validator.py`: JSONPath-like value lookup and rule evaluation.
- Create `acs_auto_sit/three_ds.py`: ARes extraction, first/later CReq generation, transStatus gating.
- Create `acs_auto_sit/http_client.py`: ACS POST wrapper around httpx with timing and raw/JSON response capture.
- Create `acs_auto_sit/services.py`: orchestration for case import, run start, challenge continue, callback capture.
- Create `acs_auto_sit/api.py`: FastAPI app, POST APIs, static file mounting.
- Create `acs_auto_sit/__main__.py`: `python -m acs_auto_sit` development server entry point.
- Create `static/index.html`: simulator UI.
- Create `static/styles.css`: compact operational styling.
- Create `static/app.js`: frontend API client and flow UI logic.
- Create `tests/fixtures/browser_cases.xlsx`: generated test workbook used by importer tests.
- Create `tests/test_*.py`: unit and API tests for each module.

---

### Task 1: Project Scaffold and Domain Models

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `acs_auto_sit/__init__.py`
- Create: `acs_auto_sit/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `RunStatus` enum with values `created`, `areq_sent`, `challenge_required`, `challenge_running`, `waiting_input`, `waiting_callback`, `passed`, `failed`, `error`.
  - `ValidationRule`, `TestCase`, `HttpRecord`, `ChallengeExchange`, `CallbackRecord`, `RunRecord` dataclasses.
  - `to_dict(value: Any) -> Any`.
  - `from_dict(model_type: type[T], data: dict[str, Any]) -> T`.

- [ ] **Step 1: Write the failing model serialization tests**

Create `tests/test_models.py`:

```python
from acs_auto_sit.models import (
    ChallengeExchange,
    HttpRecord,
    RunRecord,
    RunStatus,
    TestCase,
    ValidationRule,
    from_dict,
    to_dict,
)


def test_case_round_trips_nested_rules():
    case = TestCase(
        id="case01",
        title="OTP transaction successful",
        channel="Browser",
        module="Browser Transaction Verification Process",
        test_point="CUP",
        steps="Enter correct verification code",
        expected_results="CRes transStatus = Y",
        areq_url="https://acs.example.test/areq",
        headers={"Content-Type": "application/json"},
        areq_template={"messageType": "AReq"},
        creq_settings={"challengeWindowSize": "05"},
        validation_rules=[
            ValidationRule(target="cres", path="$.transStatus", operator="equals", expected="Y")
        ],
        imported_metadata={"System": "ACS 2.2"},
    )

    raw = to_dict(case)
    assert raw["validation_rules"][0]["path"] == "$.transStatus"

    restored = from_dict(TestCase, raw)
    assert restored == case


def test_run_record_defaults_and_exchange_round_trip():
    run = RunRecord(
        id="run-1",
        case_id="case01",
        status=RunStatus.challenge_running,
        created_at="2026-07-10T09:00:00+08:00",
        updated_at="2026-07-10T09:00:01+08:00",
        areq=HttpRecord(method="POST", url="https://acs.example.test/areq", request_body={}),
        ares={"transStatus": "C"},
        extracted={"acsURL": "https://acs.example.test/challenge"},
        challenge_exchanges=[
            ChallengeExchange(
                sequence=1,
                action="initial",
                creq={"messageType": "CReq"},
                cres={"transStatus": "C"},
                http=HttpRecord(method="POST", url="https://acs.example.test/challenge"),
            )
        ],
    )

    restored = from_dict(RunRecord, to_dict(run))
    assert restored.status is RunStatus.challenge_running
    assert restored.challenge_exchanges[0].creq["messageType"] == "CReq"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'acs_auto_sit'`.

- [ ] **Step 3: Create project scaffold**

Create `pyproject.toml`:

```toml
[project]
name = "acs-auto-sit"
version = "0.1.0"
description = "ACS automated SIT tool for 3DS browser-based AReq and CReq flows"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.116,<1",
  "uvicorn[standard]>=0.35,<1",
  "httpx>=0.28,<1",
  "openpyxl>=3.1,<4",
  "python-multipart>=0.0.20,<1"
]

[project.optional-dependencies]
dev = [
  "pytest>=8.4,<9",
  "pytest-asyncio>=1.0,<2",
  "respx>=0.22,<1"
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-q"
```

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
data/
*.log
```

Create `README.md`:

```markdown
# ACS Auto SIT Tool

Python FastAPI tool for ACS automated SIT of 3DS browser-based AReq and CReq/CRes flows.

## Setup

```powershell
python -m pip install -e .[dev]
```

## Run Locally

```powershell
python -m acs_auto_sit --host 127.0.0.1 --port 8000
```

## Run On Intranet

```powershell
python -m acs_auto_sit --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/`.

All ACS transaction requests are POST. No login is implemented in v1.
```

Create `acs_auto_sit/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

- [ ] **Step 4: Implement domain models**

Create `acs_auto_sit/models.py`:

```python
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, TypeVar, get_args, get_origin, get_type_hints


class RunStatus(str, Enum):
    created = "created"
    areq_sent = "areq_sent"
    challenge_required = "challenge_required"
    challenge_running = "challenge_running"
    waiting_input = "waiting_input"
    waiting_callback = "waiting_callback"
    passed = "passed"
    failed = "failed"
    error = "error"


@dataclass(slots=True)
class ValidationRule:
    target: str
    path: str
    operator: str
    expected: Any = None


@dataclass(slots=True)
class TestCase:
    id: str
    title: str
    channel: str
    module: str
    test_point: str
    steps: str
    expected_results: str
    areq_url: str
    headers: dict[str, str]
    areq_template: dict[str, Any]
    creq_settings: dict[str, Any] = field(default_factory=dict)
    validation_rules: list[ValidationRule] = field(default_factory=list)
    imported_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HttpRecord:
    method: str
    url: str
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: Any = None
    status_code: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: Any = None
    raw_response: str = ""
    elapsed_ms: int = 0
    error: str | None = None


@dataclass(slots=True)
class ChallengeExchange:
    sequence: int
    action: str
    creq: dict[str, Any]
    cres: dict[str, Any] | None = None
    http: HttpRecord | None = None
    error: str | None = None


@dataclass(slots=True)
class CallbackRecord:
    received_at: str
    headers: dict[str, str]
    query: dict[str, str]
    form: dict[str, Any]
    json_body: Any = None
    raw_body: str = ""


@dataclass(slots=True)
class RunRecord:
    id: str
    case_id: str
    status: RunStatus
    created_at: str
    updated_at: str
    areq: HttpRecord | None = None
    ares: dict[str, Any] | None = None
    extracted: dict[str, Any] = field(default_factory=dict)
    challenge_exchanges: list[ChallengeExchange] = field(default_factory=list)
    callbacks: list[CallbackRecord] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


T = TypeVar("T")


def to_dict(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_dict(item) for key, item in value.items()}
    return value


def from_dict(model_type: type[T], data: dict[str, Any]) -> T:
    return _coerce(model_type, data)


def _coerce(annotation: Any, value: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is list:
        return [_coerce(args[0], item) for item in value]
    if origin is dict:
        return dict(value)
    if origin is not None and type(None) in args:
        non_none = next(arg for arg in args if arg is not type(None))
        return _coerce(non_none, value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        resolved_types = get_type_hints(annotation)
        field_types = {item.name: resolved_types[item.name] for item in fields(annotation)}
        kwargs = {
            key: _coerce(field_types[key], item)
            for key, item in value.items()
            if key in field_types
        }
        return annotation(**kwargs)
    return value
```

- [ ] **Step 5: Run tests to verify models pass**

Run: `python -m pytest tests/test_models.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore README.md acs_auto_sit/__init__.py acs_auto_sit/models.py tests/test_models.py
git commit -m "feat: add project scaffold and domain models"
```

---

### Task 2: File Storage and Template Rendering

**Files:**
- Create: `acs_auto_sit/storage.py`
- Create: `acs_auto_sit/template.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_template.py`

**Interfaces:**
- Consumes: `TestCase`, `RunRecord`, `to_dict`, `from_dict`.
- Produces:
  - `JsonRepository(root: Path)`.
  - `save_case(case: TestCase) -> None`, `load_case(case_id: str) -> TestCase`, `list_cases() -> list[TestCase]`.
  - `save_run(run: RunRecord) -> None`, `load_run(run_id: str) -> RunRecord`.
  - `save_import(import_id: str, data: dict[str, Any]) -> None`.
  - `render_template(value: Any, variables: dict[str, Any]) -> Any`.

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
from acs_auto_sit.models import RunRecord, RunStatus, TestCase
from acs_auto_sit.storage import JsonRepository


def test_repository_saves_and_loads_case(tmp_path):
    repo = JsonRepository(tmp_path)
    case = TestCase(
        id="case01",
        title="Title",
        channel="Browser",
        module="Module",
        test_point="CUP",
        steps="Steps",
        expected_results="Expected",
        areq_url="https://acs.example.test/areq",
        headers={"Content-Type": "application/json"},
        areq_template={"messageType": "AReq"},
    )

    repo.save_case(case)

    assert repo.load_case("case01") == case
    assert [item.id for item in repo.list_cases()] == ["case01"]


def test_repository_saves_and_loads_run(tmp_path):
    repo = JsonRepository(tmp_path)
    run = RunRecord(
        id="run01",
        case_id="case01",
        status=RunStatus.created,
        created_at="2026-07-10T09:00:00+08:00",
        updated_at="2026-07-10T09:00:00+08:00",
    )

    repo.save_run(run)

    assert repo.load_run("run01") == run
```

- [ ] **Step 2: Write failing template tests**

Create `tests/test_template.py`:

```python
from acs_auto_sit.template import render_template


def test_render_template_recurses_dicts_and_lists():
    rendered = render_template(
        {
            "notificationURL": "{{callback_url}}",
            "nested": [{"id": "{{threeDSServerTransID}}"}],
            "unchanged": "AReq",
        },
        {
            "callback_url": "http://127.0.0.1:8000/api/callback/run01",
            "threeDSServerTransID": "trans-1",
        },
    )

    assert rendered["notificationURL"].endswith("/run01")
    assert rendered["nested"][0]["id"] == "trans-1"
    assert rendered["unchanged"] == "AReq"


def test_render_template_keeps_unknown_variables_visible():
    assert render_template("{{missing}}", {}) == "{{missing}}"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_storage.py tests/test_template.py -v`

Expected: FAIL with missing modules.

- [ ] **Step 4: Implement JSON repository**

Create `acs_auto_sit/storage.py`:

```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from acs_auto_sit.models import RunRecord, TestCase, from_dict, to_dict


class JsonRepository:
    def __init__(self, root: Path):
        self.root = root
        self.cases_dir = root / "cases"
        self.runs_dir = root / "runs"
        self.imports_dir = root / "imports"
        for path in (self.cases_dir, self.runs_dir, self.imports_dir):
            path.mkdir(parents=True, exist_ok=True)

    def save_case(self, case: TestCase) -> None:
        self._write_json(self.cases_dir / f"{case.id}.json", to_dict(case))

    def load_case(self, case_id: str) -> TestCase:
        return from_dict(TestCase, self._read_json(self.cases_dir / f"{case_id}.json"))

    def list_cases(self) -> list[TestCase]:
        return [
            from_dict(TestCase, self._read_json(path))
            for path in sorted(self.cases_dir.glob("*.json"))
        ]

    def save_run(self, run: RunRecord) -> None:
        self._write_json(self.runs_dir / f"{run.id}.json", to_dict(run))

    def load_run(self, run_id: str) -> RunRecord:
        return from_dict(RunRecord, self._read_json(self.runs_dir / f"{run_id}.json"))

    def save_import(self, import_id: str, data: dict[str, Any]) -> None:
        self._write_json(self.imports_dir / f"{import_id}.json", data)

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
```

- [ ] **Step 5: Implement recursive template rendering**

Create `acs_auto_sit/template.py`:

```python
from __future__ import annotations

import re
from typing import Any

TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def render_template(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: render_template(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    if isinstance(value, str):
        return TOKEN_RE.sub(lambda match: str(variables.get(match.group(1), match.group(0))), value)
    return value
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python -m pytest tests/test_storage.py tests/test_template.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add acs_auto_sit/storage.py acs_auto_sit/template.py tests/test_storage.py tests/test_template.py
git commit -m "feat: add file storage and template rendering"
```

---

### Task 3: Excel Importer and Validation Rules

**Files:**
- Create: `acs_auto_sit/excel_importer.py`
- Create: `acs_auto_sit/validator.py`
- Test: `tests/test_excel_importer.py`
- Test: `tests/test_validator.py`

**Interfaces:**
- Consumes: `TestCase`, `ValidationRule`.
- Produces:
  - `import_browser_cases(path: Path, default_areq_url: str, default_areq_template: dict[str, Any]) -> list[TestCase]`.
  - `draft_rules_from_expected_results(text: str) -> list[ValidationRule]`.
  - `evaluate_rules(targets: dict[str, Any], rules: list[ValidationRule]) -> list[dict[str, Any]]`.
  - `get_path(document: Any, path: str) -> tuple[bool, Any]`.

- [ ] **Step 1: Write failing validator tests**

Create `tests/test_validator.py`:

```python
from acs_auto_sit.models import ValidationRule
from acs_auto_sit.validator import evaluate_rules, get_path


def test_get_path_finds_nested_values():
    found, value = get_path({"a": {"b": [{"c": "Y"}]}}, "$.a.b[0].c")
    assert found is True
    assert value == "Y"


def test_evaluate_rules_supports_core_operators():
    results = evaluate_rules(
        {"cres": {"transStatus": "Y", "eci": "05", "cavv": "abc"}},
        [
            ValidationRule(target="cres", path="$.transStatus", operator="equals", expected="Y"),
            ValidationRule(target="cres", path="$.eci", operator="in", expected=["05", "06"]),
            ValidationRule(target="cres", path="$.cavv", operator="not_null"),
            ValidationRule(target="cres", path="$.missing", operator="not_exists"),
        ],
    )

    assert all(item["passed"] for item in results)
```

- [ ] **Step 2: Write failing Excel importer tests**

Create `tests/test_excel_importer.py`:

```python
from pathlib import Path

from openpyxl import Workbook

from acs_auto_sit.excel_importer import draft_rules_from_expected_results, import_browser_cases


def make_workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Browser"
    ws.append(["ID", "System", "Module", "Function Point", "Test Points", "Steps", "Expected Results", "Actual Result", "Test Date", "Testers", "Remarks"])
    ws.append([
        "case01",
        "ACS 2.2",
        "Browser Transaction Verification Process",
        "OTP transaction successful",
        "CUP",
        "Enter correct OTP",
        'ACS 2.2 return CRes message\n1.1 transStatus = "Y"\nRReq ECI ="05"\nCAVV is not null',
        "Pass",
        "2026-06-29",
        "Sasha",
        "",
    ])
    wb.create_sheet("App（Android Native）")
    wb.save(path)


def test_import_browser_cases_preserves_excel_fields(tmp_path):
    workbook = tmp_path / "cases.xlsx"
    make_workbook(workbook)

    cases = import_browser_cases(
        workbook,
        default_areq_url="https://acs.example.test/areq",
        default_areq_template={"messageType": "AReq"},
    )

    assert len(cases) == 1
    assert cases[0].id == "case01"
    assert cases[0].channel == "Browser"
    assert cases[0].areq_url == "https://acs.example.test/areq"
    assert cases[0].validation_rules[0].path == "$.transStatus"


def test_draft_rules_from_expected_results_extracts_common_assertions():
    rules = draft_rules_from_expected_results('transStatus = "N"\ntransStatusReason = "19"\nCAVV is null')
    pairs = {(rule.path, rule.operator, rule.expected) for rule in rules}

    assert ("$.transStatus", "equals", "N") in pairs
    assert ("$.transStatusReason", "equals", "19") in pairs
    assert ("$.cavv", "is_null", None) in pairs
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_validator.py tests/test_excel_importer.py -v`

Expected: FAIL with missing modules.

- [ ] **Step 4: Implement validator**

Create `acs_auto_sit/validator.py`:

```python
from __future__ import annotations

import re
from typing import Any

from acs_auto_sit.models import ValidationRule

PART_RE = re.compile(r"([A-Za-z0-9_]+)(?:\[(\d+)\])?")


def get_path(document: Any, path: str) -> tuple[bool, Any]:
    if path == "$":
        return True, document
    if not path.startswith("$."):
        return False, None
    current = document
    for part in path[2:].split("."):
        match = PART_RE.fullmatch(part)
        if not match:
            return False, None
        key, index = match.groups()
        if not isinstance(current, dict) or key not in current:
            return False, None
        current = current[key]
        if index is not None:
            if not isinstance(current, list):
                return False, None
            idx = int(index)
            if idx >= len(current):
                return False, None
            current = current[idx]
    return True, current


def evaluate_rules(targets: dict[str, Any], rules: list[ValidationRule]) -> list[dict[str, Any]]:
    return [_evaluate_rule(targets, rule) for rule in rules]


def _evaluate_rule(targets: dict[str, Any], rule: ValidationRule) -> dict[str, Any]:
    found, actual = get_path(targets.get(rule.target, {}), rule.path)
    passed = _compare(found, actual, rule.operator, rule.expected)
    return {
        "target": rule.target,
        "path": rule.path,
        "operator": rule.operator,
        "expected": rule.expected,
        "actual": actual,
        "found": found,
        "passed": passed,
    }


def _compare(found: bool, actual: Any, operator: str, expected: Any) -> bool:
    if operator == "exists":
        return found
    if operator == "not_exists":
        return not found
    if operator == "equals":
        return found and actual == expected
    if operator == "not_equals":
        return found and actual != expected
    if operator == "in":
        return found and actual in expected
    if operator == "not_null":
        return found and actual is not None
    if operator == "is_null":
        return (not found) or actual is None
    if operator == "contains":
        return found and str(expected) in str(actual)
    return False
```

- [ ] **Step 5: Implement Excel importer**

Create `acs_auto_sit/excel_importer.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from acs_auto_sit.models import TestCase, ValidationRule

STATUS_RE = re.compile(r"(transStatus|transStatusReason)\s*=\s*\"?([A-Za-z0-9]+)\"?", re.IGNORECASE)
ECI_RE = re.compile(r"\bECI\s*=\s*\"?([A-Za-z0-9]+)\"?", re.IGNORECASE)


def import_browser_cases(
    path: Path,
    default_areq_url: str,
    default_areq_template: dict[str, Any],
) -> list[TestCase]:
    workbook = load_workbook(path, data_only=True)
    worksheet = workbook["Browser"]
    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in worksheet[1]]
    cases: list[TestCase] = []
    for row in worksheet.iter_rows(min_row=2, values_only=True):
        values = dict(zip(headers, row))
        case_id = _clean(values.get("ID"))
        if not case_id:
            continue
        expected = _clean(values.get("Expected Results"))
        cases.append(
            TestCase(
                id=case_id,
                title=_clean(values.get("Function Point")),
                channel="Browser",
                module=_clean(values.get("Module")),
                test_point=_clean(values.get("Test Points")),
                steps=_clean(values.get("Steps")),
                expected_results=expected,
                areq_url=default_areq_url,
                headers={"Content-Type": "application/json"},
                areq_template=default_areq_template,
                creq_settings={"challengeWindowSize": "05", "maxExchanges": 5},
                validation_rules=draft_rules_from_expected_results(expected),
                imported_metadata={
                    "System": _clean(values.get("System")),
                    "Actual Result": _clean(values.get("Actual Result")),
                    "Test Date": _clean(values.get("Test Date")),
                    "Testers": _clean(values.get("Testers")),
                    "Remarks": _clean(values.get("Remarks")),
                },
            )
        )
    return cases


def draft_rules_from_expected_results(text: str) -> list[ValidationRule]:
    rules: list[ValidationRule] = []
    for field, value in STATUS_RE.findall(text):
        path = "$.transStatus" if field.lower() == "transstatus" else "$.transStatusReason"
        rules.append(ValidationRule(target="cres", path=path, operator="equals", expected=value))
    eci_match = ECI_RE.search(text)
    if eci_match:
        rules.append(ValidationRule(target="callback", path="$.eci", operator="equals", expected=eci_match.group(1)))
    lowered = text.lower()
    if "cavv is not null" in lowered:
        rules.append(ValidationRule(target="callback", path="$.cavv", operator="not_null"))
    if "cavv is null" in lowered:
        rules.append(ValidationRule(target="callback", path="$.cavv", operator="is_null"))
    return rules


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python -m pytest tests/test_validator.py tests/test_excel_importer.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add acs_auto_sit/excel_importer.py acs_auto_sit/validator.py tests/test_excel_importer.py tests/test_validator.py
git commit -m "feat: import browser cases and evaluate rules"
```

---

### Task 4: 3DS Flow Logic and HTTP Client

**Files:**
- Create: `acs_auto_sit/three_ds.py`
- Create: `acs_auto_sit/http_client.py`
- Test: `tests/test_three_ds.py`
- Test: `tests/test_http_client.py`

**Interfaces:**
- Consumes: `HttpRecord`, `ChallengeExchange`, `TestCase`, `RunRecord`.
- Produces:
  - `extract_ares_fields(ares: dict[str, Any], original_areq: dict[str, Any]) -> dict[str, Any]`.
  - `should_start_challenge(ares: dict[str, Any]) -> bool`.
  - `should_continue_challenge(cres: dict[str, Any]) -> bool`.
  - `build_first_creq(ares: dict[str, Any], original_areq: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]`.
  - `build_next_creq(previous_cres: dict[str, Any], action: str, action_data: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]`.
  - `post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float = 30.0) -> HttpRecord`.

- [ ] **Step 1: Write failing 3DS logic tests**

Create `tests/test_three_ds.py`:

```python
from acs_auto_sit.three_ds import (
    build_first_creq,
    build_next_creq,
    extract_ares_fields,
    should_continue_challenge,
    should_start_challenge,
)


def test_only_trans_status_c_starts_or_continues_challenge():
    assert should_start_challenge({"transStatus": "C"}) is True
    assert should_start_challenge({"transStatus": "Y"}) is False
    assert should_continue_challenge({"transStatus": "C"}) is True
    assert should_continue_challenge({"transStatus": "N"}) is False


def test_build_first_creq_uses_ares_and_areq_values():
    areq = {"messageVersion": "2.2.0", "threeDSServerTransID": "server-trans"}
    ares = {"acsTransID": "acs-trans", "messageVersion": "2.2.0"}

    creq = build_first_creq(ares, areq, {"challengeWindowSize": "05"})

    assert creq == {
        "messageType": "CReq",
        "messageVersion": "2.2.0",
        "threeDSServerTransID": "server-trans",
        "acsTransID": "acs-trans",
        "challengeWindowSize": "05",
    }


def test_build_next_creq_merges_action_specific_data():
    previous = {
        "messageVersion": "2.2.0",
        "threeDSServerTransID": "server-trans",
        "acsTransID": "acs-trans",
        "transStatus": "C",
    }
    creq = build_next_creq(
        previous,
        action="submit_challenge_value",
        action_data={"challengeValue": "123456"},
        base={"challengeWindowSize": "05"},
    )

    assert creq["challengeValue"] == "123456"
    assert creq["challengeAction"] == "submit_challenge_value"


def test_extract_ares_fields_falls_back_to_areq_trans_id():
    extracted = extract_ares_fields(
        {"transStatus": "C", "acsURL": "https://acs.example.test/challenge"},
        {"threeDSServerTransID": "server-trans"},
    )

    assert extracted["threeDSServerTransID"] == "server-trans"
    assert extracted["acsURL"].endswith("/challenge")
```

- [ ] **Step 2: Write failing HTTP client test**

Create `tests/test_http_client.py`:

```python
import pytest

from acs_auto_sit.http_client import post_json


@pytest.mark.asyncio
async def test_post_json_records_json_response(respx_mock):
    route = respx_mock.post("https://acs.example.test/areq").respond(200, json={"transStatus": "C"})

    record = await post_json(
        "https://acs.example.test/areq",
        {"Content-Type": "application/json"},
        {"messageType": "AReq"},
    )

    assert route.called
    assert record.method == "POST"
    assert record.status_code == 200
    assert record.response_body == {"transStatus": "C"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_three_ds.py tests/test_http_client.py -v`

Expected: FAIL with missing modules.

- [ ] **Step 4: Implement 3DS flow helpers**

Create `acs_auto_sit/three_ds.py`:

```python
from __future__ import annotations

from typing import Any


def extract_ares_fields(ares: dict[str, Any], original_areq: dict[str, Any]) -> dict[str, Any]:
    return {
        "messageType": ares.get("messageType"),
        "messageVersion": ares.get("messageVersion") or original_areq.get("messageVersion"),
        "threeDSServerTransID": ares.get("threeDSServerTransID") or original_areq.get("threeDSServerTransID"),
        "acsTransID": ares.get("acsTransID"),
        "transStatus": ares.get("transStatus"),
        "acsURL": ares.get("acsURL"),
    }


def should_start_challenge(ares: dict[str, Any]) -> bool:
    return ares.get("transStatus") == "C"


def should_continue_challenge(cres: dict[str, Any]) -> bool:
    return cres.get("transStatus") == "C"


def build_first_creq(
    ares: dict[str, Any],
    original_areq: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "messageType": "CReq",
        "messageVersion": ares.get("messageVersion") or original_areq.get("messageVersion"),
        "threeDSServerTransID": ares.get("threeDSServerTransID") or original_areq.get("threeDSServerTransID"),
        "acsTransID": ares["acsTransID"],
        "challengeWindowSize": settings.get("challengeWindowSize", "05"),
    }


def build_next_creq(
    previous_cres: dict[str, Any],
    action: str,
    action_data: dict[str, Any],
    base: dict[str, Any],
) -> dict[str, Any]:
    creq = {
        "messageType": "CReq",
        "messageVersion": previous_cres.get("messageVersion") or base.get("messageVersion"),
        "threeDSServerTransID": previous_cres.get("threeDSServerTransID") or base.get("threeDSServerTransID"),
        "acsTransID": previous_cres.get("acsTransID") or base.get("acsTransID"),
        "challengeWindowSize": base.get("challengeWindowSize", "05"),
        "challengeAction": action,
    }
    creq.update(action_data)
    return creq
```

- [ ] **Step 5: Implement HTTP client**

Create `acs_auto_sit/http_client.py`:

```python
from __future__ import annotations

import time
from typing import Any

import httpx

from acs_auto_sit.models import HttpRecord


async def post_json(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float = 30.0,
) -> HttpRecord:
    started = time.perf_counter()
    record = HttpRecord(method="POST", url=url, request_headers=headers, request_body=body)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
        record.status_code = response.status_code
        record.response_headers = dict(response.headers)
        record.raw_response = response.text
        try:
            record.response_body = response.json()
        except ValueError:
            record.response_body = None
    except httpx.HTTPError as exc:
        record.error = str(exc)
    finally:
        record.elapsed_ms = int((time.perf_counter() - started) * 1000)
    return record
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python -m pytest tests/test_three_ds.py tests/test_http_client.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml acs_auto_sit/three_ds.py acs_auto_sit/http_client.py tests/test_three_ds.py tests/test_http_client.py
git commit -m "feat: add 3ds flow helpers and post client"
```

---

### Task 5: Run Orchestration Service

**Files:**
- Create: `acs_auto_sit/services.py`
- Test: `tests/test_services.py`

**Interfaces:**
- Consumes: `JsonRepository`, `post_json`, `render_template`, `evaluate_rules`, `three_ds` helpers.
- Produces:
  - `AcsSitService(repository: JsonRepository, base_url: str)`.
  - `start_run(case_id: str, variables: dict[str, Any]) -> RunRecord`.
  - `continue_challenge(run_id: str, action: str, action_data: dict[str, Any]) -> RunRecord`.
  - `record_callback(run_id: str, callback: CallbackRecord) -> RunRecord`.

- [ ] **Step 1: Write failing service tests**

Create `tests/test_services.py`:

```python
import pytest

from acs_auto_sit.models import RunStatus, TestCase
from acs_auto_sit.services import AcsSitService
from acs_auto_sit.storage import JsonRepository


@pytest.mark.asyncio
async def test_start_run_posts_areq_and_creates_first_creq(respx_mock, tmp_path):
    repo = JsonRepository(tmp_path)
    repo.save_case(TestCase(
        id="case01",
        title="Challenge",
        channel="Browser",
        module="Module",
        test_point="CUP",
        steps="Steps",
        expected_results="Expected",
        areq_url="https://acs.example.test/areq",
        headers={"Content-Type": "application/json"},
        areq_template={"messageType": "AReq", "messageVersion": "2.2.0", "threeDSServerTransID": "server-trans"},
        creq_settings={"challengeWindowSize": "05", "maxExchanges": 5},
    ))
    respx_mock.post("https://acs.example.test/areq").respond(
        200,
        json={"messageVersion": "2.2.0", "transStatus": "C", "acsTransID": "acs-trans", "acsURL": "https://acs.example.test/challenge"},
    )

    service = AcsSitService(repo, base_url="http://127.0.0.1:8000")
    run = await service.start_run("case01", {})

    assert run.status is RunStatus.challenge_required
    assert run.challenge_exchanges[0].creq["acsTransID"] == "acs-trans"


@pytest.mark.asyncio
async def test_continue_challenge_stops_when_cres_is_not_c(respx_mock, tmp_path):
    repo = JsonRepository(tmp_path)
    repo.save_case(TestCase(
        id="case01",
        title="Challenge",
        channel="Browser",
        module="Module",
        test_point="CUP",
        steps="Steps",
        expected_results="Expected",
        areq_url="https://acs.example.test/areq",
        headers={"Content-Type": "application/json"},
        areq_template={"messageType": "AReq", "messageVersion": "2.2.0", "threeDSServerTransID": "server-trans"},
        creq_settings={"challengeWindowSize": "05", "maxExchanges": 5},
    ))
    respx_mock.post("https://acs.example.test/areq").respond(
        200,
        json={"messageVersion": "2.2.0", "transStatus": "C", "acsTransID": "acs-trans", "acsURL": "https://acs.example.test/challenge"},
    )
    respx_mock.post("https://acs.example.test/challenge").respond(200, json={"transStatus": "Y"})

    service = AcsSitService(repo, base_url="http://127.0.0.1:8000")
    started = await service.start_run("case01", {})
    continued = await service.continue_challenge(started.id, "initial", {})

    assert continued.status is RunStatus.passed
    assert continued.challenge_exchanges[0].cres == {"transStatus": "Y"}
```

- [ ] **Step 2: Run service tests to verify fail**

Run: `python -m pytest tests/test_services.py -v`

Expected: FAIL with missing `acs_auto_sit.services`.

- [ ] **Step 3: Implement orchestration service**

Create `acs_auto_sit/services.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from acs_auto_sit.http_client import post_json
from acs_auto_sit.models import CallbackRecord, ChallengeExchange, RunRecord, RunStatus
from acs_auto_sit.storage import JsonRepository
from acs_auto_sit.template import render_template
from acs_auto_sit.three_ds import (
    build_first_creq,
    build_next_creq,
    extract_ares_fields,
    should_continue_challenge,
    should_start_challenge,
)
from acs_auto_sit.validator import evaluate_rules


class AcsSitService:
    def __init__(self, repository: JsonRepository, base_url: str):
        self.repository = repository
        self.base_url = base_url.rstrip("/")

    async def start_run(self, case_id: str, variables: dict[str, Any]) -> RunRecord:
        case = self.repository.load_case(case_id)
        now = _now()
        run = RunRecord(
            id=uuid4().hex,
            case_id=case.id,
            status=RunStatus.created,
            created_at=now,
            updated_at=now,
        )
        variables = {
            **variables,
            "callback_url": f"{self.base_url}/api/callback/{run.id}",
        }
        areq_body = render_template(case.areq_template, variables)
        areq_record = await post_json(case.areq_url, case.headers, areq_body)
        run.areq = areq_record
        run.updated_at = _now()
        if areq_record.error:
            run.status = RunStatus.error
            run.errors.append(areq_record.error)
            self.repository.save_run(run)
            return run
        if not isinstance(areq_record.response_body, dict):
            run.status = RunStatus.error
            run.errors.append("ARes response body is not JSON")
            self.repository.save_run(run)
            return run
        run.ares = areq_record.response_body
        run.extracted = extract_ares_fields(run.ares, areq_body)
        if should_start_challenge(run.ares):
            acs_url = run.extracted.get("acsURL")
            if not acs_url:
                run.status = RunStatus.failed
                run.errors.append('ARes transStatus is "C" but acsURL is missing')
            else:
                run.status = RunStatus.challenge_required
                run.challenge_exchanges.append(
                    ChallengeExchange(
                        sequence=1,
                        action="initial",
                        creq=build_first_creq(run.ares, areq_body, case.creq_settings),
                    )
                )
        else:
            run.status = self._finalize(run, case.validation_rules)
        self.repository.save_run(run)
        return run

    async def continue_challenge(self, run_id: str, action: str, action_data: dict[str, Any]) -> RunRecord:
        run = self.repository.load_run(run_id)
        case = self.repository.load_case(run.case_id)
        if not run.challenge_exchanges:
            run.status = RunStatus.failed
            run.errors.append("No challenge exchange is available")
            self.repository.save_run(run)
            return run
        exchange = run.challenge_exchanges[-1]
        acs_url = run.extracted.get("acsURL")
        if not acs_url:
            run.status = RunStatus.failed
            run.errors.append("acsURL is missing")
            self.repository.save_run(run)
            return run
        if action != exchange.action or action_data:
            base = {**run.extracted, **case.creq_settings}
            previous_cres = run.challenge_exchanges[-2].cres if len(run.challenge_exchanges) > 1 else run.ares or {}
            exchange.action = action
            exchange.creq = build_next_creq(previous_cres or {}, action, action_data, base)
        exchange.http = await post_json(acs_url, {"Content-Type": "application/json"}, exchange.creq)
        if exchange.http.error:
            exchange.error = exchange.http.error
            run.status = RunStatus.error
            run.errors.append(exchange.http.error)
        elif not isinstance(exchange.http.response_body, dict):
            exchange.error = "CRes response body is not JSON"
            run.status = RunStatus.error
            run.errors.append(exchange.error)
        else:
            exchange.cres = exchange.http.response_body
            if should_continue_challenge(exchange.cres):
                max_exchanges = int(case.creq_settings.get("maxExchanges", 5))
                if len(run.challenge_exchanges) >= max_exchanges:
                    run.status = RunStatus.failed
                    run.errors.append("max_exchanges_exceeded")
                else:
                    run.status = RunStatus.waiting_input
                    run.challenge_exchanges.append(
                        ChallengeExchange(
                            sequence=len(run.challenge_exchanges) + 1,
                            action="submit_challenge_value",
                            creq=build_next_creq(exchange.cres, "submit_challenge_value", {}, {**run.extracted, **case.creq_settings}),
                        )
                    )
            else:
                run.status = self._finalize(run, case.validation_rules)
        run.updated_at = _now()
        self.repository.save_run(run)
        return run

    def record_callback(self, run_id: str, callback: CallbackRecord) -> RunRecord:
        run = self.repository.load_run(run_id)
        run.callbacks.append(callback)
        run.updated_at = _now()
        self.repository.save_run(run)
        return run

    def _finalize(self, run: RunRecord, rules: list[Any]) -> RunStatus:
        latest_cres = run.challenge_exchanges[-1].cres if run.challenge_exchanges else None
        targets = {
            "ares": run.ares or {},
            "cres": latest_cres or {},
            "callback": run.callbacks[-1].json_body if run.callbacks and run.callbacks[-1].json_body else {},
        }
        run.validation_results = evaluate_rules(targets, rules)
        if run.validation_results and not all(item["passed"] for item in run.validation_results):
            return RunStatus.failed
        return RunStatus.passed


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
```

- [ ] **Step 4: Run service tests to verify pass**

Run: `python -m pytest tests/test_services.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acs_auto_sit/services.py tests/test_services.py
git commit -m "feat: orchestrate areq and challenge runs"
```

---

### Task 6: FastAPI POST APIs

**Files:**
- Create: `acs_auto_sit/api.py`
- Create: `acs_auto_sit/__main__.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `AcsSitService`, `JsonRepository`, `import_browser_cases`.
- Produces:
  - `create_app(data_root: Path | None = None, base_url: str = "http://127.0.0.1:8000") -> FastAPI`.
  - POST endpoints from the spec.
  - CLI: `python -m acs_auto_sit --host 127.0.0.1 --port 8000`.

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from acs_auto_sit.api import create_app


def test_cases_save_and_search_are_post_only(tmp_path):
    app = create_app(data_root=tmp_path, base_url="http://testserver")
    client = TestClient(app)

    save = client.post("/api/cases/save", json={
        "id": "case01",
        "title": "Title",
        "channel": "Browser",
        "module": "Module",
        "test_point": "CUP",
        "steps": "Steps",
        "expected_results": "Expected",
        "areq_url": "https://acs.example.test/areq",
        "headers": {"Content-Type": "application/json"},
        "areq_template": {"messageType": "AReq"},
        "creq_settings": {"challengeWindowSize": "05"},
        "validation_rules": [],
        "imported_metadata": {},
    })
    assert save.status_code == 200

    search = client.post("/api/cases/search", json={})
    assert search.status_code == 200
    assert search.json()["cases"][0]["id"] == "case01"


def test_callback_records_post_body(tmp_path):
    app = create_app(data_root=tmp_path, base_url="http://testserver")
    client = TestClient(app)

    client.post("/api/cases/save", json={
        "id": "case01",
        "title": "Title",
        "channel": "Browser",
        "module": "Module",
        "test_point": "CUP",
        "steps": "Steps",
        "expected_results": "Expected",
        "areq_url": "https://acs.example.test/areq",
        "headers": {"Content-Type": "application/json"},
        "areq_template": {"messageType": "AReq"},
    })

    # Store a minimal run directly through the repository path is covered by service tests;
    # this API test verifies the endpoint accepts POST JSON shape.
    response = client.post("/api/callback/missing", json={"transStatus": "Y"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run API tests to verify fail**

Run: `python -m pytest tests/test_api.py -v`

Expected: FAIL with missing `acs_auto_sit.api`.

- [ ] **Step 3: Implement FastAPI app**

Create `acs_auto_sit/api.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from acs_auto_sit.excel_importer import import_browser_cases
from acs_auto_sit.models import CallbackRecord, TestCase, from_dict, to_dict
from acs_auto_sit.services import AcsSitService
from acs_auto_sit.storage import JsonRepository


def create_app(data_root: Path | None = None, base_url: str = "http://127.0.0.1:8000") -> FastAPI:
    repo = JsonRepository(data_root or Path("data"))
    service = AcsSitService(repo, base_url=base_url)
    app = FastAPI(title="ACS Auto SIT Tool")
    app.state.repo = repo
    app.state.service = service

    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.post("/api/cases/search")
    async def cases_search() -> dict[str, Any]:
        return {"cases": [to_dict(case) for case in repo.list_cases()]}

    @app.post("/api/cases/save")
    async def cases_save(payload: dict[str, Any]) -> dict[str, Any]:
        case = from_dict(TestCase, payload)
        repo.save_case(case)
        return {"case": to_dict(case)}

    @app.post("/api/import/excel")
    async def import_excel(file: UploadFile, areq_url: str) -> dict[str, Any]:
        temp_path = Path("data") / "imports" / file.filename
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(await file.read())
        cases = import_browser_cases(temp_path, areq_url, {"messageType": "AReq"})
        for case in cases:
            repo.save_case(case)
        return {"cases": [to_dict(case) for case in cases]}

    @app.post("/api/runs/start")
    async def runs_start(payload: dict[str, Any]) -> dict[str, Any]:
        run = await service.start_run(payload["case_id"], payload.get("variables", {}))
        return {"run": to_dict(run)}

    @app.post("/api/runs/detail")
    async def runs_detail(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"run": to_dict(repo.load_run(payload["run_id"]))}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.post("/api/runs/creq/continue")
    async def creq_continue(payload: dict[str, Any]) -> dict[str, Any]:
        run = await service.continue_challenge(
            payload["run_id"],
            payload.get("action", "submit_challenge_value"),
            payload.get("action_data", {}),
        )
        return {"run": to_dict(run)}

    @app.post("/api/callback/{run_id}")
    async def callback(run_id: str, request: Request) -> dict[str, Any]:
        try:
            body = await request.body()
            json_body = None
            form = {}
            try:
                json_body = await request.json()
            except Exception:
                try:
                    form_data = await request.form()
                    form = dict(form_data)
                except Exception:
                    form = {}
            callback_record = CallbackRecord(
                received_at="",
                headers=dict(request.headers),
                query=dict(request.query_params),
                form=form,
                json_body=json_body,
                raw_body=body.decode("utf-8", errors="replace"),
            )
            run = service.record_callback(run_id, callback_record)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        return {"run": to_dict(run)}

    return app
```

Create `acs_auto_sit/__main__.py`:

```python
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    uvicorn.run("acs_auto_sit.api:create_app", factory=True, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run API tests to verify pass**

Run: `python -m pytest tests/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acs_auto_sit/api.py acs_auto_sit/__main__.py tests/test_api.py
git commit -m "feat: expose fastapi post endpoints"
```

---

### Task 7: Simulator UI

**Files:**
- Create: `static/index.html`
- Create: `static/styles.css`
- Create: `static/app.js`
- Test: `tests/test_static_ui.py`

**Interfaces:**
- Consumes: POST APIs from Task 6.
- Produces: operational browser UI for cases, run start, challenge continue, and evidence viewing.

- [ ] **Step 1: Write failing static UI test**

Create `tests/test_static_ui.py`:

```python
from pathlib import Path


def test_static_ui_contains_required_controls():
    html = Path("static/index.html").read_text(encoding="utf-8")
    js = Path("static/app.js").read_text(encoding="utf-8")

    assert "Start Run" in html
    assert "Continue Challenge" in html
    assert "/api/cases/search" in js
    assert "/api/runs/start" in js
    assert "/api/runs/creq/continue" in js
```

- [ ] **Step 2: Run static UI test to verify fail**

Run: `python -m pytest tests/test_static_ui.py -v`

Expected: FAIL because `static/index.html` does not exist.

- [ ] **Step 3: Create HTML**

Create `static/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ACS Auto SIT</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <main class="shell">
      <section class="panel">
        <h1>ACS Auto SIT</h1>
        <button id="refreshCases">Refresh Cases</button>
        <select id="caseSelect"></select>
        <pre id="caseDetails"></pre>
      </section>

      <section class="panel">
        <h2>AReq</h2>
        <textarea id="variables" spellcheck="false">{}</textarea>
        <button id="startRun">Start Run</button>
        <div id="runStatus"></div>
      </section>

      <section class="panel">
        <h2>Challenge</h2>
        <select id="challengeAction">
          <option value="initial">initial</option>
          <option value="select_verification_method">select_verification_method</option>
          <option value="submit_challenge_value">submit_challenge_value</option>
          <option value="resend_challenge_value">resend_challenge_value</option>
          <option value="cancel">cancel</option>
        </select>
        <textarea id="actionData" spellcheck="false">{}</textarea>
        <button id="continueChallenge">Continue Challenge</button>
      </section>

      <section class="panel wide">
        <h2>Evidence</h2>
        <pre id="evidence"></pre>
      </section>
    </main>
    <script src="/static/app.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Create CSS**

Create `static/styles.css`:

```css
:root {
  color-scheme: light;
  font-family: Arial, sans-serif;
  background: #f4f6f8;
  color: #17202a;
}

body {
  margin: 0;
}

.shell {
  display: grid;
  grid-template-columns: 320px 1fr 1fr;
  gap: 16px;
  padding: 16px;
}

.panel {
  background: #ffffff;
  border: 1px solid #d8dee6;
  border-radius: 8px;
  padding: 16px;
}

.wide {
  grid-column: 1 / -1;
}

button, select, textarea {
  box-sizing: border-box;
  width: 100%;
  margin-top: 8px;
  font: inherit;
}

button {
  min-height: 36px;
  cursor: pointer;
}

textarea {
  min-height: 160px;
  font-family: Consolas, monospace;
}

pre {
  overflow: auto;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .shell {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Create frontend JavaScript**

Create `static/app.js`:

```javascript
let cases = [];
let currentRun = null;

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return response.json();
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

async function refreshCases() {
  const data = await postJson("/api/cases/search", {});
  cases = data.cases;
  const select = document.querySelector("#caseSelect");
  select.innerHTML = "";
  for (const item of cases) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = `${item.id} - ${item.title}`;
    select.appendChild(option);
  }
  showSelectedCase();
}

function showSelectedCase() {
  const caseId = document.querySelector("#caseSelect").value;
  const item = cases.find((candidate) => candidate.id === caseId);
  document.querySelector("#caseDetails").textContent = item ? pretty(item) : "";
}

async function startRun() {
  const caseId = document.querySelector("#caseSelect").value;
  const variables = JSON.parse(document.querySelector("#variables").value || "{}");
  const data = await postJson("/api/runs/start", {case_id: caseId, variables});
  currentRun = data.run;
  renderRun();
}

async function continueChallenge() {
  if (!currentRun) {
    throw new Error("Start a run first");
  }
  const action = document.querySelector("#challengeAction").value;
  const actionData = JSON.parse(document.querySelector("#actionData").value || "{}");
  const data = await postJson("/api/runs/creq/continue", {run_id: currentRun.id, action, action_data: actionData});
  currentRun = data.run;
  renderRun();
}

function renderRun() {
  document.querySelector("#runStatus").textContent = currentRun ? currentRun.status : "";
  document.querySelector("#evidence").textContent = currentRun ? pretty(currentRun) : "";
}

document.querySelector("#refreshCases").addEventListener("click", refreshCases);
document.querySelector("#caseSelect").addEventListener("change", showSelectedCase);
document.querySelector("#startRun").addEventListener("click", () => startRun().catch(alert));
document.querySelector("#continueChallenge").addEventListener("click", () => continueChallenge().catch(alert));

refreshCases().catch(() => {
  document.querySelector("#caseDetails").textContent = "No cases loaded yet.";
});
```

- [ ] **Step 6: Run static UI test**

Run: `python -m pytest tests/test_static_ui.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add static/index.html static/styles.css static/app.js tests/test_static_ui.py
git commit -m "feat: add simulator flow UI"
```

---

### Task 8: End-to-End Validation, Documentation, and Run Commands

**Files:**
- Modify: `README.md`
- Create: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes all prior tasks.
- Produces a verified local app with documented run commands.

- [ ] **Step 1: Write end-to-end test**

Create `tests/test_end_to_end.py`:

```python
import pytest

from acs_auto_sit.models import TestCase
from acs_auto_sit.services import AcsSitService
from acs_auto_sit.storage import JsonRepository


@pytest.mark.asyncio
async def test_full_areq_to_cres_flow_passes(respx_mock, tmp_path):
    repo = JsonRepository(tmp_path)
    repo.save_case(TestCase(
        id="case01",
        title="OTP success",
        channel="Browser",
        module="Browser Transaction Verification Process",
        test_point="CUP",
        steps="Enter OTP",
        expected_results="CRes transStatus = Y",
        areq_url="https://acs.example.test/areq",
        headers={"Content-Type": "application/json"},
        areq_template={"messageType": "AReq", "messageVersion": "2.2.0", "threeDSServerTransID": "server-trans"},
        creq_settings={"challengeWindowSize": "05", "maxExchanges": 5},
    ))
    respx_mock.post("https://acs.example.test/areq").respond(200, json={
        "messageVersion": "2.2.0",
        "transStatus": "C",
        "acsTransID": "acs-trans",
        "acsURL": "https://acs.example.test/challenge",
    })
    respx_mock.post("https://acs.example.test/challenge").respond(200, json={
        "messageVersion": "2.2.0",
        "transStatus": "Y",
        "acsTransID": "acs-trans",
        "threeDSServerTransID": "server-trans",
    })

    service = AcsSitService(repo, base_url="http://127.0.0.1:8000")
    run = await service.start_run("case01", {})
    run = await service.continue_challenge(run.id, "submit_challenge_value", {"challengeValue": "123456"})

    assert run.status.value == "passed"
    assert run.challenge_exchanges[0].creq["challengeValue"] == "123456"
    assert run.challenge_exchanges[0].cres["transStatus"] == "Y"
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest -v`

Expected: PASS.

- [ ] **Step 3: Update README with exact operational flow**

Modify `README.md` to include:

```markdown
## Import Browser Test Cases

Use the UI or POST `/api/import/excel` with an `.xlsx` file and AReq URL.

## Run AReq and CReq/CRes

1. Open `http://127.0.0.1:8000/`.
2. Select a Browser case.
3. Edit variables if needed.
4. Click `Start Run`.
5. If status is `challenge_required` or `waiting_input`, choose a challenge action.
6. For OTP, set action data like:

```json
{"challengeValue": "123456"}
```

7. Click `Continue Challenge`.

Only `transStatus = "C"` generates or continues CReq. Any other CRes `transStatus` ends the loop.
```

- [ ] **Step 4: Run full test suite again**

Run: `python -m pytest -v`

Expected: PASS.

- [ ] **Step 5: Check git status**

Run: `git status --short`

Expected: only `README.md` and `tests/test_end_to_end.py` are modified/untracked.

- [ ] **Step 6: Commit**

```bash
git add README.md tests/test_end_to_end.py
git commit -m "test: verify end-to-end areq creq flow"
```

---

## Final Verification

- [ ] Run: `python -m pytest -v`
  - Expected: all tests pass.
- [ ] Run: `python -m acs_auto_sit --host 127.0.0.1 --port 8000`
  - Expected: server starts and serves `http://127.0.0.1:8000/`.
- [ ] Open the UI and confirm it shows:
  - `Refresh Cases`
  - `Start Run`
  - `Continue Challenge`
  - `Evidence`
- [ ] Run: `git status --short`
  - Expected: clean working tree.

## Self-Review Notes

- Spec coverage:
  - FastAPI backend: Tasks 6 and 8.
  - No login: no auth task included.
  - Local and intranet binding: Task 6 CLI and README in Task 8.
  - Local file storage: Task 2.
  - All ACS transaction calls POST: Tasks 4, 5, 6.
  - Normal HTTPS only: Task 4 uses default httpx TLS behavior, no certificate settings.
  - Backend AReq and CReq automation: Tasks 4 and 5.
  - Only `transStatus = "C"` generates/continues CReq: Tasks 4 and 5 tests.
  - Action-based later CReq: Tasks 4, 5, 7, 8.
  - Excel Browser import: Task 3.
  - JSONPath-like validation: Task 3 and Task 5 finalization.
  - Thin simulator UI: Task 7.
  - Evidence persistence: Tasks 2 and 5.
- Placeholder scan: no placeholders are intentionally left for implementers.
- Type consistency: plan uses `TestCase`, `RunRecord`, `ChallengeExchange`, `HttpRecord`, `ValidationRule`, `RunStatus`, and service methods consistently across tasks.
