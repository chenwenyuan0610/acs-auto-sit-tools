from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit


TERMINAL_STATUSES = {"pass", "fail", "skipped", "error"}


def parse_areq_route(url: str) -> dict[str, str]:
    parts = [part for part in urlsplit(str(url or "")).path.split("/") if part]
    try:
        auth_index = parts.index("auth")
    except ValueError:
        return {"cardScheme": "", "issuerOid": ""}
    tail = parts[auth_index + 1 :]
    if len(tail) < 5 or tail[-1].lower() != "areq":
        return {"cardScheme": "", "issuerOid": ""}
    return {"cardScheme": tail[0], "issuerOid": tail[2]}


def acs_trans_id_for_result(result: dict[str, Any]) -> str:
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    transactions = details.get("transactions") if isinstance(details.get("transactions"), list) else []
    notification = details.get("notification") if isinstance(details.get("notification"), dict) else {}
    nested_notification = (
        notification.get("notification")
        if isinstance(notification.get("notification"), dict)
        else {}
    )
    candidates: list[Any] = [
        _dict_value(details.get("ares"), "acsTransID"),
        _dict_value(details.get("cres"), "acsTransID"),
        _nested_dict_value(nested_notification, "cres", "acsTransID"),
        _nested_dict_value(notification, "cres", "acsTransID"),
    ]
    for transaction in transactions:
        if not isinstance(transaction, dict):
            continue
        transaction_notification = (
            transaction.get("notification")
            if isinstance(transaction.get("notification"), dict)
            else {}
        )
        candidates.extend(
            [
                _dict_value(transaction.get("ares"), "acsTransID"),
                _dict_value(transaction.get("cres"), "acsTransID"),
                _nested_dict_value(transaction_notification, "cres", "acsTransID"),
                _nested_dict_value(
                    transaction_notification.get("notification"),
                    "cres",
                    "acsTransID",
                ),
            ]
        )
    return next(
        (str(value).strip() for value in candidates if str(value or "").strip()),
        "",
    )


def normalize_completed_run(payload: dict[str, Any]) -> dict[str, Any]:
    execution = deepcopy(payload.get("execution") or {})
    results = payload.get("results") if isinstance(payload.get("results"), list) else []
    selected = (
        execution.get("selectedCaseIds")
        if isinstance(execution.get("selectedCaseIds"), list)
        else []
    )
    if not selected:
        raise ValueError("A completed run requires at least one selected case.")
    if len(results) != len(selected) or any(
        not isinstance(item, dict) or item.get("status") not in TERMINAL_STATUSES
        for item in results
    ):
        raise ValueError(
            "All selected cases must have terminal results before saving or reporting."
        )

    execution.update(parse_areq_route(str(execution.get("areqUrl") or "")))
    normalized_results = []
    for item in results:
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        normalized_results.append(
            {
                **deepcopy(item),
                "acsTransID": acs_trans_id_for_result(item),
                "transactionResult": _normalize_transaction_result(details),
            }
        )

    summary = {
        "total": len(normalized_results),
        "completed": len(normalized_results),
        "pass": 0,
        "fail": 0,
        "skipped": 0,
        "error": 0,
    }
    for item in normalized_results:
        summary[str(item["status"])] += 1

    return {
        "schemaVersion": 1,
        "runId": str(payload.get("runId") or "").strip(),
        "startedAt": str(payload.get("startedAt") or ""),
        "finishedAt": str(payload.get("finishedAt") or ""),
        "execution": execution,
        "summary": summary,
        "results": normalized_results,
    }


def _normalize_transaction_result(details: dict[str, Any]) -> dict[str, Any]:
    source = (
        details.get("transactionResult")
        if isinstance(details.get("transactionResult"), dict)
        else {}
    )
    actual = source.get("actual") if isinstance(source.get("actual"), dict) else {}
    lookup = source.get("lookup") if isinstance(source.get("lookup"), dict) else {}
    if not source:
        lookup_status = "not_requested"
    elif source.get("error") or lookup.get("error") or lookup.get("ok") is False:
        lookup_status = "failed"
    else:
        lookup_status = "succeeded"
    mismatches = (
        source.get("mismatches")
        if isinstance(source.get("mismatches"), dict)
        else {}
    )
    return {
        "lookupStatus": lookup_status,
        "transStatus": str(actual.get("transStatus") or ""),
        "eci": str(actual.get("eci") or ""),
        "cavvPresent": actual.get("cavv") not in (None, "", "null"),
        "validationStatus": (
            "fail" if mismatches else ("pass" if actual else "not_checked")
        ),
        "raw": deepcopy(actual),
    }


def _dict_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else ""


def _nested_dict_value(value: Any, child: str, key: str) -> Any:
    if not isinstance(value, dict):
        return ""
    return _dict_value(value.get(child), key)
