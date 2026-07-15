from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from acs_auto_sit.challenge import (
    b64url_json,
    decode_b64url_json,
    parse_challenge_page,
    visible_text_from_html,
)
from acs_auto_sit.client import post_form, post_payload
from acs_auto_sit.case_plan import build_case_plan
from acs_auto_sit.issuer_modes import (
    issuer_mode_catalog,
    resolve_issuer_mode,
    resolve_preferred_challenge,
)
from acs_auto_sit.otp_provider import (
    OtpSettings,
    lookup_acs_generated_otp,
    resolve_otp_value,
    simulated_otp_for_acs_trans_id,
)
from acs_auto_sit.sit_runner import browser_cases_by_id, dry_run_cases, live_skip_reason, load_browser_case_catalog
from acs_auto_sit.three_ds import (
    build_first_creq,
    build_next_creq_draft,
    extract_acs_values,
    requires_challenge,
)
from acs_auto_sit.transaction_result_provider import simulated_transaction_result_for_acs_trans_id
from acs_auto_sit.wording_profiles import (
    DEFAULT_SUPPORTED_LOCALES,
    DEFAULT_WORDING_PROFILES_PATH,
    import_wording_workbook,
    load_wording_profiles,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = PROJECT_ROOT / "static"
NOTIFICATIONS: list[dict[str, Any]] = []


class AcsAutoSitHandler(BaseHTTPRequestHandler):
    server_version = "AcsAutoSit/0.1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/":
            self._serve_static("index.html")
            return
        if path == "/api/sit/browser-cases":
            self._handle_browser_cases(query)
            return
        if path == "/api/sit/issuer-modes":
            self._handle_issuer_modes()
            return
        if path == "/api/sit/wording-profiles":
            self._handle_wording_profiles(query)
            return
        if path.startswith("/static/"):
            self._serve_static(unquote(path.removeprefix("/static/")))
            return
        self._json_response({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/api/areq":
                self._handle_areq()
                return
            if path == "/api/creq":
                self._handle_creq()
                return
            if path == "/api/notification":
                self._handle_notification()
                return
            if path == "/api/otp/simulated":
                self._handle_simulated_otp()
                return
            if path == "/api/transaction-result/simulated":
                self._handle_simulated_transaction_result()
                return
            if path == "/api/sit/run":
                self._handle_sit_run()
                return
            if path == "/api/sit/wording-profiles/import":
                self._handle_wording_profile_import()
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

    def _handle_simulated_transaction_result(self) -> None:
        envelope = self._read_json_body()
        self._json_response(
            simulated_transaction_result_for_acs_trans_id(
                str(envelope.get("acsTransID") or "")
            )
        )

    def _handle_browser_cases(self, query: dict[str, list[str]]) -> None:
        issuer_id = str((query.get("issuerId") or ["default"])[0] or "default")
        issuer_mode = str((query.get("issuerMode") or ["sms_otp"])[0] or "sms_otp")
        catalog = load_browser_case_catalog(
            wording_profiles_path=self._wording_profiles_path(),
            issuer_id=issuer_id,
            issuer_mode=issuer_mode,
        )
        self._json_response({"ok": True, **catalog})

    def _handle_issuer_modes(self) -> None:
        self._json_response({"ok": True, **issuer_mode_catalog()})

    def _handle_wording_profiles(self, query: dict[str, list[str]]) -> None:
        path = self._wording_profiles_path()
        profiles = load_wording_profiles(path) if path else None
        issuer_id = str((query.get("issuerId") or ["default"])[0] or "default")
        requested_mode = str((query.get("issuerMode") or ["sms_otp"])[0] or "sms_otp")
        if not profiles:
            self._json_response(
                {
                    "ok": True,
                    "imported": False,
                    "sourceFormat": "",
                    "sourceSheets": [],
                    "selectedIssuerMode": requested_mode,
                    "generatedCaseCount": 0,
                    "defaultSupportedLocales": list(DEFAULT_SUPPORTED_LOCALES),
                    "issuers": [],
                    "summary": {
                        "issuerCount": 0,
                        "localeCount": 0,
                        "wordingCount": 0,
                        "generatedCaseCount": 0,
                    },
                }
            )
            return
        selected_mode = _profile_issuer_mode(profiles, requested_mode)
        catalog = load_browser_case_catalog(
            wording_profiles_path=path,
            issuer_id=issuer_id,
            issuer_mode=selected_mode,
        )
        generated_count = _generated_wording_case_count(catalog)
        summary = {**(profiles.get("summary") or {}), "generatedCaseCount": generated_count}
        self._json_response(
            {
                "ok": True,
                "imported": True,
                "sourceFile": profiles.get("sourceFile", ""),
                "sourceFormat": profiles.get("sourceFormat", ""),
                "sourceSheets": profiles.get("sourceSheets") or [],
                "importedAt": profiles.get("importedAt", ""),
                "selectedIssuerMode": selected_mode,
                "generatedCaseCount": generated_count,
                "defaultSupportedLocales": profiles.get("defaultSupportedLocales") or list(DEFAULT_SUPPORTED_LOCALES),
                "issuers": list((profiles.get("issuers") or {}).values()),
                "summary": summary,
            }
        )

    def _handle_wording_profile_import(self) -> None:
        envelope = self._read_json_body()
        file_name = str(envelope.get("fileName") or "").strip()
        encoded = str(envelope.get("contentBase64") or "").strip()
        if not file_name.lower().endswith(".xlsx"):
            raise ValueError("Wording profile file must use the .xlsx extension.")
        if not encoded:
            raise ValueError("contentBase64 is required.")
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("contentBase64 is not valid base64.") from exc
        destination = self._wording_profiles_path()
        if not destination:
            raise ValueError("Wording profile storage is not configured.")
        imported = import_wording_workbook(
            content,
            destination,
            source_file=file_name,
        )
        requested_mode = str(envelope.get("issuerMode") or "sms_otp")
        issuer_id = str(envelope.get("issuerId") or "default")
        selected_mode = _profile_issuer_mode(imported, requested_mode)
        catalog = load_browser_case_catalog(
            wording_profiles_path=destination,
            issuer_id=issuer_id,
            issuer_mode=selected_mode,
        )
        generated_count = _generated_wording_case_count(catalog)
        summary = {**(imported.get("summary") or {}), "generatedCaseCount": generated_count}
        self._json_response(
            {
                "ok": True,
                "sourceFile": imported.get("sourceFile", ""),
                "sourceFormat": imported.get("sourceFormat", ""),
                "sourceSheets": imported.get("sourceSheets") or [],
                "importedAt": imported.get("importedAt", ""),
                "selectedIssuerMode": selected_mode,
                "generatedCaseCount": generated_count,
                "defaultSupportedLocales": imported.get("defaultSupportedLocales") or [],
                "issuers": list((imported.get("issuers") or {}).values()),
                "summary": summary,
            }
        )

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
            results = dry_run_cases(case_ids)
            self._json_response(
                {
                    "ok": True,
                    "mode": mode,
                    "summary": _summarize_sit_results(results),
                    "results": results,
                }
            )
            return

        issuer_mode = resolve_issuer_mode(str(envelope.get("issuerMode") or ""))
        issuer_id = str(envelope.get("issuerId") or "default")
        preferred_challenge = resolve_preferred_challenge(str(envelope.get("preferredChallenge") or ""))
        transaction = envelope.get("transaction") or {}
        if not isinstance(transaction, dict):
            raise ValueError("transaction must be a JSON object.")

        results = _run_live_sit_cases(
            case_ids,
            transaction,
            _local_notification_url(self),
            issuer_mode,
            preferred_challenge,
            issuer_id,
            self._wording_profiles_path(),
        )
        self._json_response(
            {
                "ok": True,
                "mode": mode,
                "issuerMode": issuer_mode,
                "issuerId": issuer_id,
                "preferredChallenge": preferred_challenge,
                "summary": _summarize_sit_results(results),
                "results": results,
            }
        )

    def _read_json_body(self) -> dict[str, Any]:
        raw_body = self._read_text_body()
        value = json.loads(raw_body or "{}")
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    def _wording_profiles_path(self) -> Path | None:
        return getattr(self.server, "wording_profiles_path", None)

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


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    wording_profiles_path: Path | None = None,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), AcsAutoSitHandler)
    server.wording_profiles_path = wording_profiles_path  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ACS Auto SIT local web tool.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)

    server = create_server(
        args.host,
        args.port,
        wording_profiles_path=DEFAULT_WORDING_PROFILES_PATH,
    )
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


def _post_areq_with_retries(
    url: str,
    headers: dict[str, str],
    payload: Any,
    notification_url: str,
    timeout_seconds: int,
    max_attempts: int = 5,
) -> tuple[Any, Any, str | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    original_notification_url: str | None = None
    current_payload: Any = payload
    http: Any = None
    for attempt in range(1, max_attempts + 1):
        current_payload = _with_fresh_transaction_ids(payload)
        current_payload, original_notification_url = _with_local_notification_url(current_payload, notification_url)
        http = post_payload(url, current_payload, headers=headers, timeout_seconds=timeout_seconds)
        attempts.append(http.to_dict())
        ares = http.response_json if isinstance(http.response_json, dict) else None
        if not _is_transient_slow_backend_error(ares) or attempt >= max_attempts:
            return http, current_payload, original_notification_url, attempts
        time.sleep(float(2 ** (attempt - 1)))
    return http, current_payload, original_notification_url, attempts


def _is_transient_slow_backend_error(ares: Any) -> bool:
    if not isinstance(ares, dict):
        return False
    if str(ares.get("messageType") or "") != "Erro":
        return False
    if str(ares.get("errorCode") or "") != "403":
        return False
    text = " ".join(
        str(ares.get(key) or "")
        for key in ("errorDescription", "errorDetail")
    ).lower()
    return "slowly processing" in text or "transient system failure" in text


def _is_acs_error(message: Any) -> bool:
    return isinstance(message, dict) and str(message.get("messageType") or "") == "Erro"


def _acs_error_reason(message: Any) -> str:
    if not isinstance(message, dict):
        return "ACS error response was not available."

    code = str(message.get("errorCode") or "").strip() or "unknown"
    description = str(message.get("errorDescription") or "").strip()
    detail = str(message.get("errorDetail") or "").strip()
    parts = [part for part in (description, detail) if part]
    suffix = f": {' - '.join(parts)}" if parts else "."
    return f"ACS Erro {code}{suffix}"


def _run_areq_flow(envelope: dict[str, Any], notification_url: str) -> dict[str, Any]:
    url, headers, payload, timeout_seconds = _read_transaction_envelope(envelope)
    http, payload, original_notification_url, http_attempts = _post_areq_with_retries(
        url,
        headers,
        payload,
        notification_url,
        timeout_seconds,
    )

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
                    challenge_action=str(envelope.get("challengeAction") or ""),
                    resend_max_attempts=int(envelope.get("resendMaxAttempts") or 10),
                    challenge_headers=_challenge_headers_for_payload(payload),
                    resend_delay_seconds=_read_resend_delay_seconds(envelope),
                )
        except ValueError as exc:
            draft_error = str(exc)

    return {
        "ok": http.error is None,
        "error": http.error,
        "http": http.to_dict(),
        "httpAttempts": http_attempts,
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
    issuer_id: str = "default",
    wording_profiles_path: Path | None = None,
) -> list[dict[str, Any]]:
    cases = browser_cases_by_id(
        wording_profiles_path=wording_profiles_path,
        issuer_id=issuer_id,
        issuer_mode=issuer_mode["id"],
    )
    results: list[dict[str, Any]] = []
    case_delay_seconds = _read_case_delay_seconds(transaction)

    for index, case_id in enumerate(case_ids):
        if index > 0 and case_delay_seconds > 0:
            time.sleep(case_delay_seconds)

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

        case_transaction = _transaction_for_case(case, transaction)
        skip_reason = live_skip_reason(case)
        case_plan = _case_plan_for_issuer_mode(case, issuer_mode)
        effective_preferred_challenge = _preferred_challenge_for_case_plan(
            case_plan,
            preferred_challenge,
        )
        case_areq = _case_areq_record(case_id, case_transaction)
        if skip_reason:
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
                        "preferredChallenge": effective_preferred_challenge,
                        "casePlan": case_plan,
                        "caseAreq": case_areq,
                    },
                }
            )
            continue

        envelope = {
            **case_transaction,
            "autoSelectSms": bool((case_plan or {}).get("autoSelectAuthenticationMode", True)),
            "autoSubmitOtp": True,
            "simulatedOtp": str(case_transaction.get("simulatedOtp") or "123456"),
            "issuerMode": issuer_mode["id"],
            "preferredChallenge": effective_preferred_challenge,
        }
        if case_plan:
            envelope["otpAttempts"] = [
                action.get("otpPurpose", "success")
                for action in case_plan.get("actions", [])
                if action.get("type") == "submit_otp"
            ]
            if not envelope["otpAttempts"]:
                envelope["autoSubmitOtp"] = False
            if any(action.get("type") == "cancel_challenge" for action in case_plan.get("actions", [])):
                envelope["challengeAction"] = "cancel"
                envelope["autoSubmitOtp"] = False
            if any(action.get("type") == "resend_otp" for action in case_plan.get("actions", [])):
                envelope["challengeAction"] = "resend"
                envelope["autoSubmitOtp"] = False
            if any(action.get("type") == "resend_until_limit" for action in case_plan.get("actions", [])):
                envelope["challengeAction"] = "resend_limit"
                envelope["resendMaxAttempts"] = 10
                envelope["autoSubmitOtp"] = False

        if (case.get("expected", {}) or {}).get("transactions"):
            results.append(
                _run_transaction_case(
                    case_id,
                    case,
                    case_plan,
                    envelope,
                    notification_url,
                    issuer_mode,
                    effective_preferred_challenge,
                    case_areq,
                )
            )
            continue

        if (case.get("expected", {}) or {}).get("prompts"):
            results.append(
                _run_prompt_case(
                    case_id,
                    case,
                    case_plan,
                    envelope,
                    notification_url,
                    issuer_mode,
                    effective_preferred_challenge,
                    case_areq,
                )
            )
            continue

        if (case.get("expected", {}) or {}).get("errors"):
            results.append(
                _run_error_case(
                    case_id,
                    case,
                    case_plan,
                    envelope,
                    notification_url,
                    issuer_mode,
                    effective_preferred_challenge,
                    case_areq,
                )
            )
            continue

        if any(action.get("type") == "resend_until_limit" for action in (case_plan or {}).get("actions", [])):
            results.append(
                _run_resend_limit_case(
                    case_id,
                    case,
                    case_plan,
                    envelope,
                    notification_url,
                    issuer_mode,
                    effective_preferred_challenge,
                    case_areq,
                )
            )
            continue

        run_result = _run_areq_flow(envelope, notification_url)
        case_areq["actualRequestBody"] = (
            ((run_result.get("http") or {}).get("request_body"))
            if isinstance(run_result.get("http"), dict)
            else None
        )
        expected_messages = case.get("expected", {}).get("messages", {})
        if "ARes" in expected_messages and "CRes" not in expected_messages:
            results.append(
                _ares_only_result(
                    case_id,
                    case,
                    case_plan,
                    case_areq,
                    run_result,
                    issuer_mode,
                    effective_preferred_challenge,
                )
            )
            continue
        expected_status = (
            expected_messages
            .get("CRes", {})
            .get("transStatus")
        )
        cres = (run_result.get("autoCreq") or {}).get("cres") if isinstance(run_result.get("autoCreq"), dict) else None
        actual_status = cres.get("transStatus") if isinstance(cres, dict) else None
        passed = run_result.get("ok") is True and expected_status == actual_status
        status = "pass" if passed else "fail"
        reason = (
            f"CRes transStatus matched {expected_status}."
            if passed
            else (
                _acs_error_reason(run_result.get("ares"))
                if _is_acs_error(run_result.get("ares"))
                else _expected_actual_reason("CRes transStatus", expected_status, actual_status)
            )
        )
        results.append(
            {
                "caseId": case_id,
                "status": status,
                "reason": reason,
                "case": case,
                "details": {
                    "expected": case.get("expected", {}),
                    "issuerMode": issuer_mode,
                    "preferredChallenge": effective_preferred_challenge,
                    "casePlan": case_plan,
                    "caseAreq": case_areq,
                    "ares": run_result.get("ares"),
                    "cres": cres,
                    "challengeFlow": run_result.get("autoCreq"),
                    "notification": _notification_from_auto_creq(run_result.get("autoCreq")),
                    "http": {
                        "areq": run_result.get("http"),
                    },
                    "error": run_result.get("error") or run_result.get("draftError"),
                },
            }
        )

    return results


def _ares_only_result(
    case_id: str,
    case: dict[str, Any],
    case_plan: dict[str, Any] | None,
    case_areq: dict[str, Any],
    run_result: dict[str, Any],
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
) -> dict[str, Any]:
    expected_ares = (
        case.get("expected", {})
        .get("messages", {})
        .get("ARes", {})
    )
    actual_ares = run_result.get("ares") if isinstance(run_result.get("ares"), dict) else {}
    keys = ["transStatus", "transStatusReason"]
    mismatches = {
        key: {"expected": expected_ares.get(key), "actual": actual_ares.get(key)}
        for key in keys
        if expected_ares.get(key) is not None and expected_ares.get(key) != actual_ares.get(key)
    }
    passed = run_result.get("ok") is True and not mismatches
    reason = (
        "ARes matched expected values."
        if passed
        else (
            _acs_error_reason(actual_ares)
            if _is_acs_error(actual_ares)
            else f"ARes mismatched values: {mismatches}."
        )
    )
    return {
        "caseId": case_id,
        "status": "pass" if passed else "fail",
        "reason": reason,
        "case": case,
        "details": {
            "expected": case.get("expected", {}),
            "issuerMode": issuer_mode,
            "preferredChallenge": preferred_challenge,
            "casePlan": case_plan,
            "caseAreq": case_areq,
            "ares": actual_ares,
            "cres": None,
            "aresMismatches": mismatches,
            "http": {
                "areq": run_result.get("http"),
            },
            "error": run_result.get("error") or run_result.get("draftError"),
        },
    }


def _run_error_case(
    case_id: str,
    case: dict[str, Any],
    case_plan: dict[str, Any] | None,
    envelope: dict[str, Any],
    notification_url: str,
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
    case_areq: dict[str, Any],
) -> dict[str, Any]:
    envelope = {**envelope, "autoSubmitOtp": False}
    run_result = _run_areq_flow(envelope, notification_url)
    case_areq["actualRequestBody"] = (
        ((run_result.get("http") or {}).get("request_body"))
        if isinstance(run_result.get("http"), dict)
        else None
    )
    expected_error = ((case.get("expected", {}) or {}).get("errors") or [{}])[0]
    actual_error_source = _actual_error_source(run_result)
    missing = _missing_error_fields(expected_error, actual_error_source)
    passed = run_result.get("ok") is True and not missing
    return {
        "caseId": case_id,
        "status": "pass" if passed else "fail",
        "reason": (
            "Expected error fields were found."
            if passed
            else f"Missing expected error fields: {missing}."
        ),
        "case": case,
        "details": {
            "expected": case.get("expected", {}),
            "issuerMode": issuer_mode,
            "preferredChallenge": preferred_challenge,
            "casePlan": case_plan,
            "caseAreq": case_areq,
            "errorMatch": {
                "expected": expected_error,
                "actual": actual_error_source,
                "missing": missing,
            },
            "ares": run_result.get("ares"),
            "cres": None,
            "http": {
                "areq": run_result.get("http"),
            },
            "error": run_result.get("error") or run_result.get("draftError"),
        },
    }


def _actual_error_source(run_result: dict[str, Any]) -> Any:
    ares = run_result.get("ares")
    if ares:
        return ares
    http = run_result.get("http")
    if isinstance(http, dict):
        return http.get("response_json") or http.get("response_text") or http.get("error")
    return run_result.get("error")


def _missing_error_fields(expected_error: dict[str, Any], actual_error_source: Any) -> list[str]:
    haystack = json.dumps(actual_error_source, ensure_ascii=False) if not isinstance(actual_error_source, str) else actual_error_source
    field_aliases = {
        "code": ("errorCode", "code"),
        "description": ("errorDescription", "description"),
        "detail": ("errorDetail", "detail"),
        "component": ("errorComponent", "component"),
    }
    missing: list[str] = []
    for field, expected_value in expected_error.items():
        if expected_value in (None, ""):
            continue
        if isinstance(actual_error_source, dict):
            aliases = field_aliases.get(field, (field,))
            actual_values = [str(actual_error_source.get(alias, "")) for alias in aliases]
            if str(expected_value) in actual_values:
                continue
        if str(expected_value) not in haystack:
            missing.append(field)
    return missing


def _run_transaction_case(
    case_id: str,
    case: dict[str, Any],
    case_plan: dict[str, Any] | None,
    envelope: dict[str, Any],
    notification_url: str,
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
    case_areq: dict[str, Any],
) -> dict[str, Any]:
    expected_transactions = (case.get("expected", {}) or {}).get("transactions") or []
    otp_attempts_by_transaction = _otp_attempts_by_transaction(
        case_plan,
        _read_otp_failure_max_attempts(envelope),
    )
    transaction_results: list[dict[str, Any]] = []
    actual_request_bodies: list[Any] = []

    for index, expected_transaction in enumerate(expected_transactions):
        transaction_envelope = {
            **envelope,
            "otpAttempts": (
                otp_attempts_by_transaction[index]
                if index < len(otp_attempts_by_transaction)
                else []
            ),
        }
        if not transaction_envelope["otpAttempts"]:
            transaction_envelope["autoSubmitOtp"] = False

        run_result = _run_areq_flow(transaction_envelope, notification_url)
        request_body = (
            ((run_result.get("http") or {}).get("request_body"))
            if isinstance(run_result.get("http"), dict)
            else None
        )
        actual_request_bodies.append(request_body)

        expected_status = (
            (expected_transaction.get("messages") or {})
            .get("CRes", {})
            .get("transStatus")
        )
        cres = (run_result.get("autoCreq") or {}).get("cres") if isinstance(run_result.get("autoCreq"), dict) else None
        actual_status = cres.get("transStatus") if isinstance(cres, dict) else None
        transaction_results.append(
            {
                "index": index,
                "label": expected_transaction.get("label", ""),
                "expectedStatus": expected_status,
                "actualStatus": actual_status,
                "passed": run_result.get("ok") is True and expected_status == actual_status,
                "ares": run_result.get("ares"),
                "cres": cres,
                "notification": _notification_from_auto_creq(run_result.get("autoCreq")),
                "http": {"areq": run_result.get("http")},
                "error": run_result.get("error") or run_result.get("draftError"),
            }
        )

    case_areq["actualRequestBody"] = actual_request_bodies[0] if actual_request_bodies else None
    case_areq["actualRequestBodies"] = actual_request_bodies

    passed = bool(transaction_results) and all(item["passed"] for item in transaction_results)
    expected_statuses = [item["expectedStatus"] for item in transaction_results]
    actual_statuses = [item["actualStatus"] for item in transaction_results]
    return {
        "caseId": case_id,
        "status": "pass" if passed else "fail",
        "reason": (
            f"Transaction CRes statuses matched {expected_statuses}."
            if passed
            else f"Expected transaction CRes statuses {expected_statuses}, got {actual_statuses}."
        ),
        "case": case,
        "details": {
            "expected": case.get("expected", {}),
            "issuerMode": issuer_mode,
            "preferredChallenge": preferred_challenge,
            "casePlan": case_plan,
            "caseAreq": case_areq,
            "transactions": transaction_results,
        },
    }


def _run_prompt_case(
    case_id: str,
    case: dict[str, Any],
    case_plan: dict[str, Any] | None,
    envelope: dict[str, Any],
    notification_url: str,
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
    case_areq: dict[str, Any],
) -> dict[str, Any]:
    run_result = _run_areq_flow(envelope, notification_url)
    case_areq["actualRequestBody"] = (
        ((run_result.get("http") or {}).get("request_body"))
        if isinstance(run_result.get("http"), dict)
        else None
    )
    expected = case.get("expected", {}) or {}
    expected_prompts = expected.get("prompts") or []
    visible_text = _visible_text_from_run_result(run_result)
    raw_html = _raw_html_from_run_result(run_result)
    excel_fields = expected.get("uiFields") or {}
    field_results = (
        _excel_field_results(excel_fields, visible_text)
        if expected.get("validationMode") == "excel_fields"
        else []
    )
    if _is_acs_error(run_result.get("ares")):
        return {
            "caseId": case_id,
            "status": "fail",
            "reason": _acs_error_reason(run_result.get("ares")),
            "case": case,
            "details": {
                "expected": case.get("expected", {}),
                "issuerMode": issuer_mode,
                "preferredChallenge": preferred_challenge,
                "casePlan": case_plan,
                "caseAreq": case_areq,
                "prompt": {
                    "expected": expected_prompts,
                    "visibleText": visible_text,
                    "missing": expected_prompts,
                    "fields": [{**field, "found": False} for field in field_results],
                    "rawHtml": raw_html,
                },
                "ares": run_result.get("ares"),
                "cres": None,
                "notification": _notification_from_auto_creq(run_result.get("autoCreq")),
                "http": {
                    "areq": run_result.get("http"),
                },
                "error": run_result.get("error") or run_result.get("draftError"),
            },
        }
    missing = (
        [field["expected"] for field in field_results if not field["found"]]
        if field_results
        else _missing_prompt_text(expected_prompts, visible_text)
    )
    passed = run_result.get("ok") is True and bool(visible_text) and not missing
    return {
        "caseId": case_id,
        "status": "pass" if passed else "fail",
        "reason": (
            "Expected prompt text was found."
            if passed
            else (
                f"Missing expected prompt text: {missing}."
                if visible_text
                else "No challenge page text was captured."
            )
        ),
        "case": case,
        "details": {
            "expected": case.get("expected", {}),
            "issuerMode": issuer_mode,
            "preferredChallenge": preferred_challenge,
            "casePlan": case_plan,
            "caseAreq": case_areq,
            "prompt": {
                "expected": expected_prompts,
                "visibleText": visible_text,
                "missing": missing,
                "fields": field_results,
                "rawHtml": raw_html,
            },
            "ares": run_result.get("ares"),
            "cres": None,
            "notification": _notification_from_auto_creq(run_result.get("autoCreq")),
            "http": {
                "areq": run_result.get("http"),
            },
            "error": run_result.get("error") or run_result.get("draftError"),
        },
    }


def _run_resend_limit_case(
    case_id: str,
    case: dict[str, Any],
    case_plan: dict[str, Any] | None,
    envelope: dict[str, Any],
    notification_url: str,
    issuer_mode: dict[str, Any],
    preferred_challenge: str,
    case_areq: dict[str, Any],
) -> dict[str, Any]:
    run_result = _run_areq_flow(envelope, notification_url)
    case_areq["actualRequestBody"] = (
        ((run_result.get("http") or {}).get("request_body"))
        if isinstance(run_result.get("http"), dict)
        else None
    )
    auto_creq = run_result.get("autoCreq") if isinstance(run_result.get("autoCreq"), dict) else {}
    submissions = auto_creq.get("resendSubmissions") if isinstance(auto_creq, dict) else []
    if not isinstance(submissions, list):
        submissions = []
    limit_reached = bool(auto_creq.get("resendLimitReached")) if isinstance(auto_creq, dict) else False
    passed = run_result.get("ok") is True and limit_reached and bool(submissions)
    return {
        "caseId": case_id,
        "status": "pass" if passed else "fail",
        "reason": (
            f"Resend limit reached after {len(submissions)} resend attempt(s)."
            if passed
            else "Resend limit was not reached."
        ),
        "case": case,
        "details": {
            "expected": case.get("expected", {}),
            "issuerMode": issuer_mode,
            "preferredChallenge": preferred_challenge,
            "casePlan": case_plan,
            "caseAreq": case_areq,
            "resendLimit": {
                "attemptCount": len(submissions),
                "maxAttempts": envelope.get("resendMaxAttempts"),
                "reached": limit_reached,
                "reason": auto_creq.get("resendLimitReason") if isinstance(auto_creq, dict) else "",
                "submissions": submissions,
            },
            "ares": run_result.get("ares"),
            "cres": auto_creq.get("cres") if isinstance(auto_creq, dict) else None,
            "notification": _notification_from_auto_creq(auto_creq),
            "http": {
                "areq": run_result.get("http"),
            },
            "error": run_result.get("error") or run_result.get("draftError"),
        },
    }


def _visible_text_from_run_result(run_result: dict[str, Any]) -> list[str]:
    auto_creq = run_result.get("autoCreq")
    if not isinstance(auto_creq, dict):
        return []
    visible_text: list[str] = []
    for path in (
        ("challenge",),
        ("smsSelection", "challenge"),
        ("oobSubmission", "challenge"),
        ("otpSubmission", "challenge"),
        ("resendSubmission", "challenge"),
    ):
        value: Any = auto_creq
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, dict) and isinstance(value.get("visibleText"), list):
            visible_text.extend(str(item) for item in value["visibleText"])
    for collection_name in ("otpSubmissions", "resendSubmissions"):
        for submission in auto_creq.get(collection_name) or []:
            value = submission.get("challenge") if isinstance(submission, dict) else None
            if isinstance(value, dict) and isinstance(value.get("visibleText"), list):
                visible_text.extend(str(item) for item in value["visibleText"])
    return list(dict.fromkeys(visible_text))


def _raw_html_from_run_result(run_result: dict[str, Any]) -> list[dict[str, str]]:
    auto_creq = run_result.get("autoCreq")
    if not isinstance(auto_creq, dict):
        return []
    pages = []
    for stage, path in (
        ("challenge", ("challenge",)),
        ("smsSelection", ("smsSelection", "challenge")),
        ("oobSubmission", ("oobSubmission", "challenge")),
        ("otpSubmission", ("otpSubmission", "challenge")),
        ("resendSubmission", ("resendSubmission", "challenge")),
    ):
        value: Any = auto_creq
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        raw_html = value.get("rawHtml") if isinstance(value, dict) else None
        if isinstance(raw_html, str) and raw_html:
            pages.append({"stage": stage, "html": raw_html})
    for collection_name in ("otpSubmissions", "resendSubmissions"):
        for index, submission in enumerate(auto_creq.get(collection_name) or []):
            page = submission.get("challenge") if isinstance(submission, dict) else None
            raw_html = page.get("rawHtml") if isinstance(page, dict) else None
            if isinstance(raw_html, str) and raw_html:
                pages.append({"stage": f"{collection_name}[{index}]", "html": raw_html})
    return pages


def _missing_prompt_text(expected_prompts: list[Any], visible_text: list[str]) -> list[str]:
    visible = "\n".join(visible_text)
    missing = []
    for prompt in expected_prompts:
        text = str(prompt)
        normalized = _normalize_expected_prompt_text(text)
        if not normalized:
            continue
        if not _expected_prompt_matches(normalized, visible):
            missing.append(text)
    return missing


def _excel_field_results(fields: dict[str, Any], visible_text: list[str]) -> list[dict[str, Any]]:
    visible = " ".join(" ".join(str(item).split()) for item in visible_text)
    results = []
    for name, value in fields.items():
        expected = str(value or "").strip()
        if not expected:
            continue
        normalized = " ".join(visible_text_from_html(expected).split())
        results.append(
            {
                "name": str(name),
                "expected": expected,
                "found": bool(normalized) and _excel_text_matches(normalized, visible),
            }
        )
    return results


def _excel_text_matches(expected: str, visible: str) -> bool:
    parts = re.split(r"(\{\d+\})", expected)
    pattern = []
    for part in parts:
        if re.fullmatch(r"\{\d+\}", part):
            pattern.append(r".+?")
            continue
        pattern.append(r"\s+".join(re.escape(word) for word in part.split()))
    return re.search("".join(pattern), visible, flags=re.DOTALL) is not None


def _expected_prompt_matches(expected: str, visible: str) -> bool:
    if not re.search(r"\{\d+\}|<br\s*/?>", expected, flags=re.IGNORECASE):
        return expected in visible
    parts = re.split(r"(\{\d+\}|<br\s*/?>)", expected, flags=re.IGNORECASE)
    pattern_parts: list[str] = []
    for part in parts:
        if re.fullmatch(r"\{\d+\}", part):
            pattern_parts.append(r".+?")
        elif re.fullmatch(r"<br\s*/?>", part, flags=re.IGNORECASE):
            pattern_parts.append(r"\s*")
        else:
            pattern_parts.append(re.escape(part))
    return re.search("".join(pattern_parts), visible, flags=re.DOTALL) is not None


def _normalize_expected_prompt_text(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    lower_text = text.lower()
    if lower_text.startswith("display prompt") or lower_text.startswith("ui and page format"):
        return ""
    if lower_text.startswith("page content"):
        return ""
    if lower_text.startswith("help title:") or lower_text.startswith("help content:"):
        return ""
    merchant_prefixes = (
        "Merchant:",
        "商店:",
        "ชื่อผู้ค้า:",
        "ผู้ค้า:",
        "ពាណិជ្ជករ:",
    )
    if any(text.startswith(prefix) for prefix in merchant_prefixes):
        return ""
    for prefix in (
        "Title：",
        "Title:",
        "Input Prompt:",
        "Submit OTP button:",
        "Resend OTP button:",
        "Help Title:",
        "Help Content:",
    ):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    dynamic_prefixes = (
        "Amount:",
        "Total amount:",
        "Transaction time:",
        "Transaction date:",
        "Card number:",
        "购买金额:",
        "购买日期:",
        "卡号:",
        "ยอดรวมทั้งหมด:",
        "วันที่/เวลาทำธุรกรรม:",
        "วันที่/เวลาทำรายการ:",
        "หมายเลขบัตร",
        "ចំនួនទឹកប្រាក់សរុប:",
        "កាលបរិច្ឆេទប្រតិបត្តិការ/ពេលវេលា:",
    )
    if text.startswith(dynamic_prefixes):
        return ""
    if "******" in text or "************" in text:
        return ""
    return text


def _otp_attempts_by_transaction(
    case_plan: dict[str, Any] | None,
    failure_max_attempts: int = 5,
) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] | None = None
    for action in (case_plan or {}).get("actions") or []:
        action_type = action.get("type")
        if action_type == "send_areq":
            if current is not None:
                segments.append(current)
            current = []
            continue
        if action_type == "submit_otp" and current is not None:
            current.append(str(action.get("otpPurpose") or "success"))
    if current is not None:
        segments.append(current)
    return [_expand_failure_attempt_segment(segment, failure_max_attempts) for segment in segments]


def _expand_failure_attempt_segment(segment: list[str], failure_max_attempts: int) -> list[str]:
    if segment and all(item == "failure" for item in segment):
        return ["failure"] * max(1, failure_max_attempts)
    return segment


def _case_areq_record(case_id: str, transaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "caseId": case_id,
        "sharedAcrossIssuerModes": True,
        "url": str(transaction.get("url") or ""),
        "headers": deepcopy(transaction.get("headers") or {}),
        "payloadTemplate": deepcopy(transaction.get("payload")),
        "actualRequestBody": None,
    }


def _transaction_for_case(case: dict[str, Any], transaction: dict[str, Any]) -> dict[str, Any]:
    case_transaction = deepcopy(transaction)
    case_id = str(case.get("baseCaseId") or case.get("id") or "")
    payload = deepcopy(case_transaction.get("payload"))
    if isinstance(payload, dict):
        card_number = _card_number_for_case(case, case_transaction)
        if card_number:
            payload["acctNumber"] = card_number
        browser_language = _browser_language_for_case(case)
        if browser_language:
            payload["browserLanguage"] = browser_language
        tags = set((case.get("automation") or {}).get("tags") or [])
        if "npa" in tags:
            payload["messageCategory"] = "02"
        elif "pa" in tags:
            payload["messageCategory"] = "01"
        if "3ri" in tags:
            payload["messageCategory"] = "02"
            payload["deviceChannel"] = "03"
            payload["threeDSRequestorAuthenticationInd"] = "01"
            payload["threeRIInd"] = "03"
        purchase_currency = {
            "case18": "840",
            "case19": "156",
            "case20": "978",
        }.get(case_id)
        if purchase_currency:
            payload["purchaseCurrency"] = purchase_currency
        case_transaction["payload"] = payload
    if case_id in {"case35", "case36", "case37", "case38", "case43", "case44", "case45", "case46"}:
        case_transaction["resendDelaySeconds"] = 30
    elif case_id in {"case39", "case40", "case41", "case42"}:
        case_transaction["resendDelaySeconds"] = 0
    return case_transaction


def _browser_language_for_case(case: dict[str, Any]) -> str:
    configured = str(case.get("browserLanguage") or "").strip()
    if configured:
        return configured
    name = str(case.get("functionPoint") or "").lower()
    if "simplified chinese" in name:
        return "zh-CN"
    if "thai" in name:
        return "th-TH"
    if "khmer" in name:
        return "km-KH"
    if "english" in name:
        return "en-US"
    return ""


def _challenge_headers_for_payload(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    browser_language = str(payload.get("browserLanguage") or "").strip()
    return {"Accept-Language": browser_language} if browser_language else {}


def _card_number_for_case(case: dict[str, Any], transaction: dict[str, Any]) -> str:
    if _is_invalid_card_case(case):
        return str(
            transaction.get("invalidCardNumber")
            or transaction.get("failedCardNumber")
            or transaction.get("failureCardNumber")
            or ""
        )
    return str(
        transaction.get("validCardNumber")
        or transaction.get("correctCardNumber")
        or ""
    )


def _is_invalid_card_case(case: dict[str, Any]) -> bool:
    tags = set((case.get("automation") or {}).get("tags") or [])
    return "invalid_card" in tags


def _case_plan_for_issuer_mode(
    case: dict[str, Any],
    issuer_mode: dict[str, Any],
) -> dict[str, Any] | None:
    if issuer_mode.get("id") in {
        "sms_otp",
        "email_otp",
        "direct_oob",
        "selection_sms_oob",
        "selection_sms_email",
        "selection_sms_email_oob",
        "selection_email_oob",
        "default_oob_can_switch_otp",
    }:
        return build_case_plan(case, issuer_mode)
    return None


def _preferred_challenge_for_case_plan(
    case_plan: dict[str, Any] | None,
    fallback: str,
) -> str:
    preferred = str((case_plan or {}).get("preferredChallenge") or "")
    return preferred if preferred and preferred != "auto" else fallback


def _notification_from_auto_creq(auto_creq: Any) -> Any:
    if not isinstance(auto_creq, dict):
        return None
    otp_submission = auto_creq.get("otpSubmission")
    if isinstance(otp_submission, dict) and otp_submission.get("notification") is not None:
        return otp_submission.get("notification")
    return auto_creq.get("notification")


def _summarize_sit_results(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "completed": len(results),
        "pass": 0,
        "fail": 0,
        "skipped": 0,
        "error": 0,
    }
    for result in results:
        status = str(result.get("status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def _profile_issuer_mode(profiles: dict[str, Any], requested_mode: str) -> str:
    requested = requested_mode or "sms_otp"
    canonical = resolve_issuer_mode(requested)["id"]
    if profiles.get("sourceFormat") != "challenge_ui_info" and canonical == "sms_otp":
        configured_modes = {
            str(mode)
            for issuer in (profiles.get("issuers") or {}).values()
            for mode in issuer.get("issuerModes") or []
        }
        if "direct_otp" in configured_modes:
            return "direct_otp"
    return canonical


def _generated_wording_case_count(catalog: dict[str, Any]) -> int:
    return sum(1 for case in catalog.get("cases") or [] if case.get("wording"))


def _expected_actual_reason(label: str, expected: Any, actual: Any) -> str:
    return f"預期 {label}={expected}，實際={actual}."


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
    challenge_action: str = "",
    resend_max_attempts: int = 10,
    challenge_headers: dict[str, str] | None = None,
    resend_delay_seconds: float = 0,
) -> dict[str, Any]:
    issuer_mode = issuer_mode or resolve_issuer_mode("")
    preferred_challenge = resolve_preferred_challenge(preferred_challenge)
    otp_settings = otp_settings or OtpSettings(success_otp=simulated_otp or "123456")
    otp_attempts = otp_attempts or (["success"] if auto_submit_otp and (simulated_otp or otp_settings.success_otp) else [])
    http = post_form(
        url,
        {"creq": b64url_json(creq), "threeDSSessionData": ""},
        headers=challenge_headers,
        timeout_seconds=timeout_seconds,
    )
    page = parse_challenge_page(http.response_text, url) if http.response_text else None
    if page is not None:
        page["requestHeaders"] = dict(challenge_headers or {})
    cres = page.get("cres") if page else None
    response = _creq_response(http, cres, build_next_creq_draft(cres, creq))
    response["challenge"] = page
    response["smsSelection"] = None
    response["oobSubmission"] = None
    response["otpSubmission"] = None
    response["otpSubmissions"] = []
    response["resendSubmission"] = None
    response["resendSubmissions"] = []
    response["resendLimitReached"] = False
    response["resendLimitReason"] = ""
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
            challenge_action,
            resend_max_attempts,
            resend_delay_seconds,
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
            challenge_action,
            resend_max_attempts,
            resend_delay_seconds,
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
    challenge_action: str = "",
    resend_max_attempts: int = 10,
    resend_delay_seconds: float = 0,
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
                challenge_action,
                resend_max_attempts,
                resend_delay_seconds,
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

    if challenge_action == "cancel" and page["type"] in {"otp", "html"}:
        cancel_response = _submit_challenge_form(
            page,
            _cancel_challenge_overrides(page),
            timeout_seconds,
        )
        response["cancelSubmission"] = {
            "action": "cancel",
            **cancel_response,
        }
        if cancel_response.get("cres"):
            _apply_final_challenge_response(
                response,
                "cancelSubmission",
                cancel_response,
                previous_creq,
                notification_url,
                timeout_seconds,
            )
        return

    if challenge_action == "resend_limit" and page["type"] in {"otp", "html"}:
        _resend_until_limit(
            response,
            page,
            previous_creq,
            timeout_seconds,
            notification_url,
            resend_max_attempts,
            resend_delay_seconds,
        )
        return

    if challenge_action == "resend" and page["type"] in {"otp", "html"}:
        if resend_delay_seconds > 0:
            time.sleep(resend_delay_seconds)
        resend_response = _submit_challenge_form(
            page,
            _resend_otp_overrides(page),
            timeout_seconds,
        )
        response["resendSubmission"] = {
            "action": "resend",
            **resend_response,
        }
        if resend_response.get("cres"):
            _apply_final_challenge_response(
                response,
                "resendSubmission",
                resend_response,
                previous_creq,
                notification_url,
                timeout_seconds,
            )
        return

    if page["type"] == "otp" and auto_submit_otp and otp_attempts:
        current_page = page
        completed = False
        for purpose in otp_attempts:
            max_attempts = (
                2
                if purpose == "success" and otp_settings.source_mode == "acs_generated"
                else 1
            )
            for attempt in range(max_attempts):
                if attempt > 0:
                    time.sleep(1.0)
                acs_trans_id = str(
                    (current_page.get("fields") or {}).get("acsTransID")
                    or previous_creq.get("acsTransID")
                    or ""
                )
                otp_value, otp_lookup = _resolve_otp_submission_value(
                    purpose,
                    acs_trans_id,
                    otp_settings,
                    timeout_seconds,
                )
                otp_response = _submit_challenge_form(
                    current_page,
                    {"challengeValue": otp_value},
                    timeout_seconds,
                )
                submission = {
                    "simulatedOtpUsed": otp_lookup.get("source") in {
                        "configured",
                        "simulated",
                        "simulated_fallback",
                    },
                    "otpSourceMode": otp_settings.source_mode,
                    "otpPurpose": purpose,
                    "otpLength": len(otp_value),
                    "otpLookup": otp_lookup,
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
                    completed = True
                    break
                next_page = otp_response.get("challenge")
                if not next_page or next_page.get("type") != "otp":
                    completed = True
                    break
                current_page = next_page
            if completed:
                break


def _resend_until_limit(
    response: dict[str, Any],
    page: dict[str, Any],
    previous_creq: dict[str, Any],
    timeout_seconds: int,
    notification_url: str,
    max_attempts: int,
    resend_delay_seconds: float = 0,
) -> None:
    current_page = page
    max_attempts = max(1, max_attempts)
    response.setdefault("resendSubmission", None)
    response.setdefault("resendSubmissions", [])
    response.setdefault("resendLimitReached", False)
    response.setdefault("resendLimitReason", "")
    for attempt in range(1, max_attempts + 1):
        if not _page_has_resend_action(current_page):
            response["resendLimitReached"] = bool(response["resendSubmissions"])
            response["resendLimitReason"] = "Resend control is no longer available."
            return

        if resend_delay_seconds > 0:
            time.sleep(resend_delay_seconds)
        resend_response = _submit_challenge_form(
            current_page,
            _resend_otp_overrides(current_page),
            timeout_seconds,
        )
        submission = {
            "action": "resend",
            "attempt": attempt,
            **resend_response,
        }
        response["resendSubmission"] = submission
        response["resendSubmissions"].append(submission)
        if resend_response.get("cres"):
            _apply_final_challenge_response(
                response,
                "resendSubmission",
                resend_response,
                previous_creq,
                notification_url,
                timeout_seconds,
            )
            response["resendLimitReached"] = True
            response["resendLimitReason"] = "Final CRes returned during resend."
            return

        next_page = resend_response.get("challenge")
        if not next_page:
            response["resendLimitReached"] = True
            response["resendLimitReason"] = "No challenge page returned after resend."
            return
        current_page = next_page

    response["resendLimitReached"] = False
    response["resendLimitReason"] = f"Safety max attempts reached ({max_attempts}) while resend control is still available."


def _page_has_resend_action(page: dict[str, Any] | None) -> bool:
    if not page:
        return False
    return bool((page.get("availableActions") or {}).get("resendOtp"))


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
    requested = preferred_challenge
    if issuer_mode["id"] == "selection_sms_otp":
        requested = "sms"
    elif requested == "auto":
        requested = str(issuer_mode.get("defaultPreferredChallenge") or "sms")

    label_terms = {
        "sms": ("sms", "text message", "mobile number"),
        "email": ("email", "e-mail", "mail"),
        "oob": ("oob", "mobile app", "application", "push", "app approval"),
        "otp": ("sms", "otp", "passcode"),
    }
    terms = label_terms.get(requested, ())
    for option in page.get("radioOptions") or []:
        if option.get("name") != "challengeValue":
            continue
        label = str(option.get("label") or "").lower()
        if any(term in label for term in terms):
            return str(option.get("value") or "")

    if issuer_mode["id"] == "selection_sms_otp":
        preferred_values = ["1", "2", "3"]
    elif preferred_challenge in {"oob"} or issuer_mode["id"] == "direct_oob":
        preferred_values = ["3", "2", "1"]
    elif preferred_challenge == "email":
        preferred_values = ["2", "1", "3"]
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


def _cancel_challenge_overrides(page: dict[str, Any]) -> dict[str, str]:
    fields = page.get("fields") or {}
    for name in ("cancel", "cancelChallenge", "challengeCancel", "cancelTransaction", "cancelButton"):
        if name in fields:
            return {name: "true" if name == "cancel" else "Y"}
    return {"cancel": "true"}


def _resend_otp_overrides(page: dict[str, Any]) -> dict[str, str]:
    fields = page.get("fields") or {}
    controls = page.get("actionControls") or []
    resend_names = (
        "resend",
        "resendCode",
        "resendOtp",
        "resendOTP",
        "resendButton",
        "resendChallenge",
    )
    for name in resend_names:
        if name in fields:
            return {name: fields.get(name) or "Y"}
    for control in controls:
        name = str(control.get("name") or "")
        if name and "resend" in name.lower():
            return {name: str(control.get("value") or "Y")}
    return {"resend": "Y"}


def _submit_challenge_form(
    page: dict[str, Any],
    overrides: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    fields = dict(page.get("fields") or {})
    fields.update(overrides)
    request_headers = dict(page.get("requestHeaders") or {})
    http = post_form(
        page["formAction"],
        fields,
        headers=request_headers,
        timeout_seconds=timeout_seconds,
    )
    next_page = parse_challenge_page(http.response_text, page["formAction"]) if http.response_text else None
    if next_page is not None:
        next_page["requestHeaders"] = request_headers
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
    lookup_url_template = str(
        envelope.get("otpLookupUrl")
        or "https://acscloud-test.hitrust-us.com/acs-sit-info/api/sit/otp/{acsTrandId}"
    )
    if source_mode not in {"customer_generated", "acs_generated"}:
        raise ValueError("otpSourceMode must be customer_generated or acs_generated.")
    return OtpSettings(
        source_mode=source_mode,
        success_otp=success_otp,
        failure_otp=failure_otp,
        lookup_url_template=lookup_url_template,
    )


def _resolve_otp_submission_value(
    purpose: str,
    acs_trans_id: str,
    otp_settings: OtpSettings,
    timeout_seconds: int,
) -> tuple[str, dict[str, Any]]:
    normalized_purpose = (purpose or "success").strip()
    if normalized_purpose == "success" and otp_settings.source_mode == "acs_generated":
        return lookup_acs_generated_otp(
            acs_trans_id,
            otp_settings,
            timeout_seconds=timeout_seconds,
        )
    otp_value = resolve_otp_value(normalized_purpose, acs_trans_id, otp_settings)
    return otp_value, {
        "source": "configured" if otp_settings.source_mode == "customer_generated" else "direct",
        "requestedAcsTransID": acs_trans_id,
        "resolvedOtp": otp_value,
        "lookupUsed": False,
    }


def _read_otp_failure_max_attempts(envelope: dict[str, Any]) -> int:
    raw_value = envelope.get("otpFailureMaxAttempts", 5)
    try:
        attempts = int(raw_value)
    except (TypeError, ValueError):
        attempts = 5
    return max(1, attempts)


def _read_case_delay_seconds(envelope: dict[str, Any]) -> float:
    raw_value = envelope.get("caseDelaySeconds", 0)
    try:
        delay = float(raw_value)
    except (TypeError, ValueError):
        delay = 0.0
    return max(0.0, delay)


def _read_resend_delay_seconds(envelope: dict[str, Any]) -> float:
    raw_value = envelope.get("resendDelaySeconds", 0)
    try:
        delay = float(raw_value)
    except (TypeError, ValueError):
        delay = 0.0
    return max(0.0, delay)


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
