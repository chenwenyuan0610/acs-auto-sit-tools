from __future__ import annotations

import argparse
import json
import mimetypes
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote
from uuid import uuid4

from acs_auto_sit.challenge import b64url_json, decode_b64url_json, parse_challenge_page
from acs_auto_sit.client import post_form, post_payload
from acs_auto_sit.case_plan import build_direct_otp_case_plan, build_selection_sms_otp_case_plan
from acs_auto_sit.issuer_modes import (
    issuer_mode_catalog,
    resolve_issuer_mode,
    resolve_preferred_challenge,
)
from acs_auto_sit.otp_provider import OtpSettings, resolve_otp_value, simulated_otp_for_acs_trans_id
from acs_auto_sit.sit_runner import browser_cases_by_id, dry_run_cases, live_skip_reason, load_browser_case_catalog
from acs_auto_sit.three_ds import (
    build_first_creq,
    build_next_creq_draft,
    extract_acs_values,
    requires_challenge,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = PROJECT_ROOT / "static"
NOTIFICATIONS: list[dict[str, Any]] = []


class AcsAutoSitHandler(BaseHTTPRequestHandler):
    server_version = "AcsAutoSit/0.1"

    def do_GET(self) -> None:
        if self.path == "/":
            self._serve_static("index.html")
            return
        if self.path == "/api/sit/browser-cases":
            self._handle_browser_cases()
            return
        if self.path == "/api/sit/issuer-modes":
            self._handle_issuer_modes()
            return
        if self.path.startswith("/static/"):
            self._serve_static(unquote(self.path.removeprefix("/static/")))
            return
        self._json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/areq":
                self._handle_areq()
                return
            if self.path == "/api/creq":
                self._handle_creq()
                return
            if self.path == "/api/notification":
                self._handle_notification()
                return
            if self.path == "/api/otp/simulated":
                self._handle_simulated_otp()
                return
            if self.path == "/api/sit/run":
                self._handle_sit_run()
                return
            self._json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except json.JSONDecodeError as exc:
            self._json_response({"error": f"Invalid JSON request: {exc}"}, HTTPStatus.BAD_REQUEST)
        except ValueError as exc:
            self._json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_areq(self) -> None:
        envelope = self._read_json_body()
        notification_url = _local_notification_url(self)
        self._json_response(_run_areq_flow(envelope, notification_url))

    def _handle_creq(self) -> None:
        envelope = self._read_json_body()
        url, headers, payload, timeout_seconds = _read_transaction_envelope(envelope)
        http = post_payload(url, payload, headers=headers, timeout_seconds=timeout_seconds)

        cres = http.response_json if isinstance(http.response_json, dict) else None
        next_draft = build_next_creq_draft(cres, payload if isinstance(payload, dict) else {})

        self._json_response(
            _creq_response(http, cres, next_draft)
        )

    def _handle_notification(self) -> None:
        raw_body = self._read_text_body()
        notification = _build_notification_record(
            self.headers.get("Content-Type", ""),
            raw_body,
        )
        NOTIFICATIONS.append(notification)
        self._json_response({"ok": True, "notification": notification})

    def _handle_simulated_otp(self) -> None:
        envelope = self._read_json_body()
        acs_trans_id = str(envelope.get("acsTransID") or "")
        if not acs_trans_id:
            raise ValueError("acsTransID is required.")
        self._json_response(
            {
                "ok": True,
                "acsTransID": acs_trans_id,
                "otp": simulated_otp_for_acs_trans_id(acs_trans_id),
            }
        )

    def _handle_browser_cases(self) -> None:
        catalog = load_browser_case_catalog()
        self._json_response({"ok": True, **catalog})

    def _handle_issuer_modes(self) -> None:
        self._json_response({"ok": True, **issuer_mode_catalog()})

    def _handle_sit_run(self) -> None:
        envelope = self._read_json_body()
        case_ids = envelope.get("caseIds") or []
        if not isinstance(case_ids, list) or not all(isinstance(case_id, str) for case_id in case_ids):
            raise ValueError("caseIds must be a list of case ID strings.")
        if not case_ids:
            raise ValueError("At least one case ID is required.")

        mode = str(envelope.get("mode") or "dryRun")
        if mode not in {"dryRun", "live"}:
            raise ValueError("mode must be dryRun or live.")

        if mode == "dryRun":
            self._json_response(
                {
                    "ok": True,
                    "mode": mode,
                    "results": dry_run_cases(case_ids),
                }
            )
            return

        issuer_mode = resolve_issuer_mode(str(envelope.get("issuerMode") or ""))
        preferred_challenge = resolve_preferred_challenge(str(envelope.get("preferredChallenge") or ""))
        transaction = envelope.get("transaction") or {}
        if not isinstance(transaction, dict):
            raise ValueError("transaction must be a JSON object.")

        self._json_response(
            {
                "ok": True,
                "mode": mode,
                "issuerMode": issuer_mode,
                "preferredChallenge": preferred_challenge,
                "results": _run_live_sit_cases(
                    case_ids,
                    transaction,
                    _local_notification_url(self),
                    issuer_mode,
                    preferred_challenge,
                ),
            }
        )

    def _read_json_body(self) -> dict[str, Any]:
        raw_body = self._read_text_body()
        value = json.loads(raw_body or "{}")
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    def _read_text_body(self) -> str:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length).decode("utf-8")

    def _json_response(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_static(self, relative_path: str) -> None:
        path = (STATIC_ROOT / relative_path).resolve()
        if not _is_relative_to(path, STATIC_ROOT.resolve()) or not path.is_file():
            self._json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type = f"{content_type}; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), AcsAutoSitHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ACS Auto SIT local web tool.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port)
    host, port = server.server_address
    print(f"ACS Auto SIT running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def _read_transaction_envelope(envelope: dict[str, Any]) -> tuple[str, dict[str, str], Any, int]:
    url = str(envelope.get("url") or "").strip()
    if not url:
        raise ValueError("Transaction URL is required.")

    headers = envelope.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be a JSON object.")

    payload = envelope.get("payload")
    if payload is None:
        raise ValueError("payload is required.")

    timeout_seconds = int(envelope.get("timeoutSeconds") or 30)
    return url, {str(key): str(value) for key, value in headers.items()}, payload, timeout_seconds


def _run_areq_flow(envelope: dict[str, Any], notification_url: str) -> dict[str, Any]:
    url, headers, payload, timeout_seconds = _read_transaction_envelope(envelope)
    payload = _with_fresh_transaction_ids(payload)
    payload, original_notification_url = _with_local_notification_url(payload, notification_url)
    http = post_payload(url, payload, headers=headers, timeout_seconds=timeout_seconds)

    ares = http.response_json if isinstance(http.response_json, dict) else None
    creq_draft = None
    draft_error = None
    auto_creq = None
    if requires_challenge(ares):
        try:
            creq_draft = build_first_creq(
                ares,
                payload if isinstance(payload, dict) else {},
                challenge_window_size=str(envelope.get("challengeWindowSize") or "05"),
            )
            creq_url = ares.get("acsURL")
            if creq_url:
                auto_creq = _post_creq(
                    creq_url,
                    creq_draft,
                    timeout_seconds,
                    auto_select_sms=bool(envelope.get("autoSelectSms", True)),
                    auto_submit_otp=bool(envelope.get("autoSubmitOtp", False)),
                    simulated_otp=str(envelope.get("simulatedOtp") or ""),
                    notification_url=notification_url,
                    issuer_mode=resolve_issuer_mode(str(envelope.get("issuerMode") or "")),
                    preferred_challenge=resolve_preferred_challenge(str(envelope.get("preferredChallenge") or "")),
                    otp_attempts=_read_otp_attempts(envelope),
                    otp_settings=_read_otp_settings(envelope),
                )
        except ValueError as exc:
            draft_error = str(exc)

    return {
        "ok": http.error is None,
        "error": http.error,
        "http": http.to_dict(),
        "ares": ares,
        "extracted": extract_acs_values(ares),
        "challengeRequired": requires_challenge(ares),
        "creqUrl": ares.get("acsURL") if isinstance(ares, dict) else "",
        "creqDraft": creq_draft,
        "autoCreq": auto_creq,
        "draftError": draft_error,
        "notificationURL": notification_url,
        "originalNotificationURL": original_notification_url,
    }


def _run_live_sit_cases(
    case_ids: list[str],
    transaction: dict[str, Any],
    notification_url: str,
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
) -> list[dict[str, Any]]:
    cases = browser_cases_by_id()
    results: list[dict[str, Any]] = []

    for case_id in case_ids:
        case = cases.get(case_id)
        if not case:
            results.append(
                {
                    "caseId": case_id,
                    "status": "error",
                    "reason": "Case ID was not found in the Browser SIT catalog.",
                    "case": None,
                    "details": {},
                }
            )
            continue

        skip_reason = live_skip_reason(case)
        case_plan = _case_plan_for_issuer_mode(case, issuer_mode["id"])
        if skip_reason and case_plan is None:
            results.append(
                {
                    "caseId": case_id,
                    "status": "skipped",
                    "reason": skip_reason,
                    "case": case,
                    "details": {
                        "expected": case.get("expected", {}),
                        "automation": case.get("automation", {}),
                        "issuerMode": issuer_mode,
                        "preferredChallenge": preferred_challenge,
                    },
                }
            )
            continue

        envelope = {
            **transaction,
            "autoSelectSms": True,
            "autoSubmitOtp": True,
            "simulatedOtp": str(transaction.get("simulatedOtp") or "123456"),
            "issuerMode": issuer_mode["id"],
            "preferredChallenge": preferred_challenge,
        }
        if case_plan:
            envelope["otpAttempts"] = [
                action.get("otpPurpose", "success")
                for action in case_plan.get("actions", [])
                if action.get("type") == "submit_otp"
            ]
            if not envelope["otpAttempts"]:
                envelope["autoSubmitOtp"] = False

        run_result = _run_areq_flow(envelope, notification_url)
        expected_status = (
            case.get("expected", {})
            .get("messages", {})
            .get("CRes", {})
            .get("transStatus")
        )
        cres = (run_result.get("autoCreq") or {}).get("cres") if isinstance(run_result.get("autoCreq"), dict) else None
        actual_status = cres.get("transStatus") if isinstance(cres, dict) else None
        passed = run_result.get("ok") is True and expected_status == actual_status
        status = "pass" if passed else "fail"
        results.append(
            {
                "caseId": case_id,
                "status": status,
                "reason": (
                    f"CRes transStatus matched {expected_status}."
                    if passed
                    else f"Expected CRes transStatus {expected_status}, got {actual_status}."
                ),
                "case": case,
                "details": {
                    "expected": case.get("expected", {}),
                    "issuerMode": issuer_mode,
                    "preferredChallenge": preferred_challenge,
                    "casePlan": case_plan,
                    "ares": run_result.get("ares"),
                    "cres": cres,
                    "notification": _notification_from_auto_creq(run_result.get("autoCreq")),
                    "http": {
                        "areq": run_result.get("http"),
                    },
                    "error": run_result.get("error") or run_result.get("draftError"),
                },
            }
        )

    return results


def _case_plan_for_issuer_mode(case: dict[str, Any], issuer_mode_id: str) -> dict[str, Any] | None:
    if issuer_mode_id == "direct_otp":
        return build_direct_otp_case_plan(case)
    if issuer_mode_id == "selection_sms_otp":
        return build_selection_sms_otp_case_plan(case)
    return None


def _notification_from_auto_creq(auto_creq: Any) -> Any:
    if not isinstance(auto_creq, dict):
        return None
    otp_submission = auto_creq.get("otpSubmission")
    if isinstance(otp_submission, dict) and otp_submission.get("notification") is not None:
        return otp_submission.get("notification")
    return auto_creq.get("notification")


def _with_fresh_transaction_ids(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    refreshed = deepcopy(payload)
    refreshed["threeDSServerTransID"] = str(uuid4())
    refreshed["dsTransID"] = str(uuid4())
    return refreshed


def _with_local_notification_url(payload: Any, notification_url: str) -> tuple[Any, str | None]:
    if not isinstance(payload, dict):
        return payload, None

    refreshed = deepcopy(payload)
    original = refreshed.get("notificationURL")
    refreshed["notificationURL"] = notification_url
    return refreshed, str(original) if original is not None else None


def _local_notification_url(handler: BaseHTTPRequestHandler) -> str:
    host = handler.headers.get("Host")
    if not host:
        server_host, server_port = handler.server.server_address[:2]
        host = f"{server_host}:{server_port}"
    return f"http://{host}/api/notification"


def _post_creq(
    url: str,
    creq: dict[str, Any],
    timeout_seconds: int,
    auto_select_sms: bool = True,
    auto_submit_otp: bool = False,
    simulated_otp: str = "",
    notification_url: str = "",
    issuer_mode: dict[str, Any] | None = None,
    preferred_challenge: str = "auto",
    otp_attempts: list[str] | None = None,
    otp_settings: OtpSettings | None = None,
) -> dict[str, Any]:
    issuer_mode = issuer_mode or resolve_issuer_mode("")
    preferred_challenge = resolve_preferred_challenge(preferred_challenge)
    otp_settings = otp_settings or OtpSettings(success_otp=simulated_otp or "123456")
    otp_attempts = otp_attempts or (["success"] if auto_submit_otp and (simulated_otp or otp_settings.success_otp) else [])
    http = post_form(
        url,
        {"creq": b64url_json(creq), "threeDSSessionData": ""},
        timeout_seconds=timeout_seconds,
    )
    page = parse_challenge_page(http.response_text, url) if http.response_text else None
    cres = page.get("cres") if page else None
    response = _creq_response(http, cres, build_next_creq_draft(cres, creq))
    response["challenge"] = page
    response["smsSelection"] = None
    response["oobSubmission"] = None
    response["otpSubmission"] = None
    response["otpSubmissions"] = []
    response["notification"] = _post_final_notification(page, cres, notification_url, timeout_seconds)
    response["issuerMode"] = issuer_mode
    response["preferredChallenge"] = preferred_challenge

    if page and page["type"] == "authentication_mode" and auto_select_sms:
        selected_value = _authentication_mode_value(page, issuer_mode, preferred_challenge)
        sms_response = _submit_challenge_form(
            page,
            {"challengeValue": selected_value},
            timeout_seconds,
        )
        response["smsSelection"] = {
            "selectedValue": selected_value,
            "selectedLabel": _radio_label(page, "challengeValue", selected_value),
            **sms_response,
        }

        _advance_challenge_response(
            response,
            sms_response.get("challenge"),
            creq,
            timeout_seconds,
            auto_submit_otp,
            simulated_otp,
            otp_attempts,
            otp_settings,
            notification_url,
            issuer_mode,
            preferred_challenge,
        )
    elif page:
        _advance_challenge_response(
            response,
            page,
            creq,
            timeout_seconds,
            auto_submit_otp,
            simulated_otp,
            otp_attempts,
            otp_settings,
            notification_url,
            issuer_mode,
            preferred_challenge,
        )

    return response


def _advance_challenge_response(
    response: dict[str, Any],
    page: dict[str, Any] | None,
    previous_creq: dict[str, Any],
    timeout_seconds: int,
    auto_submit_otp: bool,
    simulated_otp: str,
    otp_attempts: list[str],
    otp_settings: OtpSettings,
    notification_url: str,
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
) -> None:
    if not page:
        return

    if page["type"] == "oob":
        should_switch = (
            issuer_mode["id"] == "default_oob_can_switch_otp"
            and preferred_challenge in {"otp", "sms"}
            and page.get("availableActions", {}).get("switchToOtp")
        )
        if should_switch:
            switch_response = _submit_challenge_form(
                page,
                _switch_to_otp_overrides(page),
                timeout_seconds,
            )
            response["oobSubmission"] = {
                "action": "switchToOtp",
                **switch_response,
            }
            _advance_challenge_response(
                response,
                switch_response.get("challenge"),
                previous_creq,
                timeout_seconds,
                auto_submit_otp,
                simulated_otp,
                otp_attempts,
                otp_settings,
                notification_url,
                issuer_mode,
                "otp",
            )
            return

        if page.get("availableActions", {}).get("oobContinue"):
            oob_response = _submit_challenge_form(page, {"oobContinue": "Y"}, timeout_seconds)
            response["oobSubmission"] = {
                "action": "oobContinue",
                **oob_response,
            }
            if oob_response.get("cres"):
                _apply_final_challenge_response(
                    response,
                    "oobSubmission",
                    oob_response,
                    previous_creq,
                    notification_url,
                    timeout_seconds,
                )
            return

    if page["type"] == "otp" and auto_submit_otp and otp_attempts:
        current_page = page
        for purpose in otp_attempts:
            acs_trans_id = str((current_page.get("fields") or {}).get("acsTransID") or previous_creq.get("acsTransID") or "")
            otp_value = resolve_otp_value(purpose, acs_trans_id, otp_settings)
            otp_response = _submit_challenge_form(
                current_page,
                {"challengeValue": otp_value},
                timeout_seconds,
            )
            submission = {
                "simulatedOtpUsed": True,
                "otpSourceMode": otp_settings.source_mode,
                "otpPurpose": purpose,
                "otpLength": len(otp_value),
                **otp_response,
            }
            response["otpSubmission"] = submission
            response["otpSubmissions"].append(submission)
            if otp_response.get("cres"):
                _apply_final_challenge_response(
                    response,
                    "otpSubmission",
                    otp_response,
                    previous_creq,
                    notification_url,
                    timeout_seconds,
                )
                break
            next_page = otp_response.get("challenge")
            if not next_page or next_page.get("type") != "otp":
                break
            current_page = next_page


def _apply_final_challenge_response(
    response: dict[str, Any],
    response_key: str,
    challenge_response: dict[str, Any],
    previous_creq: dict[str, Any],
    notification_url: str,
    timeout_seconds: int,
) -> None:
    response["cres"] = challenge_response["cres"]
    response["continueRequired"] = requires_challenge(challenge_response["cres"])
    response["nextCreqDraft"] = build_next_creq_draft(challenge_response["cres"], previous_creq)
    response[response_key]["notification"] = _post_final_notification(
        challenge_response.get("challenge"),
        challenge_response["cres"],
        notification_url,
        timeout_seconds,
    )


def _authentication_mode_value(
    page: dict[str, Any],
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
) -> str:
    if issuer_mode["id"] == "selection_sms_otp":
        preferred_values = ["1", "2", "3"]
    elif preferred_challenge in {"oob"} or issuer_mode["id"] == "direct_oob":
        preferred_values = ["3", "2", "1"]
    elif preferred_challenge in {"sms", "otp"}:
        preferred_values = ["1", "2", "3"]
    elif issuer_mode["id"] == "default_oob_can_switch_otp":
        preferred_values = ["3", "1", "2"]
    else:
        preferred_values = ["1", "3", "2"]

    available_values = {
        str(option.get("value") or "")
        for option in page.get("radioOptions") or []
        if option.get("name") == "challengeValue"
    }
    for value in preferred_values:
        if value in available_values:
            return value
    return next(iter(available_values), "1")


def _switch_to_otp_overrides(page: dict[str, Any]) -> dict[str, str]:
    fields = page.get("fields") or {}
    for name in ("switchauthm", "switchAuthm", "switchToOtp", "switchToOTP"):
        if name in fields:
            return {name: "Y"}
    if "isForceOTP" in fields:
        return {"isForceOTP": "true"}
    return {}


def _submit_challenge_form(
    page: dict[str, Any],
    overrides: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    fields = dict(page.get("fields") or {})
    fields.update(overrides)
    http = post_form(page["formAction"], fields, timeout_seconds=timeout_seconds)
    next_page = parse_challenge_page(http.response_text, page["formAction"]) if http.response_text else None
    cres = next_page.get("cres") if next_page else None
    return {
        "ok": http.error is None,
        "error": http.error,
        "http": http.to_dict(),
        "challenge": next_page,
        "cres": cres,
    }


def _read_otp_attempts(envelope: dict[str, Any]) -> list[str]:
    attempts = envelope.get("otpAttempts")
    if isinstance(attempts, list):
        return [str(item) for item in attempts if str(item)]
    if envelope.get("simulatedOtp"):
        return ["success"]
    return []


def _read_otp_settings(envelope: dict[str, Any]) -> OtpSettings:
    success_otp = str(envelope.get("successOtp") or envelope.get("simulatedOtp") or "123456")
    failure_otp = str(envelope.get("failureOtp") or "000000")
    source_mode = str(envelope.get("otpSourceMode") or "customer_generated")
    if source_mode not in {"customer_generated", "acs_generated"}:
        raise ValueError("otpSourceMode must be customer_generated or acs_generated.")
    return OtpSettings(
        source_mode=source_mode,
        success_otp=success_otp,
        failure_otp=failure_otp,
    )


def _radio_label(page: dict[str, Any], name: str, value: str) -> str:
    for option in page.get("radioOptions") or []:
        if option.get("name") == name and option.get("value") == value:
            return str(option.get("label") or "")
    return ""


def _post_final_notification(
    page: dict[str, Any] | None,
    cres: dict[str, Any] | None,
    notification_url: str,
    timeout_seconds: int,
) -> dict[str, Any] | None:
    if not cres or not notification_url:
        return None

    fields = dict(page.get("fields") or {}) if page else {}
    form = {
        "cres": fields.get("cres") or b64url_json(cres),
        "threeDSSessionData": fields.get("threeDSSessionData", ""),
    }
    http = post_form(notification_url, form, timeout_seconds=timeout_seconds)
    notification = http.response_json.get("notification") if isinstance(http.response_json, dict) else None
    return {
        "ok": http.error is None,
        "error": http.error,
        "http": http.to_dict(),
        "notification": notification,
    }


def _build_notification_record(content_type: str, raw_body: str) -> dict[str, Any]:
    body_type = content_type.split(";", 1)[0].strip().lower()
    form: dict[str, str] = {}
    json_body: Any = None

    if body_type == "application/json":
        json_body = json.loads(raw_body or "{}")
        if not isinstance(json_body, dict):
            raise ValueError("Notification JSON body must be an object.")
    else:
        parsed = parse_qs(raw_body, keep_blank_values=True)
        form = {key: values[0] if values else "" for key, values in parsed.items()}

    encoded_cres = ""
    if isinstance(json_body, dict):
        encoded_cres = str(json_body.get("cres") or "")
    else:
        encoded_cres = form.get("cres", "")

    return {
        "receivedAt": datetime.now(timezone.utc).isoformat(),
        "contentType": content_type,
        "form": form,
        "json": json_body,
        "cres": decode_b64url_json(encoded_cres),
    }


def _creq_response(http: Any, cres: dict[str, Any] | None, next_draft: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "ok": http.error is None,
        "error": http.error,
        "http": http.to_dict(),
        "cres": cres,
        "extracted": extract_acs_values(cres),
        "continueRequired": requires_challenge(cres),
        "nextCreqDraft": next_draft,
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
