from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OtpSettings:
    source_mode: str = "customer_generated"
    success_otp: str = "123456"
    failure_otp: str = "000000"


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
