import json

import pytest

from acs_auto_sit.case_progress import (
    TRACKED_ISSUER_MODES,
    build_browser_case_progress,
    generated_case_implementation,
    load_case_progress_records,
)
from acs_auto_sit.issuer_modes import resolve_issuer_mode
from acs_auto_sit.sit_runner import live_skip_reason, load_browser_case_catalog


def _generated_case_with_flow_and_scenario(scenario: str) -> dict:
    return {
        "id": f"ui_sms_{scenario}",
        "wordingScenario": scenario,
        "wording": {"code": "SEND_SMS_OTP"},
        "flow": {"kind": "direct", "destination": "sms", "stages": []},
        "availability": {"enabled": True, "reason": ""},
    }


def test_load_case_progress_records_reads_case_modes_and_ignores_unknown_modes(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "trackedIssuerModes": TRACKED_ISSUER_MODES,
                "cases": {
                    "case01": {
                        "completedModes": ["direct_otp", "not_a_mode"],
                        "note": "direct flow complete",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    records = load_case_progress_records(path)

    assert records == {
        "case01": {
            "completedModes": ["sms_otp"],
            "note": "direct flow complete",
        }
    }


def test_load_case_progress_records_returns_empty_for_missing_file(tmp_path):
    assert load_case_progress_records(tmp_path / "missing.json") == {}


def test_load_case_progress_records_reports_invalid_json(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid case progress JSON"):
        load_case_progress_records(path)


def test_build_browser_case_progress_defaults_missing_cases_to_pending():
    progress = build_browser_case_progress(
        [{"id": "case01"}, {"id": "case02"}],
        {"case01": {"completedModes": ["direct_otp"]}},
    )

    assert progress["cases"][0]["completedModes"] == ["sms_otp"]
    assert progress["cases"][1]["status"] == "pending"
    assert progress["summary"]["smsOtpCompleted"] == 1


def test_generated_case_progress_comes_from_action_capability():
    case = _generated_case_with_flow_and_scenario("incorrect_otp")

    implementation = generated_case_implementation(
        case,
        resolve_issuer_mode("selection_sms_email_oob"),
    )

    assert implementation["status"] == "completed"
    assert implementation["actionCount"] > 0
    assert implementation["actions"][0]["type"] == "send_areq"


def test_pending_generated_case_is_skipped_before_base_case_fallback():
    case = {
        "id": "ui_unknown",
        "baseCaseId": "case23",
        "wordingScenario": "unknown",
        "wording": {"code": "UNKNOWN"},
        "flow": {"kind": "selection_branch", "destination": "sms", "stages": []},
        "automation": {"status": "manual_or_slow"},
        "availability": {"enabled": True, "reason": ""},
    }

    reason = live_skip_reason(case, resolve_issuer_mode("selection_sms_email_oob"))

    assert "not implemented" in reason.lower()


def test_browser_case_catalog_uses_progress_file(tmp_path):
    progress_path = tmp_path / "progress.json"
    progress_path.write_text(
        json.dumps(
            {
                "version": 1,
                "trackedIssuerModes": TRACKED_ISSUER_MODES,
                "cases": {
                    "case01": {
                        "completedModes": ["direct_otp"],
                        "note": "",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    catalog = load_browser_case_catalog(progress_path=progress_path)

    implementation = catalog["cases"][0]["caseImplementation"]
    assert implementation["directOtp"]["status"] == "completed"
    assert implementation["selectionSmsOtp"]["status"] == "pending"


def test_browser_case_progress_marks_completed_otp_modes_done_for_all_cases():
    catalog = load_browser_case_catalog()

    progress = build_browser_case_progress(catalog["cases"])

    assert progress["summary"]["total"] == 43
    assert progress["summary"]["directOtpCompleted"] == 43
    assert progress["summary"]["selectionSmsOtpCompleted"] == 43
    assert progress["summary"]["pendingIssuerModes"] == [
        "email_otp",
        "direct_oob",
        "selection_sms_oob",
        "selection_sms_email",
        "selection_sms_email_oob",
        "selection_email_oob",
        "default_oob_can_switch_otp",
    ]
    assert all(item["directOtp"]["status"] == "completed" for item in progress["cases"])
    assert all(item["selectionSmsOtp"]["status"] == "completed" for item in progress["cases"])


def test_browser_case_catalog_excludes_deleted_cases():
    catalog = load_browser_case_catalog()

    assert catalog["caseCount"] == 43
    assert {
        "case05",
        "case06",
        "case15",
        "case16",
        "case17",
        "case21",
        "case22",
    }.isdisjoint({case["id"] for case in catalog["cases"]})


def test_browser_case_progress_exposes_pending_modes_per_case():
    catalog = load_browser_case_catalog()

    progress = build_browser_case_progress(catalog["cases"])

    first_case = progress["cases"][0]
    assert first_case["caseId"] == "case01"
    assert first_case["status"] == "partial"
    assert first_case["completedModes"] == ["sms_otp", "selection_sms_otp"]
    assert "selection_sms_oob" in first_case["pendingModes"]
