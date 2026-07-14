from __future__ import annotations

from typing import Any


CHALLENGE_VALUES = {"sms": "1", "email": "2", "oob": "3"}


def build_case_plan(case: dict[str, Any], issuer_mode: dict[str, Any]) -> dict[str, Any]:
    flow = case.get("flow") or {}
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
