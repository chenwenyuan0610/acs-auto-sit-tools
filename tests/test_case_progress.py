from acs_auto_sit.case_progress import build_browser_case_progress
from acs_auto_sit.sit_runner import load_browser_case_catalog


def test_browser_case_progress_marks_completed_otp_modes_done_for_all_cases():
    catalog = load_browser_case_catalog()

    progress = build_browser_case_progress(catalog["cases"])

    assert progress["summary"]["total"] == 50
    assert progress["summary"]["directOtpCompleted"] == 50
    assert progress["summary"]["selectionSmsOtpCompleted"] == 50
    assert progress["summary"]["pendingIssuerModes"] == [
        "selection_sms_oob",
        "direct_oob",
        "default_oob_can_switch_otp",
    ]
    assert all(item["directOtp"]["status"] == "completed" for item in progress["cases"])
    assert all(item["selectionSmsOtp"]["status"] == "completed" for item in progress["cases"])


def test_browser_case_progress_exposes_pending_modes_per_case():
    catalog = load_browser_case_catalog()

    progress = build_browser_case_progress(catalog["cases"])

    first_case = progress["cases"][0]
    assert first_case["caseId"] == "case01"
    assert first_case["status"] == "partial"
    assert first_case["completedModes"] == ["direct_otp", "selection_sms_otp"]
    assert "selection_sms_oob" in first_case["pendingModes"]
