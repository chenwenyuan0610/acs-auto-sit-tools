import json

import pytest

from acs_auto_sit.case_progress import (
    TRACKED_ISSUER_MODES,
    build_browser_case_progress,
    generated_case_implementation,
    load_case_progress_records,
)
from acs_auto_sit.issuer_modes import resolve_issuer_mode
from acs_auto_sit.sit_runner import (
    DEFAULT_OOB_BROWSER_CASES_PATH,
    browser_catalog_path,
    effective_preferred_challenge,
    live_skip_reason,
    load_browser_case_catalog,
)


def _generated_case_with_flow_and_scenario(scenario: str) -> dict:
    return {
        "id": f"ui_sms_{scenario}",
        "wordingScenario": scenario,
        "wording": {"code": "SEND_SMS_OTP"},
        "flow": {"kind": "direct", "destination": "sms", "stages": []},
        "availability": {"enabled": True, "reason": ""},
    }


@pytest.mark.parametrize(
    ("issuer_mode_id", "preferred_challenge", "expected"),
    [
        ("direct_oob", "auto", "oob"),
        ("selection_sms_oob", "oob", "oob"),
        ("selection_sms_oob", "auto", "sms"),
        ("selection_sms_email_oob", "email", "email"),
    ],
)
def test_effective_preferred_challenge_resolves_explicit_and_auto_values(
    issuer_mode_id, preferred_challenge, expected
):
    assert effective_preferred_challenge(
        resolve_issuer_mode(issuer_mode_id), preferred_challenge
    ) == expected


def test_browser_catalog_path_selects_oob_catalog_for_effective_oob():
    assert (
        browser_catalog_path(resolve_issuer_mode("direct_oob"), "auto")
        == DEFAULT_OOB_BROWSER_CASES_PATH
    )


def test_browser_catalog_path_preserves_caller_otp_path_for_effective_sms(tmp_path):
    otp_path = tmp_path / "otp-cases.json"

    assert (
        browser_catalog_path(
            resolve_issuer_mode("selection_sms_oob"), "auto", otp_path=otp_path
        )
        == otp_path
    )


def test_direct_oob_auto_loads_the_complete_oob_catalog(tmp_path):
    catalog = load_browser_case_catalog(
        progress_path=tmp_path / "missing-progress.json",
        issuer_mode="direct_oob",
    )

    assert [case["id"] for case in catalog["cases"]] == [
        f"oob{number:02d}" for number in range(1, 14)
    ]
    assert {case["challengeType"] for case in catalog["cases"]} == {"oob"}


def test_selection_sms_oob_switches_between_independent_oob_and_otp_catalogs(tmp_path):
    oob_catalog = load_browser_case_catalog(
        progress_path=tmp_path / "missing-progress.json",
        issuer_mode="selection_sms_oob",
        preferred_challenge="oob",
    )
    otp_catalog = load_browser_case_catalog(
        progress_path=tmp_path / "missing-progress.json",
        issuer_mode="selection_sms_oob",
        preferred_challenge="sms",
    )

    oob_ids = {case["id"] for case in oob_catalog["cases"]}
    otp_ids = {case["id"] for case in otp_catalog["cases"]}
    assert oob_ids.isdisjoint(otp_ids)
    assert otp_catalog["cases"][0]["id"] == "case01"


def test_invalid_selected_oob_catalog_raises_without_falling_back_to_otp(tmp_path):
    malformed_oob_path = tmp_path / "oob-cases.json"
    malformed_oob_path.write_text(json.dumps({"caseCount": 13, "cases": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid OOB Browser catalog"):
        load_browser_case_catalog(
            progress_path=tmp_path / "missing-progress.json",
            issuer_mode="direct_oob",
            oob_path=malformed_oob_path,
        )


def test_oob_catalog_rejects_duplicate_case_ids_even_when_expected_ids_exist(tmp_path):
    cases = [
        {"id": f"oob{number:02d}", "challengeType": "oob"}
        for number in range(1, 14)
    ]
    cases.append({"id": "oob01", "challengeType": "oob"})
    oob_path = tmp_path / "duplicate-oob-cases.json"
    oob_path.write_text(
        json.dumps({"caseCount": 13, "cases": cases}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Invalid OOB Browser catalog"):
        load_browser_case_catalog(
            progress_path=tmp_path / "missing-progress.json",
            issuer_mode="direct_oob",
            oob_path=oob_path,
        )


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


def test_normalized_generated_case_without_flow_uses_generated_implementation(monkeypatch, tmp_path):
    generated_case = {
        "id": "case23_zh_TW",
        "baseCaseId": "case23",
        "wordingScenario": "initial_challenge",
        "wording": {"code": "SEND_SMS_OTP"},
        "availability": {"enabled": True, "reason": ""},
    }
    monkeypatch.setattr(
        "acs_auto_sit.sit_runner.build_localized_wording_cases",
        lambda *args, **kwargs: [generated_case],
    )
    monkeypatch.setattr(
        "acs_auto_sit.sit_runner.load_wording_profiles",
        lambda path: {"issuers": {"default": {"id": "default", "supportedLocales": ["zh_TW"]}}},
    )

    catalog = load_browser_case_catalog(
        progress_path=tmp_path / "missing-progress.json",
        wording_profiles_path=tmp_path / "wording_profiles.json",
    )

    generated = next(case for case in catalog["cases"] if case["id"] == "case23_zh_TW")
    implementation = generated["caseImplementation"]
    assert implementation["status"] == "pending"
    assert "unsupported generated flow" in implementation["note"].lower()


def test_normalized_generated_case_without_flow_is_skipped_live():
    case = {
        "id": "case23_zh_TW",
        "baseCaseId": "case23",
        "wordingScenario": "initial_challenge",
        "wording": {"code": "SEND_SMS_OTP"},
        "availability": {"enabled": True, "reason": ""},
    }

    reason = live_skip_reason(case, resolve_issuer_mode("sms_otp"))

    assert reason is not None
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
