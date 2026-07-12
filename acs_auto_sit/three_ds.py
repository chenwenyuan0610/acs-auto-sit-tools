from __future__ import annotations

from typing import Any


def requires_challenge(message: dict[str, Any] | None) -> bool:
    return isinstance(message, dict) and message.get("transStatus") == "C"


def extract_acs_values(message: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}

    keys = ("transStatus", "acsURL", "acsTransID", "threeDSServerTransID")
    return {key: message[key] for key in keys if key in message}


def build_first_creq(
    ares: dict[str, Any] | None,
    areq: dict[str, Any] | None,
    challenge_window_size: str = "05",
) -> dict[str, Any] | None:
    if not requires_challenge(ares):
        return None

    ares = ares or {}
    areq = areq or {}
    acs_trans_id = ares.get("acsTransID")
    server_trans_id = ares.get("threeDSServerTransID") or areq.get("threeDSServerTransID")
    message_version = ares.get("messageVersion") or areq.get("messageVersion") or "2.2.0"

    missing = [
        name
        for name, value in (
            ("acsTransID", acs_trans_id),
            ("threeDSServerTransID", server_trans_id),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"ARes is missing fields required for CReq: {', '.join(missing)}")

    return {
        "messageType": "CReq",
        "messageVersion": message_version,
        "threeDSServerTransID": server_trans_id,
        "acsTransID": acs_trans_id,
        "challengeWindowSize": challenge_window_size,
    }


def build_next_creq_draft(
    cres: dict[str, Any] | None,
    previous_creq: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not requires_challenge(cres):
        return None

    previous_creq = previous_creq or {}
    draft = {
        "messageType": "CReq",
        "messageVersion": previous_creq.get("messageVersion") or "2.2.0",
        "threeDSServerTransID": previous_creq.get("threeDSServerTransID"),
        "acsTransID": previous_creq.get("acsTransID"),
        "challengeDataEntry": "",
    }
    if previous_creq.get("challengeWindowSize"):
        draft["challengeWindowSize"] = previous_creq["challengeWindowSize"]
    return draft
