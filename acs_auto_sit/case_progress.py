from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acs_auto_sit.case_plan import build_case_plan

TRACKED_ISSUER_MODES = [
    "sms_otp",
    "email_otp",
    "direct_oob",
    "selection_sms_oob",
    "selection_sms_email",
    "selection_sms_email_oob",
    "selection_email_oob",
    "default_oob_can_switch_otp",
]
LEGACY_ISSUER_MODES = ["selection_sms_otp"]
PROGRESS_MODE_ALIASES = {"direct_otp": "sms_otp"}

PENDING_ISSUER_MODES = [mode for mode in TRACKED_ISSUER_MODES if mode != "sms_otp"]

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
        raise ValueError(
            f"Invalid case progress structure in {path}: cases must be an object"
        )

    records: dict[str, dict[str, Any]] = {}
    for case_id, record in payload["cases"].items():
        if not isinstance(case_id, str) or not isinstance(record, dict):
            continue
        completed_modes = _canonical_completed_modes(record.get("completedModes") or [])
        records[case_id] = {
            "completedModes": completed_modes,
            "note": str(record.get("note") or ""),
        }
    return records


def build_browser_case_progress(
    cases: list[dict[str, Any]],
    records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    progress_records = load_case_progress_records() if records is None else records
    case_progress = [
        _case_progress(case, progress_records.get(str(case.get("id") or ""), {}))
        for case in cases
    ]
    sms_otp_completed = sum(
        1
        for item in case_progress
        if item["smsOtp"]["status"] == "completed"
    )
    selection_sms_otp_completed = sum(
        1
        for item in case_progress
        if item["selectionSmsOtp"]["status"] == "completed"
    )
    return {
        "summary": {
            "total": len(case_progress),
            "smsOtpCompleted": sms_otp_completed,
            "directOtpCompleted": sms_otp_completed,
            "selectionSmsOtpCompleted": selection_sms_otp_completed,
            "allModesCompleted": 0,
            "pendingIssuerModes": list(PENDING_ISSUER_MODES),
        },
        "cases": case_progress,
    }


def case_progress_by_id(
    cases: list[dict[str, Any]],
    records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    progress = build_browser_case_progress(cases, records)
    return {item["caseId"]: item for item in progress["cases"]}


def generated_case_implementation(
    case: dict[str, Any], issuer_mode: dict[str, Any]
) -> dict[str, Any]:
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


def _case_progress(
    case: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    completed_modes = _canonical_completed_modes(record.get("completedModes") or [])
    pending_modes = [mode for mode in TRACKED_ISSUER_MODES if mode not in completed_modes]
    status = "completed" if not pending_modes else "partial" if completed_modes else "pending"

    return {
        "caseId": case.get("id", ""),
        "status": status,
        "completedModes": completed_modes,
        "pendingModes": pending_modes,
        "note": str(record.get("note") or ""),
        "directOtp": {
            "status": "completed" if "sms_otp" in completed_modes else "pending",
            "actionCount": 0,
            "actions": [],
        },
        "smsOtp": {
            "status": "completed" if "sms_otp" in completed_modes else "pending",
            "actionCount": 0,
            "actions": [],
        },
        "selectionSmsOtp": {
            "status": "completed" if "selection_sms_otp" in completed_modes else "pending",
            "actionCount": 0,
            "actions": [],
        },
    }


def _canonical_completed_modes(modes: list[Any]) -> list[str]:
    completed: list[str] = []
    allowed = set(TRACKED_ISSUER_MODES + LEGACY_ISSUER_MODES)
    for value in modes:
        mode = PROGRESS_MODE_ALIASES.get(str(value), str(value))
        if mode in allowed and mode not in completed:
            completed.append(mode)
    return completed
