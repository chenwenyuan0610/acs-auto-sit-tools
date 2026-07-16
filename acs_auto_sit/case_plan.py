from __future__ import annotations

from typing import Any


CHALLENGE_VALUES = {"sms": "1", "email": "2", "oob": "3"}
GENERATED_SCENARIOS = {
    "initial_challenge",
    "incorrect_otp",
    "resend_success",
    "resend_gap_limit",
    "resend_count_limit",
    "expired_otp",
}


def build_case_plan(case: dict[str, Any], issuer_mode: dict[str, Any]) -> dict[str, Any]:
    flow = case.get("flow") or {}
    if "wordingScenario" in case:
        return _build_generated_case_plan(case, issuer_mode)
    if not flow:
        if str(issuer_mode.get("id") or "").startswith("selection_"):
            return build_selection_sms_otp_case_plan(case)
        return build_direct_otp_case_plan(case)

    kind = str(flow.get("kind") or "")
    destination = str(flow.get("destination") or "")
    if kind == "selection_page":
        actions = [
            {"type": "send_areq"},
            {"type": "assert_authentication_mode_page"},
            {"type": "expect_prompt"},
        ]
        return _flow_plan(case, issuer_mode, actions, "auto", auto_select=False)

    if kind == "oob_switch_sms":
        actions = [
            {"type": "send_areq"},
            {"type": "assert_oob_page"},
            {"type": "switch_to_otp"},
            {"type": "lookup_otp"},
            {"type": "submit_otp", "otpPurpose": "success"},
            {"type": "expect_prompt"},
        ]
        return _flow_plan(case, issuer_mode, actions, "sms")

    selection_actions: list[dict[str, Any]] = []
    if kind == "selection_branch":
        selection_actions.append(
            {
                "type": "choose_authentication_mode",
                "preferredChallenge": destination,
                "challengeValue": CHALLENGE_VALUES.get(destination, ""),
                "label": destination.upper(),
            }
        )

    if destination == "oob":
        actions = [
            {"type": "send_areq"},
            *selection_actions,
            {"type": "assert_oob_page"},
            {"type": "expect_prompt"},
        ]
    else:
        direct_actions = build_direct_otp_case_plan(case).get("actions") or []
        actions = []
        for action in direct_actions:
            actions.append(action)
            if action.get("type") == "send_areq":
                actions.extend(selection_actions)
    return _flow_plan(
        case,
        issuer_mode,
        actions,
        destination or str(issuer_mode.get("defaultPreferredChallenge") or "auto"),
        auto_select=kind == "selection_branch",
    )


def _generated_destination_actions(destination: str, scenario: str) -> list[dict[str, Any]] | None:
    if destination == "oob":
        if scenario != "initial_challenge":
            return None
        return [
            {"type": "assert_oob_page"},
            {"type": "assert_stage_ui", "stage": "oob"},
        ]

    actions: list[dict[str, Any]] = [
        {"type": "assert_otp_page"},
    ]
    if scenario == "incorrect_otp":
        actions.append({"type": "submit_otp", "otpPurpose": "failure"})
    elif scenario == "resend_success":
        actions.append({"type": "resend_otp", "delayMode": "configured"})
    elif scenario == "resend_gap_limit":
        actions.append({"type": "resend_otp", "delaySeconds": 0})
    elif scenario == "resend_count_limit":
        actions.append({"type": "resend_until_limit"})
    elif scenario == "expired_otp":
        actions.extend(
            [
                {"type": "wait_otp_expiry"},
                {"type": "submit_otp", "otpPurpose": "expired"},
            ]
        )
    elif scenario != "initial_challenge":
        return None
    actions.append({"type": "assert_stage_ui", "stage": destination})
    return actions


def _generated_plan(
    case: dict[str, Any],
    issuer_mode: dict[str, Any],
    actions: list[dict[str, Any]],
    preferred_challenge: str,
    *,
    auto_select: bool,
    coverage: str = "implemented",
    pending_reason: str | None = None,
) -> dict[str, Any]:
    plan = {
        "caseId": case.get("id", ""),
        "mode": str(issuer_mode.get("id") or ""),
        "coverage": coverage,
        "classification": "generated",
        "preferredChallenge": preferred_challenge,
        "autoSelectAuthenticationMode": auto_select,
        "actions": actions,
    }
    if pending_reason:
        plan["pendingReason"] = pending_reason
    return plan


def _build_generated_case_plan(
    case: dict[str, Any], issuer_mode: dict[str, Any]
) -> dict[str, Any]:
    flow = case.get("flow") or {}
    kind = str(flow.get("kind") or "")
    destination = str(flow.get("destination") or "")
    scenario = str(case.get("wordingScenario") or "")
    selection_actions = [
        {"type": "send_areq"},
        {"type": "assert_authentication_mode_page"},
        {"type": "assert_stage_ui", "stage": "single_select"},
    ]

    def pending(reason: str, actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return _generated_plan(
            case,
            issuer_mode,
            actions or [{"type": "send_areq"}],
            destination or str(issuer_mode.get("defaultPreferredChallenge") or "auto"),
            auto_select=False,
            coverage="pending",
            pending_reason=reason,
        )

    if scenario not in GENERATED_SCENARIOS:
        return pending(f"Unsupported generated wording scenario: {scenario or '<missing>'}")

    if kind == "selection_page":
        return _generated_plan(
            case,
            issuer_mode,
            selection_actions,
            "auto",
            auto_select=False,
        )

    if kind == "selection_branch":
        destination_actions = _generated_destination_actions(destination, scenario)
        if destination not in CHALLENGE_VALUES or destination_actions is None:
            return pending(
                f"Unsupported generated selection destination/scenario: {destination}/{scenario}",
                selection_actions,
            )
        actions = [
            *selection_actions,
            {
                "type": "choose_authentication_mode",
                "preferredChallenge": destination,
                "challengeValue": CHALLENGE_VALUES[destination],
                "label": destination.upper(),
            },
            *destination_actions,
        ]
        return _generated_plan(case, issuer_mode, actions, destination, auto_select=True)

    if kind == "direct":
        destination_actions = _generated_destination_actions(destination, scenario)
        if destination not in CHALLENGE_VALUES or destination_actions is None:
            return pending(
                f"Unsupported generated direct destination/scenario: {destination}/{scenario}"
            )
        return _generated_plan(
            case,
            issuer_mode,
            [{"type": "send_areq"}, *destination_actions],
            destination,
            auto_select=False,
        )

    if kind == "oob_switch_sms":
        destination_actions = _generated_destination_actions("sms", scenario)
        if destination != "sms" or destination_actions is None:
            return pending(
                f"Unsupported generated OOB switch destination/scenario: {destination}/{scenario}"
            )
        return _generated_plan(
            case,
            issuer_mode,
            [
                {"type": "send_areq"},
                {"type": "assert_oob_page"},
                {"type": "switch_to_otp"},
                *destination_actions,
            ],
            "sms",
            auto_select=False,
        )

    return pending(f"Unsupported generated flow kind: {kind or '<missing>'}")


def _flow_plan(
    case: dict[str, Any],
    issuer_mode: dict[str, Any],
    actions: list[dict[str, Any]],
    preferred_challenge: str,
    *,
    auto_select: bool = True,
) -> dict[str, Any]:
    return {
        "caseId": case.get("id", ""),
        "mode": str(issuer_mode.get("id") or ""),
        "coverage": "implemented",
        "preferredChallenge": preferred_challenge,
        "autoSelectAuthenticationMode": auto_select,
        "actions": actions,
    }


def build_direct_otp_case_plan(case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") or {}
    messages = expected.get("messages") or {}
    transactions = expected.get("transactions") or []
    function_point = str(case.get("functionPoint") or "")
    lower_name = function_point.lower()

    actions: list[dict[str, Any]] = [{"type": "send_areq"}]

    if transactions:
        for index, transaction in enumerate(transactions):
            if index > 0:
                actions.append({"type": "new_transaction"})
                actions.append({"type": "send_areq"})
            expected_cres = (transaction.get("messages") or {}).get("CRes") or {}
            if expected_cres.get("transStatus") == "N":
                actions.extend(
                    [
                        {"type": "submit_otp", "otpPurpose": "failure"},
                        {"type": "submit_otp", "otpPurpose": "failure"},
                        {"type": "submit_otp", "otpPurpose": "failure"},
                    ]
                )
            elif expected_cres.get("transStatus") == "Y":
                actions.append({"type": "submit_otp", "otpPurpose": "success"})
            actions.append({"type": "expect_transaction", "index": index})
        return _plan(case, actions)

    if "ARes" in messages and "CRes" not in messages:
        if "RReq" in messages:
            actions.append({"type": "interrupt_challenge"})
        actions.append({"type": "expect_ares"})
        return _plan(case, actions)

    if "CRes" in messages:
        if "verification code error" in lower_name and "successful" in lower_name:
            actions.append({"type": "submit_otp", "otpPurpose": "failure"})
            actions.append({"type": "submit_otp", "otpPurpose": "success"})
        elif "cancel" in lower_name:
            actions.append({"type": "cancel_challenge"})
        else:
            actions.append({"type": "submit_otp", "otpPurpose": "success"})
        actions.append({"type": "expect_cres"})
        return _plan(case, actions)

    prompts = expected.get("prompts") or []
    if prompts:
        actions.extend(_prompt_actions(lower_name))
        actions.append({"type": "expect_prompt"})
        return _plan(case, actions)

    tags = set((case.get("automation") or {}).get("tags") or [])
    if "error" in tags:
        actions.append({"type": "expect_error"})
    elif "resend" in tags:
        actions.append({"type": "resend_until_limit"})
    else:
        actions.append({"type": "expect_result"})
    return _plan(case, actions)


def _prompt_actions(lower_name: str) -> list[dict[str, Any]]:
    if "don't enter" in lower_name:
        return [{"type": "submit_otp", "otpPurpose": "empty"}]
    if "enter english" in lower_name:
        return [{"type": "submit_otp", "otpPurpose": "alpha"}]
    if "special symbols" in lower_name:
        return [{"type": "submit_otp", "otpPurpose": "special"}]
    if "incorrect otp" in lower_name:
        return [{"type": "submit_otp", "otpPurpose": "failure"}]
    if "expired" in lower_name:
        return [{"type": "submit_otp", "otpPurpose": "expired"}]
    if "resend code" in lower_name:
        return [{"type": "resend_otp"}]
    return [{"type": "assert_otp_page"}]


def _plan(case: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "caseId": case.get("id", ""),
        "mode": "direct_otp",
        "coverage": "implemented",
        "actions": actions,
    }


def build_selection_sms_otp_case_plan(case: dict[str, Any]) -> dict[str, Any]:
    direct_plan = build_direct_otp_case_plan(case)
    actions: list[dict[str, Any]] = []
    for action in direct_plan.get("actions") or []:
        actions.append(action)
        if action.get("type") == "send_areq":
            actions.append(
                {
                    "type": "choose_authentication_mode",
                    "challengeValue": "1",
                    "label": "SMS",
                }
            )

    return {
        **direct_plan,
        "mode": "selection_sms_otp",
        "actions": actions,
    }
