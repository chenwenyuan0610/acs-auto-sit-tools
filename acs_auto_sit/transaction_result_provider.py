from __future__ import annotations

import base64
import hashlib
from typing import Any

from acs_auto_sit.client import get_json


DEFAULT_TRANSACTION_RESULT_URL = (
    "https://acscloud-test.hitrust-us.com/acs-sit-info/api/sit/transaction/{acsTransID}"
)


def simulated_transaction_result_for_acs_trans_id(acs_trans_id: str) -> dict[str, Any]:
    value = (acs_trans_id or "").strip()
    if not value:
        raise ValueError("acsTransID is required.")

    cavv = _simulated_cavv(value)
    return {
        "ok": True,
        "source": "simulated",
        "acsTransID": value,
        "transaction": {
            "transStatus": "Y",
            "eci": "02",
            "cavv": cavv,
            "cavvPresent": True,
        },
        "checks": {
            "transStatus": {
                "expected": "Y",
                "actual": "Y",
                "status": "pass",
            },
            "eci": {
                "expected": "02",
                "actual": "02",
                "status": "pass",
            },
            "cavv": {
                "expected": "not_null",
                "actual": cavv,
                "status": "pass",
            },
        },
    }


def lookup_transaction_result_for_acs_trans_id(
    acs_trans_id: str,
    url_template: str = DEFAULT_TRANSACTION_RESULT_URL,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    value = (acs_trans_id or "").strip()
    if not value:
        raise ValueError("acsTransID is required.")

    template = (url_template or DEFAULT_TRANSACTION_RESULT_URL).strip()
    url = _transaction_result_url(template, value)
    http = get_json(url, timeout_seconds=timeout_seconds, use_system_proxy=True)
    response = http.response_json if isinstance(http.response_json, dict) else {}
    transaction = response.get("transaction") if isinstance(response.get("transaction"), dict) else response
    return {
        "ok": http.error is None and http.status_code is not None and 200 <= http.status_code < 300,
        "source": "remote",
        "acsTransID": value,
        "transaction": transaction,
        "http": http.to_dict(),
        "error": http.error,
    }


def _transaction_result_url(template: str, acs_trans_id: str) -> str:
    return (
        template
        .replace("{acsTransID}", acs_trans_id)
        .replace("{acsTransId}", acs_trans_id)
        .replace("{acsTrandId}", acs_trans_id)
    )


def _simulated_cavv(acs_trans_id: str) -> str:
    digest = hashlib.sha256(acs_trans_id.encode("utf-8")).digest()
    return base64.b64encode(digest[:20]).decode("ascii")
