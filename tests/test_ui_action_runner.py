from __future__ import annotations

from typing import Any

from acs_auto_sit.ui_action_runner import ActionContext, execute_generated_actions


def _page(page_type: str, *, resend: bool = False, switch: bool = False) -> dict[str, Any]:
    return {
        "type": page_type,
        "fields": {},
        "availableActions": {"resendOtp": resend, "switchToOtp": switch},
        "visibleText": [page_type],
    }


def _context(pages: list[dict[str, Any]]):
    submitted: list[dict[str, str]] = []
    sleeps: list[float] = []
    remaining = iter(pages)

    def submit(page: dict[str, Any], overrides: dict[str, str]) -> dict[str, Any]:
        submitted.append(overrides)
        try:
            next_page = next(remaining)
        except StopIteration:
            next_page = None
        return {"challenge": next_page, "cres": (next_page or {}).get("cres")}

    context = ActionContext(
        page=None,
        stage_fields={},
        submit_form=submit,
        resolve_otp=lambda purpose, page: (
            "000000" if purpose == "failure" else "654321",
            {"source": "test"},
        ),
        sleep=sleeps.append,
    )
    return context, submitted, sleeps


def test_selection_sms_incorrect_otp_executes_actions_in_order():
    context, submitted, _ = _context([_page("otp"), _page("otp")])
    context.page = _page("authentication_mode")
    actions = [
        {"type": "send_areq"},
        {"type": "assert_authentication_mode_page"},
        {"type": "assert_stage_ui", "stage": "single_select"},
        {"type": "choose_authentication_mode", "challengeValue": "1"},
        {"type": "assert_otp_page"},
        {"type": "submit_otp", "otpPurpose": "failure"},
        {"type": "assert_stage_ui", "stage": "sms"},
    ]

    result = execute_generated_actions(context, actions)

    assert [item["type"] for item in result["actionResults"]] == [
        "assert_authentication_mode_page",
        "assert_stage_ui",
        "choose_authentication_mode",
        "assert_otp_page",
        "submit_otp",
        "assert_stage_ui",
    ]
    assert submitted == [{"challengeValue": "1"}, {"challengeValue": "000000"}]
    assert result["classification"] == "passed"


def test_selection_branch_fails_before_submit_when_otp_returned_directly():
    context, submitted, _ = _context([])
    context.page = _page("otp")

    result = execute_generated_actions(
        context,
        [{"type": "assert_authentication_mode_page"}, {"type": "choose_authentication_mode", "challengeValue": "1"}],
    )

    assert result["classification"] == "assertion_failed"
    assert result["failedAction"]["type"] == "assert_authentication_mode_page"
    assert submitted == []


def test_selection_page_only_plan_does_not_submit_form():
    context, submitted, _ = _context([])
    context.page = _page("authentication_mode")

    result = execute_generated_actions(
        context,
        [{"type": "assert_authentication_mode_page"}, {"type": "assert_stage_ui", "stage": "single_select"}],
    )

    assert result["classification"] == "passed"
    assert submitted == []


def test_email_selection_uses_challenge_value_two():
    context, submitted, _ = _context([_page("otp")])
    context.page = _page("authentication_mode")

    result = execute_generated_actions(
        context,
        [{"type": "choose_authentication_mode", "challengeValue": "2"}, {"type": "assert_otp_page"}],
    )

    assert result["classification"] == "passed"
    assert submitted == [{"challengeValue": "2"}]


def test_resend_otp_uses_configured_delay_and_updates_stage_page():
    context, submitted, sleeps = _context([{"type": "otp", "visibleText": ["new message"], "availableActions": {"resendOtp": True}}])
    context.page = _page("otp", resend=True)
    context.resend_delay_seconds = 30
    context.stage_fields = {"sms": {"message": "new message"}}

    result = execute_generated_actions(
        context,
        [{"type": "resend_otp", "delayMode": "configured"}, {"type": "assert_stage_ui", "stage": "sms"}],
    )

    assert result["classification"] == "passed"
    assert submitted == [{"resendCode": "Y"}]
    assert sleeps == [30]
    assert result["actionResults"][-1]["fieldResults"][0]["found"] is True


def test_resend_gap_limit_does_not_sleep():
    context, submitted, sleeps = _context([_page("otp")])
    context.page = _page("otp", resend=True)
    context.resend_delay_seconds = 30

    result = execute_generated_actions(context, [{"type": "resend_otp", "delaySeconds": 0}])

    assert result["classification"] == "passed"
    assert submitted == [{"resendCode": "Y"}]
    assert sleeps == []


def test_resend_until_limit_stops_when_control_disappears():
    context, submitted, sleeps = _context([
        _page("otp", resend=True),
        _page("otp", resend=True),
        _page("otp", resend=False),
    ])
    context.page = _page("otp", resend=True)
    context.resend_delay_seconds = 30
    context.resend_max_attempts = 10

    result = execute_generated_actions(context, [{"type": "resend_until_limit"}])

    assert result["classification"] == "passed"
    assert submitted == [{"resendCode": "Y"}] * 3
    assert sleeps == [30, 30, 30]


def test_resend_until_limit_fails_at_safety_maximum():
    context, _, _ = _context([_page("otp", resend=True), _page("otp", resend=True)])
    context.page = _page("otp", resend=True)
    context.resend_max_attempts = 2

    result = execute_generated_actions(context, [{"type": "resend_until_limit"}])

    assert result["classification"] == "assertion_failed"
    assert "Safety max" in result["failedAction"]["reason"]


def test_direct_oob_asserts_without_submitting():
    context, submitted, _ = _context([])
    context.page = _page("oob")

    result = execute_generated_actions(context, [{"type": "assert_oob_page"}])

    assert result["classification"] == "passed"
    assert submitted == []


def test_continue_oob_submits_continue_control():
    context, submitted, _ = _context([_page("oob")])
    context.page = _page("oob")

    result = execute_generated_actions(context, [{"type": "continue_oob"}])

    assert result["classification"] == "passed"
    assert submitted == [{"oobContinue": "Y"}]


def test_oob_switch_sms_reuses_sms_stage_actions():
    context, submitted, _ = _context([_page("otp"), _page("cres")])
    context.page = _page("oob", switch=True)
    context.stage_fields = {"oob": {}, "sms": {}}

    result = execute_generated_actions(
        context,
        [
            {"type": "assert_oob_page"},
            {"type": "assert_stage_ui", "stage": "oob"},
            {"type": "switch_to_otp"},
            {"type": "assert_otp_page"},
            {"type": "submit_otp", "otpPurpose": "success"},
            {"type": "assert_stage_ui", "stage": "sms"},
        ],
    )

    assert result["classification"] == "passed"
    assert submitted == [{"isForceOTP": "true"}, {"challengeValue": "654321"}]
    assert [
        item.get("stage")
        for item in result["actionResults"]
        if item["type"] == "assert_stage_ui"
    ] == ["oob", "sms"]


def test_oob_assertion_rejects_otp_before_submit():
    context, submitted, _ = _context([])
    context.page = _page("otp")

    result = execute_generated_actions(
        context,
        [{"type": "assert_oob_page"}, {"type": "switch_to_otp"}],
    )

    assert result["classification"] == "assertion_failed"
    assert submitted == []


def test_wait_otp_expiry_uses_configured_context_wait():
    context, submitted, sleeps = _context([_page("otp")])
    context.page = _page("otp")
    context.expiry_wait_seconds = 120

    result = execute_generated_actions(
        context,
        [{"type": "wait_otp_expiry"}, {"type": "submit_otp", "otpPurpose": "expired"}],
    )

    assert result["classification"] == "passed"
    assert sleeps == [120]
    assert submitted == [{"challengeValue": "654321"}]
