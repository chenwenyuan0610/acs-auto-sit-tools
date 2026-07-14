from __future__ import annotations

import base64
import hashlib
from typing import Any


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


def _simulated_cavv(acs_trans_id: str) -> str:
    digest = hashlib.sha256(acs_trans_id.encode("utf-8")).digest()
    return base64.b64encode(digest[:20]).decode("ascii")
