from acs_auto_sit.case_plan import build_direct_otp_case_plan
from acs_auto_sit.otp_provider import OtpSettings, resolve_otp_value, simulated_otp_for_acs_trans_id
from acs_auto_sit.sit_runner import load_browser_case_catalog


def test_direct_otp_case_plan_covers_every_browser_case():
    catalog = load_browser_case_catalog()

    plans = [build_direct_otp_case_plan(case) for case in catalog["cases"]]

    assert len(plans) == 50
    assert all(plan["mode"] == "direct_otp" for plan in plans)
    assert all(plan["coverage"] == "implemented" for plan in plans)
    assert all(plan["actions"] for plan in plans)


def test_direct_otp_case_plan_uses_failure_then_success_for_recovery_case():
    case = _case_by_id("case02")

    plan = build_direct_otp_case_plan(case)

    assert [action["type"] for action in plan["actions"]] == [
        "send_areq",
        "submit_otp",
        "submit_otp",
        "expect_cres",
    ]
    assert [action.get("otpPurpose") for action in plan["actions"] if action["type"] == "submit_otp"] == [
        "failure",
        "success",
    ]


def test_customer_generated_otp_uses_configured_success_and_failure_values():
    settings = OtpSettings(
        source_mode="customer_generated",
        success_otp="654321",
        failure_otp="000000",
    )

    assert resolve_otp_value("success", "acs-trans-1", settings) == "654321"
    assert resolve_otp_value("failure", "acs-trans-1", settings) == "000000"


def test_acs_generated_otp_uses_simulated_provider_from_acs_trans_id():
    settings = OtpSettings(source_mode="acs_generated")

    otp = resolve_otp_value("success", "acs-trans-1", settings)

    assert otp == simulated_otp_for_acs_trans_id("acs-trans-1")
    assert len(otp) == 6
    assert otp.isdigit()


def _case_by_id(case_id: str):
    for case in load_browser_case_catalog()["cases"]:
        if case["id"] == case_id:
            return case
    raise AssertionError(f"Missing case {case_id}")
