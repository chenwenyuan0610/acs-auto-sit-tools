import pytest

from acs_auto_sit.case_plan import build_case_plan, build_selection_sms_otp_case_plan
from acs_auto_sit.issuer_modes import resolve_issuer_mode
from acs_auto_sit.sit_runner import load_browser_case_catalog


def _generated_case(locale, scenario, destination="sms", kind="selection_branch"):
    return {
        "id": f"ui_{destination}_{scenario}_{locale}",
        "browserLanguage": locale.replace("_", "-"),
        "wordingScenario": scenario,
        "expected": {
            "stageUiFields": {
                "single_select": {"challenge_title": f"select-{locale}"},
                destination: {"challenge_title": f"challenge-{locale}"},
            }
        },
        "flow": {
            "kind": kind,
            "destination": destination,
            "stages": [{"type": "single_select"}, {"type": destination}],
        },
    }


@pytest.mark.parametrize(
    ("scenario", "expected_types"),
    (
        (
            "initial_challenge",
            [
                "send_areq",
                "assert_authentication_mode_page",
                "assert_stage_ui",
                "choose_authentication_mode",
                "assert_otp_page",
                "assert_stage_ui",
            ],
        ),
        (
            "incorrect_otp",
            [
                "send_areq",
                "assert_authentication_mode_page",
                "assert_stage_ui",
                "choose_authentication_mode",
                "assert_otp_page",
                "submit_otp",
                "assert_stage_ui",
            ],
        ),
        (
            "resend_success",
            [
                "send_areq",
                "assert_authentication_mode_page",
                "assert_stage_ui",
                "choose_authentication_mode",
                "assert_otp_page",
                "resend_otp",
                "assert_stage_ui",
            ],
        ),
        (
            "resend_gap_limit",
            [
                "send_areq",
                "assert_authentication_mode_page",
                "assert_stage_ui",
                "choose_authentication_mode",
                "assert_otp_page",
                "resend_otp",
                "assert_stage_ui",
            ],
        ),
        (
            "resend_count_limit",
            [
                "send_areq",
                "assert_authentication_mode_page",
                "assert_stage_ui",
                "choose_authentication_mode",
                "assert_otp_page",
                "resend_until_limit",
                "assert_stage_ui",
            ],
        ),
        (
            "expired_otp",
            [
                "send_areq",
                "assert_authentication_mode_page",
                "assert_stage_ui",
                "choose_authentication_mode",
                "assert_otp_page",
                "wait_otp_expiry",
                "submit_otp",
                "assert_stage_ui",
            ],
        ),
    ),
)
def test_generated_action_registry_maps_scenario_to_reusable_actions(scenario, expected_types):
    plan = build_case_plan(
        _generated_case("en_US", scenario),
        resolve_issuer_mode("selection_sms_email"),
    )

    assert plan["coverage"] == "implemented"
    assert plan["classification"] == "generated"
    assert [action["type"] for action in plan["actions"]] == expected_types


def test_generated_action_plan_does_not_change_with_locale():
    english = build_case_plan(_generated_case("en_US", "incorrect_otp"), resolve_issuer_mode("selection_sms_email"))
    chinese = build_case_plan(_generated_case("zh_CN", "incorrect_otp"), resolve_issuer_mode("selection_sms_email"))

    assert english["actions"] == chinese["actions"]


def test_generated_selection_page_stops_after_single_select_assertion():
    plan = build_case_plan(
        _generated_case("en_US", "initial_challenge", kind="selection_page"),
        resolve_issuer_mode("selection_sms_email"),
    )

    assert [action["type"] for action in plan["actions"]] == [
        "send_areq",
        "assert_authentication_mode_page",
        "assert_stage_ui",
    ]
    assert plan["autoSelectAuthenticationMode"] is False


def test_generated_direct_plan_runs_destination_actions_without_selection():
    plan = build_case_plan(
        _generated_case("en_US", "initial_challenge", kind="direct"),
        resolve_issuer_mode("sms_otp"),
    )

    assert [action["type"] for action in plan["actions"]] == [
        "send_areq",
        "assert_otp_page",
        "assert_stage_ui",
    ]
    assert plan["autoSelectAuthenticationMode"] is False


def test_generated_oob_switch_plan_asserts_oob_then_sms_stage():
    plan = build_case_plan(
        _generated_case("en_US", "initial_challenge", kind="oob_switch_sms"),
        resolve_issuer_mode("default_oob_can_switch_otp"),
    )

    assert [action["type"] for action in plan["actions"]] == [
        "send_areq",
        "assert_oob_page",
        "switch_to_otp",
        "assert_otp_page",
        "assert_stage_ui",
    ]
    assert plan["preferredChallenge"] == "sms"


@pytest.mark.parametrize(
    ("destination", "challenge_value", "label"),
    (("email", "2", "EMAIL"), ("oob", "3", "OOB")),
)
def test_generated_selection_branch_uses_destination_challenge_value(destination, challenge_value, label):
    plan = build_case_plan(
        _generated_case("en_US", "initial_challenge", destination=destination),
        resolve_issuer_mode("selection_sms_email"),
    )

    selection = next(action for action in plan["actions"] if action["type"] == "choose_authentication_mode")

    assert selection["challengeValue"] == challenge_value
    assert selection["label"] == label


def test_generated_unknown_scenario_is_pending_without_mutation_actions():
    plan = build_case_plan(
        _generated_case("en_US", "unknown_scenario"),
        resolve_issuer_mode("selection_sms_email"),
    )

    assert plan["coverage"] == "pending"
    assert "unknown_scenario" in plan["pendingReason"]
    assert not {
        "choose_authentication_mode",
        "submit_otp",
        "resend_otp",
        "resend_until_limit",
        "wait_otp_expiry",
    }.intersection(action["type"] for action in plan["actions"])


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


def test_legacy_selection_case_plan_uses_preferred_oob_destination():
    case = {
        "id": "case04",
        "functionPoint": "Don't enter verification code",
        "expected": {"prompts": ["Enter OTP"]},
        "automation": {"tags": ["prompt"]},
    }

    plan = build_case_plan(
        case,
        resolve_issuer_mode("selection_sms_oob"),
        preferred_challenge="oob",
    )

    assert [action["type"] for action in plan["actions"]] == [
        "send_areq",
        "choose_authentication_mode",
        "assert_oob_page",
        "expect_prompt",
    ]
    selection = plan["actions"][1]
    assert selection["preferredChallenge"] == "oob"
    assert selection["challengeValue"] == "3"
    assert plan["preferredChallenge"] == "oob"


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
