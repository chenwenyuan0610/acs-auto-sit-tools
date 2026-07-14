from acs_auto_sit.case_plan import build_selection_sms_otp_case_plan
from acs_auto_sit.sit_runner import load_browser_case_catalog


def test_selection_sms_otp_case_plan_covers_every_browser_case():
    catalog = load_browser_case_catalog()

    plans = [build_selection_sms_otp_case_plan(case) for case in catalog["cases"]]

    assert len(plans) == 43
    assert {
        "case05",
        "case06",
        "case15",
        "case16",
        "case17",
        "case21",
        "case22",
    }.isdisjoint({plan["caseId"] for plan in plans})
    assert all(plan["mode"] == "selection_sms_otp" for plan in plans)
    assert all(plan["coverage"] == "implemented" for plan in plans)
    assert all(plan["actions"] for plan in plans)


def test_selection_sms_otp_case_plan_chooses_sms_before_otp_actions():
    case = _case_by_id("case02")

    plan = build_selection_sms_otp_case_plan(case)

    assert [action["type"] for action in plan["actions"]] == [
        "send_areq",
        "choose_authentication_mode",
        "submit_otp",
        "submit_otp",
        "expect_cres",
    ]
    selection_action = plan["actions"][1]
    assert selection_action["challengeValue"] == "1"
    assert selection_action["label"] == "SMS"
    assert [action.get("otpPurpose") for action in plan["actions"] if action["type"] == "submit_otp"] == [
        "failure",
        "success",
    ]


def _case_by_id(case_id: str):
    for case in load_browser_case_catalog()["cases"]:
        if case["id"] == case_id:
            return case
    raise AssertionError(f"Missing case {case_id}")
