from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from acs_auto_sit.client import get_json


@dataclass(frozen=True, slots=True)
class OtpSettings:
    source_mode: str = "customer_generated"
    success_otp: str = "123456"
    failure_otp: str = "000000"
    lookup_url_template: str = ""


def simulated_otp_for_acs_trans_id(acs_trans_id: str) -> str:
    digest = hashlib.sha256(acs_trans_id.encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % 1_000_000:06d}"


def resolve_otp_value(purpose: str, acs_trans_id: str, settings: OtpSettings) -> str:
    purpose = (purpose or "success").strip()
    if purpose == "success":
        if settings.source_mode == "acs_generated":
            return simulated_otp_for_acs_trans_id(acs_trans_id)
        return settings.success_otp
    if purpose == "failure":
        return settings.failure_otp
    if purpose == "empty":
        return ""
    if purpose == "alpha":
        return "ABCDEF"
    if purpose == "special":
        return "!@#$%^"
    if purpose == "expired":
        return settings.success_otp
    return purpose


def lookup_acs_generated_otp(
    acs_trans_id: str,
    settings: OtpSettings,
    timeout_seconds: int = 30,
) -> tuple[str, dict[str, Any]]:
    template = (settings.lookup_url_template or "").strip()
    fallback_otp = simulated_otp_for_acs_trans_id(acs_trans_id)
    if not template:
        return fallback_otp, {
            "source": "simulated",
            "requestedAcsTransID": acs_trans_id,
            "resolvedOtp": fallback_otp,
            "lookupUsed": False,
        }

    url = _format_lookup_url(template, acs_trans_id)
    http = get_json(url, timeout_seconds=timeout_seconds)
    otp = _otp_from_lookup_response(http.response_json)
    if otp:
        return otp, {
            "source": "lookup_api",
            "requestedAcsTransID": acs_trans_id,
            "resolvedOtp": otp,
            "lookupUsed": True,
            "http": http.to_dict(),
        }

    return fallback_otp, {
        "source": "simulated_fallback",
        "requestedAcsTransID": acs_trans_id,
        "resolvedOtp": fallback_otp,
        "lookupUsed": True,
        "http": http.to_dict(),
        "error": "OTP lookup response does not contain a usable OTP value.",
    }


def _format_lookup_url(template: str, acs_trans_id: str) -> str:
    placeholders = (
        "{acsTrandId}",
        "{acsTransID}",
        "{acsTransId}",
        "{acs_trans_id}",
    )
    for placeholder in placeholders:
        if placeholder in template:
            return template.replace(placeholder, acs_trans_id)
    return template.rstrip("/") + "/" + acs_trans_id


def _otp_from_lookup_response(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = (
        payload.get("otp"),
        payload.get("verificationCode"),
        payload.get("challengeValue"),
        payload.get("code"),
    )
    for candidate in candidates:
        value = _otp_candidate(candidate)
        if value:
            return value
    nested = payload.get("data")
    if isinstance(nested, dict):
        return _otp_from_lookup_response(nested)
    return ""


def _otp_candidate(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return _otp_from_lookup_response(value)
    text = str(value).strip()
    if not text:
        return ""
    prefix, separator, suffix = text.rpartition("-")
    if separator and prefix and len(suffix) == 6 and suffix.isdigit():
        return suffix
    return text
