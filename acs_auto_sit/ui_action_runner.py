from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from acs_auto_sit.ui_validation import validate_stage_fields


@dataclass
class ActionContext:
    page: dict[str, Any] | None
    stage_fields: dict[str, dict[str, Any]]
    submit_form: Callable[[dict[str, Any], dict[str, str]], dict[str, Any]]
    resolve_otp: Callable[[str, dict[str, Any]], tuple[str, dict[str, Any]]]
    sleep: Callable[[float], None]
    expiry_wait_seconds: float = 0
    resend_delay_seconds: float = 0
    resend_max_attempts: int = 10


def execute_generated_actions(
    context: ActionContext,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    current_page = context.page
    results: list[dict[str, Any]] = []

    for action in actions:
        action_type = str(action.get("type") or "")
        if action_type == "send_areq":
            continue

        result: dict[str, Any] = {"type": action_type, "status": "passed"}
        if action_type == "assert_authentication_mode_page":
            failure = _require_page_type(current_page, "authentication_mode", result)
        elif action_type == "assert_otp_page":
            failure = _require_page_type(current_page, "otp", result)
        elif action_type == "assert_stage_ui":
            stage = str(action.get("stage") or "")
            field_results = validate_stage_fields(
                stage,
                context.stage_fields.get(stage) or {},
                current_page,
            )
            result.update({"stage": stage, "fieldResults": field_results})
            missing = [item for item in field_results if not item.get("found")]
            failure = f"{len(missing)} expected {stage} UI fields were missing." if missing else None
        elif action_type == "choose_authentication_mode":
            failure = _page_required(current_page, result)
            if not failure:
                response = context.submit_form(
                    current_page or {},
                    {"challengeValue": str(action.get("challengeValue") or "")},
                )
                current_page = _response_page(response)
                result["response"] = response
        elif action_type == "submit_otp":
            failure = _require_page_type(current_page, "otp", result)
            if not failure:
                purpose = str(action.get("otpPurpose") or "success")
                value, lookup = context.resolve_otp(purpose, current_page or {})
                response = context.submit_form(current_page or {}, {"challengeValue": value})
                current_page = _response_page(response)
                result.update({"otpPurpose": purpose, "otpLookup": lookup, "response": response})
        elif action_type == "resend_otp":
            failure = _require_page_type(current_page, "otp", result)
            if not failure:
                delay = _action_delay(action, context.resend_delay_seconds)
                if delay > 0:
                    context.sleep(delay)
                response = context.submit_form(current_page or {}, {"resendCode": "Y"})
                current_page = _response_page(response)
                result.update({"delaySeconds": delay, "response": response})
        elif action_type == "resend_until_limit":
            failure = _require_page_type(current_page, "otp", result)
            submissions: list[dict[str, Any]] = []
            if not failure:
                for attempt in range(1, max(1, context.resend_max_attempts) + 1):
                    if not _has_action(current_page, "resendOtp"):
                        break
                    if context.resend_delay_seconds > 0:
                        context.sleep(context.resend_delay_seconds)
                    response = context.submit_form(current_page or {}, {"resendCode": "Y"})
                    submissions.append({"attempt": attempt, **response})
                    current_page = _response_page(response)
                    if response.get("cres") or current_page is None:
                        break
                else:
                    if _has_action(current_page, "resendOtp"):
                        failure = (
                            f"Safety max attempts reached ({context.resend_max_attempts}) "
                            "while resend control is still available."
                        )
                result["submissions"] = submissions
        elif action_type == "assert_oob_page":
            failure = _require_page_type(current_page, "oob", result)
        elif action_type == "continue_oob":
            failure = _require_page_type(current_page, "oob", result)
            if not failure:
                response = context.submit_form(current_page or {}, {"oobContinue": "Y"})
                current_page = _response_page(response)
                result["response"] = response
        elif action_type == "switch_to_otp":
            failure = _require_page_type(current_page, "oob", result)
            if not failure and not _has_action(current_page, "switchToOtp"):
                failure = "OOB page does not expose a switch-to-OTP control."
            if not failure:
                response = context.submit_form(current_page or {}, {"isForceOTP": "true"})
                current_page = _response_page(response)
                result["response"] = response
                if not current_page or current_page.get("type") != "otp":
                    actual = str((current_page or {}).get("type") or "none")
                    failure = f"Expected otp page after OOB switch, received {actual}."
        elif action_type == "wait_otp_expiry":
            failure = _require_page_type(current_page, "otp", result)
            if not failure:
                if context.expiry_wait_seconds <= 0:
                    failure = "OTP expiry wait must be a positive number."
                else:
                    context.sleep(context.expiry_wait_seconds)
                    result["waitSeconds"] = context.expiry_wait_seconds
        else:
            result.update({"status": "not_implemented", "reason": f"Unsupported generated action: {action_type}"})
            results.append(result)
            return _outcome("not_implemented", results, result, current_page)

        if failure:
            result.update({"status": "failed", "reason": failure})
            results.append(result)
            return _outcome("assertion_failed", results, result, current_page)
        results.append(result)

    return _outcome("passed", results, None, current_page)


def _page_required(page: dict[str, Any] | None, result: dict[str, Any]) -> str | None:
    if page is None:
        return f"Action {result['type']} requires a challenge page."
    return None


def _require_page_type(
    page: dict[str, Any] | None,
    expected: str,
    result: dict[str, Any],
) -> str | None:
    if page is None:
        return f"Expected {expected} page, but no challenge page was available."
    actual = str(page.get("type") or "unknown")
    if actual != expected:
        return f"Expected {expected} page, received {actual}."
    return None


def _response_page(response: dict[str, Any]) -> dict[str, Any] | None:
    challenge = response.get("challenge")
    return challenge if isinstance(challenge, dict) else None


def _has_action(page: dict[str, Any] | None, name: str) -> bool:
    return bool(page and (page.get("availableActions") or {}).get(name))


def _action_delay(action: dict[str, Any], configured: float) -> float:
    if "delaySeconds" in action:
        try:
            return max(0.0, float(action["delaySeconds"]))
        except (TypeError, ValueError):
            return 0.0
    if action.get("delayMode") == "configured":
        return max(0.0, configured)
    return 0.0


def _outcome(
    classification: str,
    results: list[dict[str, Any]],
    failed_action: dict[str, Any] | None,
    page: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "classification": classification,
        "actionResults": results,
        "failedAction": failed_action,
        "challenge": page,
        "cres": page.get("cres") if isinstance(page, dict) else None,
    }
