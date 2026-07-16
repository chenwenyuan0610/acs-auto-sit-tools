from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acs_auto_sit.case_progress import (
    DEFAULT_CASE_PROGRESS_PATH,
    build_browser_case_progress,
    generated_case_implementation,
    load_case_progress_records,
)
from acs_auto_sit.case_plan import build_case_plan
from acs_auto_sit.issuer_modes import resolve_issuer_mode
from acs_auto_sit.wording_profiles import (
    build_localized_wording_cases,
    load_wording_profiles,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BROWSER_CASES_PATH = PROJECT_ROOT / "sit_cases" / "pipay_cup_browser_cases.json"
LIVE_RUNNER_SUPPORTED_CASE_IDS = {
    "case01",
    "case02",
    "case03",
    "case04",
    "case07",
    "case08",
    "case09",
    "case10",
    "case11",
    "case12",
    "case14",
    "case18",
    "case19",
    "case20",
    "case23",
    "case24",
    "case25",
    "case26",
    "case27",
    "case28",
    "case29",
    "case30",
    "case31",
    "case32",
    "case33",
    "case34",
    "case35",
    "case36",
    "case37",
    "case38",
    "case39",
    "case40",
    "case41",
    "case42",
    "case43",
    "case44",
    "case45",
    "case46",
}

LIVE_RUNNER_EXCLUDED_CASE_REASONS = {
    "case47": "Case is not included in this live run (manual_or_slow: OTP expiration wait).",
    "case48": "Case is not included in this live run (manual_or_slow: OTP expiration wait).",
    "case49": "Case is not included in this live run (manual_or_slow: OTP expiration wait).",
    "case50": "Case is not included in this live run (manual_or_slow: OTP expiration wait).",
}


def load_browser_case_catalog(
    path: Path = DEFAULT_BROWSER_CASES_PATH,
    progress_path: Path = DEFAULT_CASE_PROGRESS_PATH,
    wording_profiles_path: Path | None = None,
    issuer_id: str = "default",
    issuer_mode: str = "direct_otp",
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "sourceWorkbook": "",
            "sheet": "Browser",
            "caseCount": 0,
            "cases": [],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    source_cases = data.get("cases") or []
    profiles = load_wording_profiles(wording_profiles_path) if wording_profiles_path else None
    wording_profile = {
        "enabled": False,
        "issuerId": issuer_id,
        "issuerMode": issuer_mode,
        "supportedLocales": [],
    }
    if profiles:
        legacy_wording_ids = {
            f"case{number:02d}"
            for number in range(23, 51)
        }
        generated = build_localized_wording_cases(
            profiles,
            source_cases,
            issuer_id=issuer_id,
            issuer_mode=issuer_mode,
        )
        source_cases = [case for case in source_cases if case.get("id") not in legacy_wording_ids] + generated
        selected_issuer = (profiles.get("issuers") or {}).get(issuer_id) or (profiles.get("issuers") or {}).get("default") or {}
        wording_profile = {
            "enabled": True,
            "issuerId": str(selected_issuer.get("id") or issuer_id),
            "issuerMode": issuer_mode,
            "supportedLocales": list(selected_issuer.get("supportedLocales") or []),
        }
    cases = [_case_summary(case) for case in source_cases]
    progress = build_browser_case_progress(
        cases,
        load_case_progress_records(progress_path),
    )
    progress_by_id = {item["caseId"]: item for item in progress["cases"]}
    resolved_issuer_mode = resolve_issuer_mode(issuer_mode)
    cases = [
        {
            **case,
            "caseImplementation": (
                generated_case_implementation(case, resolved_issuer_mode)
                if "flow" in case and "wording" in case
                else progress_by_id.get(case["id"], {})
            ),
        }
        for case in cases
    ]
    return {
        "sourceWorkbook": data.get("sourceWorkbook", ""),
        "sheet": "Browser",
        "caseCount": len(cases),
        "caseProgress": progress["summary"],
        "wordingProfile": wording_profile,
        "cases": cases,
    }


def dry_run_cases(case_ids: list[str], path: Path = DEFAULT_BROWSER_CASES_PATH) -> list[dict[str, Any]]:
    catalog = load_browser_case_catalog(path)
    cases_by_id = {case["id"]: case for case in catalog["cases"]}
    results: list[dict[str, Any]] = []

    for case_id in case_ids:
        case = cases_by_id.get(case_id)
        if not case:
            results.append(
                {
                    "caseId": case_id,
                    "status": "error",
                    "reason": "Case ID was not found in the Browser SIT catalog.",
                    "case": None,
                    "details": {},
                }
            )
            continue

        automation_status = case.get("automation", {}).get("status", "")
        reason = "Dry run only; live execution was not requested."
        if automation_status != "automatable":
            reason = f"Case automation status is {automation_status}; live execution is not supported yet."

        results.append(
            {
                "caseId": case_id,
                "status": "skipped",
                "reason": reason,
                "case": case,
                "details": {
                    "expected": case.get("expected", {}),
                    "automation": case.get("automation", {}),
                },
            }
        )
    return results


def browser_cases_by_id(
    path: Path = DEFAULT_BROWSER_CASES_PATH,
    *,
    wording_profiles_path: Path | None = None,
    issuer_id: str = "default",
    issuer_mode: str = "direct_otp",
) -> dict[str, dict[str, Any]]:
    catalog = load_browser_case_catalog(
        path,
        wording_profiles_path=wording_profiles_path,
        issuer_id=issuer_id,
        issuer_mode=issuer_mode,
    )
    return {case["id"]: case for case in catalog["cases"]}


def live_skip_reason(
    case: dict[str, Any], issuer_mode: dict[str, Any] | None = None
) -> str | None:
    availability = case.get("availability") or {}
    if availability.get("enabled") is False:
        return str(availability.get("reason") or "Case wording is not configured.")

    if "flow" in case and "wording" in case:
        plan = build_case_plan(case, issuer_mode or resolve_issuer_mode(None))
        if plan.get("coverage") != "implemented":
            pending_reason = str(plan.get("pendingReason") or "Generated UI flow is not implemented.")
            return f"Generated UI flow is not implemented: {pending_reason}"

    case_id = str(case.get("baseCaseId") or case.get("id") or "")
    if case_id in LIVE_RUNNER_EXCLUDED_CASE_REASONS:
        return LIVE_RUNNER_EXCLUDED_CASE_REASONS[case_id]
    if case_id in LIVE_RUNNER_SUPPORTED_CASE_IDS:
        return None

    automation = case.get("automation") or {}
    automation_status = str(automation.get("status") or "")
    if automation_status != "automatable":
        return f"Case automation status is {automation_status}; live execution is not supported yet."

    tags = set(automation.get("tags") or [])
    expected_messages = case.get("expected", {}).get("messages", {})
    expected_cres = expected_messages.get("CRes", {})
    unsupported_tags = {"retry", "invalid_card", "cancel", "timeout", "error", "prompt", "currency", "3ri"}
    if tags.intersection(unsupported_tags):
        return "Live runner currently supports only simple browser OTP success cases."
    if expected_cres.get("transStatus") != "Y":
        return "Live runner currently supports only CRes transStatus=Y expectations."
    if "otp" not in tags or "challenge" not in tags:
        return "Live runner currently supports only OTP challenge cases."
    return None


def _case_summary(case: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "sheet": case.get("sheet", "Browser"),
        "channel": case.get("channel", "browser"),
        "id": case.get("id", ""),
        "system": case.get("system", ""),
        "module": case.get("module", ""),
        "functionPoint": case.get("functionPoint", ""),
        "testPoint": case.get("testPoint", ""),
        "steps": case.get("steps", []),
        "expected": case.get("expected", {}),
        "automation": case.get("automation", {}),
        "source": case.get("source", {}),
        "status": "pending",
    }
    for key in (
        "baseCaseId",
        "locale",
        "browserLanguage",
        "wordingScenario",
        "wording",
        "flow",
        "availability",
    ):
        if key in case:
            summary[key] = case[key]
    return summary
