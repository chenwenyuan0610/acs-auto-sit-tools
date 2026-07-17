from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_ISSUER_MODE = "sms_otp"
DEFAULT_PREFERRED_CHALLENGE = "auto"
ISSUER_MODE_ALIASES = {
    "direct_otp": "sms_otp",
    "selection_sms_otp": "selection_sms_oob",
}

ISSUER_MODES: list[dict[str, Any]] = [
    {
        "id": "sms_otp",
        "label": "SMS OTP",
        "description": "Issuer enters an SMS OTP challenge directly.",
        "defaultPreferredChallenge": "sms",
        "destinations": ["sms"],
        "requiresPreferredChallenge": False,
    },
    {
        "id": "email_otp",
        "label": "Email OTP",
        "description": "Issuer enters an Email OTP challenge directly.",
        "defaultPreferredChallenge": "email",
        "destinations": ["email"],
        "requiresPreferredChallenge": False,
    },
    {
        "id": "direct_oob",
        "label": "Direct OOB",
        "description": "Issuer skips verification selection and enters OOB challenge directly.",
        "defaultPreferredChallenge": "oob",
        "destinations": ["oob"],
        "requiresPreferredChallenge": False,
    },
    {
        "id": "selection_sms_oob",
        "label": "Has selection: SMS / OOB",
        "description": "Issuer shows a selection page with SMS and OOB destinations.",
        "defaultPreferredChallenge": "sms",
        "destinations": ["sms", "oob"],
        "requiresPreferredChallenge": True,
    },
    {
        "id": "selection_sms_email",
        "label": "Has selection: SMS / Email",
        "description": "Issuer shows a selection page with SMS and Email destinations.",
        "defaultPreferredChallenge": "sms",
        "destinations": ["sms", "email"],
        "requiresPreferredChallenge": True,
    },
    {
        "id": "selection_sms_email_oob",
        "label": "Has selection: SMS / Email / OOB",
        "description": "Issuer shows a selection page with SMS, Email, and OOB destinations.",
        "defaultPreferredChallenge": "sms",
        "destinations": ["sms", "email", "oob"],
        "requiresPreferredChallenge": True,
    },
    {
        "id": "selection_email_oob",
        "label": "Has selection: Email / OOB",
        "description": "Issuer shows a selection page with Email and OOB destinations.",
        "defaultPreferredChallenge": "email",
        "destinations": ["email", "oob"],
        "requiresPreferredChallenge": True,
    },
    {
        "id": "default_oob_can_switch_otp",
        "label": "Default OOB, switchable to OTP",
        "description": "Issuer enters OOB by default and exposes a switch action to OTP.",
        "defaultPreferredChallenge": "oob",
        "destinations": ["oob", "sms"],
        "switchDestination": "sms",
        "requiresPreferredChallenge": True,
    },
]

PREFERRED_CHALLENGES: list[dict[str, str]] = [
    {"id": "auto", "label": "Auto"},
    {"id": "sms", "label": "SMS"},
    {"id": "email", "label": "Email"},
    {"id": "oob", "label": "OOB"},
    {"id": "otp", "label": "Switch to OTP"},
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
    selected = ISSUER_MODE_ALIASES.get(selected, selected)
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
