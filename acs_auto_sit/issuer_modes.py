from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_ISSUER_MODE = "direct_otp"
DEFAULT_PREFERRED_CHALLENGE = "auto"

ISSUER_MODES: list[dict[str, Any]] = [
    {
        "id": "selection_sms_oob",
        "label": "Has selection: SMS / OOB",
        "description": "Issuer shows a verification selection page; runner can choose SMS or OOB.",
        "defaultPreferredChallenge": "sms",
    },
    {
        "id": "selection_sms_otp",
        "label": "Has selection: choose SMS, then OTP",
        "description": "Issuer shows a verification selection page; runner chooses SMS and enters OTP.",
        "defaultPreferredChallenge": "sms",
    },
    {
        "id": "direct_otp",
        "label": "Direct OTP",
        "description": "Issuer skips verification selection and enters OTP challenge directly.",
        "defaultPreferredChallenge": "otp",
    },
    {
        "id": "direct_oob",
        "label": "Direct OOB",
        "description": "Issuer skips verification selection and enters OOB challenge directly.",
        "defaultPreferredChallenge": "oob",
    },
    {
        "id": "default_oob_can_switch_otp",
        "label": "Default OOB, switchable to OTP",
        "description": "Issuer enters OOB by default and exposes a switch action to OTP.",
        "defaultPreferredChallenge": "oob",
    },
]

PREFERRED_CHALLENGES: list[dict[str, str]] = [
    {"id": "auto", "label": "Auto"},
    {"id": "sms", "label": "SMS"},
    {"id": "oob", "label": "OOB"},
    {"id": "otp", "label": "OTP"},
]


def issuer_mode_catalog() -> dict[str, Any]:
    return {
        "issuerModes": deepcopy(ISSUER_MODES),
        "preferredChallenges": deepcopy(PREFERRED_CHALLENGES),
        "defaultIssuerMode": DEFAULT_ISSUER_MODE,
        "defaultPreferredChallenge": DEFAULT_PREFERRED_CHALLENGE,
    }


def resolve_issuer_mode(mode_id: str | None) -> dict[str, Any]:
    selected = (mode_id or DEFAULT_ISSUER_MODE).strip() or DEFAULT_ISSUER_MODE
    for mode in ISSUER_MODES:
        if mode["id"] == selected:
            return deepcopy(mode)
    raise ValueError(f"Unsupported issuerMode: {selected}")


def resolve_preferred_challenge(value: str | None) -> str:
    selected = (value or DEFAULT_PREFERRED_CHALLENGE).strip() or DEFAULT_PREFERRED_CHALLENGE
    allowed = {item["id"] for item in PREFERRED_CHALLENGES}
    if selected not in allowed:
        raise ValueError(f"Unsupported preferredChallenge: {selected}")
    return selected
