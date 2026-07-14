import pytest

from acs_auto_sit.case_plan import build_case_plan, build_selection_sms_otp_case_plan
from acs_auto_sit.issuer_modes import resolve_issuer_mode
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


@pytest.mark.parametrize(
    ("mode_id", "destination", "challenge_value"),
    (
        ("selection_sms_oob", "sms", "1"),
        ("selection_sms_email", "email", "2"),
        ("selection_email_oob", "oob", "3"),
    ),
)
def test_flow_aware_case_plan_selects_requested_destination(mode_id, destination, challenge_value):
    case = {
        "id": f"ui_select_{destination}",
        "functionPoint": "Generated challenge UI",
        "expected": {"prompts": ["Challenge title"]},
        "wordingScenario": "initial_challenge",
        "flow": {
            "kind": "selection_branch",
            "destination": destination,
            "stages": [{"type": "single_select"}, {"type": destination}],
        },
    }

    plan = build_case_plan(case, resolve_issuer_mode(mode_id))

    selection = next(action for action in plan["actions"] if action["type"] == "choose_authentication_mode")
    assert selection["preferredChallenge"] == destination
    assert selection["challengeValue"] == challenge_value
    assert plan["preferredChallenge"] == destination


def test_flow_aware_case_plan_runs_oob_to_sms_switch_before_otp_submission():
    case = {
        "id": "ui_oob_switch_sms",
        "functionPoint": "Generated OOB switch",
        "expected": {"prompts": ["SMS challenge"]},
        "flow": {
            "kind": "oob_switch_sms",
            "destination": "sms",
            "switchCreq": True,
            "stages": [{"type": "oob"}, {"type": "sms"}],
        },
    }

    plan = build_case_plan(case, resolve_issuer_mode("default_oob_can_switch_otp"))

    action_types = [action["type"] for action in plan["actions"]]
    assert action_types == [
        "send_areq",
        "assert_oob_page",
        "switch_to_otp",
        "lookup_otp",
        "submit_otp",
        "expect_prompt",
    ]
    assert plan["preferredChallenge"] == "sms"


def test_flow_aware_oob_case_does_not_submit_otp():
    case = {
        "id": "ui_oob",
        "functionPoint": "Generated OOB",
        "expected": {"prompts": ["Approve in app"]},
        "flow": {
            "kind": "direct",
            "destination": "oob",
            "stages": [{"type": "oob"}],
        },
    }

    plan = build_case_plan(case, resolve_issuer_mode("direct_oob"))

    assert [action["type"] for action in plan["actions"]] == ["send_areq", "assert_oob_page", "expect_prompt"]
    assert plan["preferredChallenge"] == "oob"


def _case_by_id(case_id: str):
    for case in load_browser_case_catalog()["cases"]:
        if case["id"] == case_id:
            return case
    raise AssertionError(f"Missing case {case_id}")
