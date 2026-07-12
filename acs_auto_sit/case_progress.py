from __future__ import annotations

from typing import Any

from acs_auto_sit.case_plan import build_direct_otp_case_plan, build_selection_sms_otp_case_plan


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


def build_browser_case_progress(cases: list[dict[str, Any]]) -> dict[str, Any]:
    case_progress = [_case_progress(case) for case in cases]
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


def case_progress_by_id(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    progress = build_browser_case_progress(cases)
    return {item["caseId"]: item for item in progress["cases"]}


def _case_progress(case: dict[str, Any]) -> dict[str, Any]:
    direct_otp_plan = build_direct_otp_case_plan(case)
    selection_sms_otp_plan = build_selection_sms_otp_case_plan(case)
    direct_otp_done = direct_otp_plan.get("coverage") == "implemented" and bool(direct_otp_plan.get("actions"))
    selection_sms_otp_done = (
        selection_sms_otp_plan.get("coverage") == "implemented"
        and bool(selection_sms_otp_plan.get("actions"))
    )
    completed_modes = []
    if direct_otp_done:
        completed_modes.append("direct_otp")
    if selection_sms_otp_done:
        completed_modes.append("selection_sms_otp")
    pending_modes = [mode for mode in TRACKED_ISSUER_MODES if mode not in completed_modes]
    status = "completed" if not pending_modes else "partial" if completed_modes else "pending"

    return {
        "caseId": case.get("id", ""),
        "status": status,
        "completedModes": completed_modes,
        "pendingModes": pending_modes,
        "directOtp": {
            "status": "completed" if direct_otp_done else "pending",
            "actionCount": len(direct_otp_plan.get("actions") or []),
            "actions": direct_otp_plan.get("actions") or [],
        },
        "selectionSmsOtp": {
            "status": "completed" if selection_sms_otp_done else "pending",
            "actionCount": len(selection_sms_otp_plan.get("actions") or []),
            "actions": selection_sms_otp_plan.get("actions") or [],
        },
    }
