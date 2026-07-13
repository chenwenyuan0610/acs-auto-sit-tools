from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TRACKED_ISSUER_MODES = [
    "selection_sms_oob",
    "selection_sms_otp",
    "direct_otp",
    "direct_oob",
    "default_oob_can_switch_otp",
]

PENDING_ISSUER_MODES = [
    "selection_sms_oob",
    "direct_oob",
    "default_oob_can_switch_otp",
]

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


def build_browser_case_progress(
    cases: list[dict[str, Any]],
    records: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    progress_records = load_case_progress_records() if records is None else records
    case_progress = [
        _case_progress(case, progress_records.get(str(case.get("id") or ""), {}))
        for case in cases
    ]
    direct_otp_completed = sum(
        1
        for item in case_progress
        if item["directOtp"]["status"] == "completed"
    )
    selection_sms_otp_completed = sum(
        1
        for item in case_progress
        if item["selectionSmsOtp"]["status"] == "completed"
    )
    return {
        "summary": {
            "total": len(case_progress),
            "directOtpCompleted": direct_otp_completed,
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


def _case_progress(
    case: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    completed_modes = [
        mode
        for mode in record.get("completedModes") or []
        if mode in TRACKED_ISSUER_MODES
    ]
    pending_modes = [mode for mode in TRACKED_ISSUER_MODES if mode not in completed_modes]
    status = "completed" if not pending_modes else "partial" if completed_modes else "pending"

    return {
        "caseId": case.get("id", ""),
        "status": status,
        "completedModes": completed_modes,
        "pendingModes": pending_modes,
        "note": str(record.get("note") or ""),
        "directOtp": {
            "status": "completed" if "direct_otp" in completed_modes else "pending",
            "actionCount": 0,
            "actions": [],
        },
        "selectionSmsOtp": {
            "status": "completed" if "selection_sms_otp" in completed_modes else "pending",
            "actionCount": 0,
            "actions": [],
        },
    }
