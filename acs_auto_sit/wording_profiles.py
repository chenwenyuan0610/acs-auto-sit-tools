from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORDING_PROFILES_PATH = PROJECT_ROOT / "data" / "wording_profiles.json"
DEFAULT_SUPPORTED_LOCALES = ("zh_TW", "en_US", "zh_CN")

WORDING_CASE_SCENARIOS = (
    {
        "baseCaseId": "case23",
        "name": "PA Purchase Authentication",
        "messageCategory": "PA",
        "wordingCode": "SEND_SMS_OTP",
        "scenario": "initial_otp",
    },
    {
        "baseCaseId": "case27",
        "name": "NPA Purchase Authentication",
        "messageCategory": "NPA",
        "wordingCode": "SEND_SMS_OTP",
        "scenario": "initial_otp",
    },
    {
        "baseCaseId": "case31",
        "name": "Incorrect OTP Authentication",
        "messageCategory": "PA",
        "wordingCode": "INCORRECT_SMS_OTP",
        "scenario": "incorrect_otp",
    },
    {
        "baseCaseId": "case35",
        "name": "Resend code Authentication",
        "messageCategory": "PA",
        "wordingCode": "RESEND_SMS_OTP",
        "scenario": "resend_success",
    },
    {
        "baseCaseId": "case39",
        "name": "Resend code before interval",
        "messageCategory": "PA",
        "wordingCode": "RESEND_SMS_GAP_LIMIT",
        "scenario": "resend_gap_limit",
    },
    {
        "baseCaseId": "case43",
        "name": "Resend code limit Authentication",
        "messageCategory": "PA",
        "wordingCode": "RESEND_SMS_LIMIT_EXCEED",
        "scenario": "resend_count_limit",
    },
    {
        "baseCaseId": "case47",
        "name": "Expired OTP Authentication",
        "messageCategory": "PA",
        "wordingCode": "SMS_PASSCODE_EXPIRED",
        "scenario": "expired_otp",
    },
)
EXPECTED_FIELD_ORDER = (
    "challenge_title",
    "challenge_message",
    "challenge_label",
    "second_challenge_label",
    "single_select_option",
    "continue_oob_button",
    "next_button",
    "resend_button",
    "help_label",
    "help_text",
)
REQUIRED_WORDING_FIELDS = ("challenge_title", "challenge_message")

ISSUER_SHEET = "發卡行設定"
WORDING_SHEET = "話術匯入"
ISSUER_REQUIRED_COLUMNS = ("啟用", "發卡行代號", "發卡行名稱", "Issuer Mode", "預設語言")
WORDING_REQUIRED_COLUMNS = (
    "啟用匯入",
    "發卡行代號",
    "Issuer Mode",
    "設備通道",
    "訊息類別",
    "編碼代號",
    "語言代碼",
    "欄位代號",
    "話術內容",
)


def import_wording_workbook(
    content: bytes,
    destination: Path = DEFAULT_WORDING_PROFILES_PATH,
    *,
    source_file: str = "",
) -> dict[str, Any]:
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Invalid Excel workbook: {exc}") from exc

    missing_sheets = [name for name in (ISSUER_SHEET, WORDING_SHEET) if name not in workbook.sheetnames]
    if missing_sheets:
        raise ValueError(f"Missing required sheet(s): {', '.join(missing_sheets)}")

    issuer_rows = _sheet_records(workbook[ISSUER_SHEET], ISSUER_REQUIRED_COLUMNS)
    wording_rows = _sheet_records(workbook[WORDING_SHEET], WORDING_REQUIRED_COLUMNS)
    issuers = _normalize_issuers(issuer_rows)
    wordings = _normalize_wordings(wording_rows)
    _add_wording_only_issuers(issuers, wordings)
    _apply_supported_locales(issuers, wordings)

    all_locales = {wording["locale"] for wording in wordings}
    normalized = {
        "version": 1,
        "sourceFile": str(source_file or ""),
        "importedAt": datetime.now(timezone.utc).isoformat(),
        "defaultSupportedLocales": list(DEFAULT_SUPPORTED_LOCALES),
        "issuers": issuers,
        "wordings": wordings,
        "summary": {
            "issuerCount": len(issuers),
            "localeCount": len(all_locales),
            "wordingCount": len(wordings),
        },
    }
    _write_json_atomically(destination, normalized)
    return normalized


def load_wording_profiles(path: Path = DEFAULT_WORDING_PROFILES_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Wording profile JSON must contain an object.")
    return data


def build_localized_wording_cases(
    profiles: dict[str, Any],
    source_cases: list[dict[str, Any]],
    *,
    issuer_id: str = "default",
    issuer_mode: str = "direct_otp",
) -> list[dict[str, Any]]:
    issuers = profiles.get("issuers") or {}
    issuer = issuers.get(issuer_id) or issuers.get("default") or {}
    selected_issuer_id = str(issuer.get("id") or issuer_id or "default")
    locales = issuer.get("supportedLocales") or profiles.get("defaultSupportedLocales") or DEFAULT_SUPPORTED_LOCALES
    templates = {str(case.get("id") or ""): case for case in source_cases}
    wording_index = _wording_field_index(profiles.get("wordings") or [])
    generated: list[dict[str, Any]] = []

    for scenario in WORDING_CASE_SCENARIOS:
        base_case_id = scenario["baseCaseId"]
        if base_case_id not in templates:
            raise ValueError(f"Missing source wording case template: {base_case_id}")
        for locale in locales:
            locale = str(locale)
            fields = _resolve_wording_fields(
                wording_index,
                selected_issuer_id,
                issuer_mode,
                scenario["messageCategory"],
                scenario["wordingCode"],
                locale,
            )
            missing_fields = [field for field in REQUIRED_WORDING_FIELDS if not fields.get(field)]
            enabled = not missing_fields
            reason = "" if enabled else (
                f"Missing wording fields {', '.join(missing_fields)}: issuer={selected_issuer_id}, "
                f"mode={issuer_mode}, code={scenario['wordingCode']}, locale={locale}."
            )
            expected = deepcopy(templates[base_case_id].get("expected") or {})
            expected["prompts"] = [fields[key] for key in EXPECTED_FIELD_ORDER if key in fields]
            expected["uiFields"] = {key: fields[key] for key in EXPECTED_FIELD_ORDER if key in fields}

            case = deepcopy(templates[base_case_id])
            case.update(
                {
                    "id": f"{base_case_id}_{locale}",
                    "baseCaseId": base_case_id,
                    "functionPoint": f"{scenario['name']} ({locale})",
                    "locale": locale,
                    "browserLanguage": locale.replace("_", "-"),
                    "wordingScenario": scenario["scenario"],
                    "wording": {
                        "issuerId": selected_issuer_id,
                        "issuerMode": issuer_mode,
                        "messageCategory": scenario["messageCategory"],
                        "code": scenario["wordingCode"],
                    },
                    "expected": expected,
                    "availability": {"enabled": enabled, "reason": reason},
                }
            )
            generated.append(case)
    return generated


def _wording_field_index(wordings: Iterable[dict[str, Any]]) -> dict[tuple[str, ...], dict[str, str]]:
    index: dict[tuple[str, ...], dict[str, str]] = {}
    for wording in wordings:
        if str(wording.get("deviceChannel") or "").upper() != "BROWSER":
            continue
        key = (
            str(wording.get("issuerId") or "default"),
            str(wording.get("issuerMode") or ""),
            str(wording.get("messageCategory") or "").upper(),
            str(wording.get("wordingCode") or "").upper(),
            str(wording.get("locale") or ""),
        )
        field_key = str(wording.get("fieldKey") or "")
        content = str(wording.get("content") or "")
        if field_key and content:
            index.setdefault(key, {})[field_key] = content
    return index


def _resolve_wording_fields(
    index: dict[tuple[str, ...], dict[str, str]],
    issuer_id: str,
    issuer_mode: str,
    message_category: str,
    wording_code: str,
    locale: str,
) -> dict[str, str]:
    suffix = (issuer_mode, message_category, wording_code, locale)
    fields = dict(index.get(("default", *suffix), {}))
    if issuer_id != "default":
        fields.update(index.get((issuer_id, *suffix), {}))
    return fields


def _sheet_records(sheet: Any, required_columns: Iterable[str]) -> list[dict[str, Any]]:
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        raise ValueError(f"Sheet {sheet.title} is empty.")
    columns = [str(value or "").strip() for value in header]
    missing = [column for column in required_columns if column not in columns]
    if missing:
        raise ValueError(f"Sheet {sheet.title} is missing column(s): {', '.join(missing)}")
    return [dict(zip(columns, row)) for row in rows if any(value not in (None, "") for value in row)]


def _normalize_issuers(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    issuers: dict[str, dict[str, Any]] = {}
    current_id = "default"
    current_name = "預設發卡行"
    for row in rows:
        if not _enabled(row.get("啟用")):
            continue
        current_id = _text(row.get("發卡行代號")) or current_id
        current_name = _text(row.get("發卡行名稱")) or current_name
        issuer = issuers.setdefault(
            current_id,
            {
                "id": current_id,
                "name": current_name,
                "defaultLocale": _text(row.get("預設語言")) or DEFAULT_SUPPORTED_LOCALES[0],
                "issuerModes": [],
                "supportedLocales": [],
            },
        )
        mode = _text(row.get("Issuer Mode"))
        if mode and mode not in issuer["issuerModes"]:
            issuer["issuerModes"].append(mode)
    return issuers


def _normalize_wordings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wordings: list[dict[str, Any]] = []
    values_by_key: dict[tuple[str, ...], str] = {}
    for row in rows:
        if not _enabled(row.get("啟用匯入")):
            continue
        normalized = {
            "issuerId": _text(row.get("發卡行代號")) or "default",
            "issuerMode": _required_text(row, "Issuer Mode"),
            "deviceChannel": _required_text(row, "設備通道").upper(),
            "messageCategory": _required_text(row, "訊息類別").upper(),
            "wordingCode": _required_text(row, "編碼代號").upper(),
            "locale": _required_text(row, "語言代碼"),
            "fieldKey": _required_text(row, "欄位代號"),
            "content": _required_text(row, "話術內容"),
            "placeholders": list(dict.fromkeys(re.findall(r"\{\d+\}", _text(row.get("話術內容"))))),
        }
        option_index = _text(row.get("選項序號"))
        if option_index:
            normalized["optionIndex"] = option_index
        key = tuple(
            normalized[name]
            for name in (
                "issuerId",
                "issuerMode",
                "deviceChannel",
                "messageCategory",
                "wordingCode",
                "locale",
                "fieldKey",
            )
        ) + (option_index,)
        if key in values_by_key and values_by_key[key] == normalized["content"]:
            continue
        if key in values_by_key:
            raise ValueError(f"Duplicate wording key: {' / '.join(key)}")
        values_by_key[key] = normalized["content"]
        wordings.append(normalized)
    return wordings


def _add_wording_only_issuers(
    issuers: dict[str, dict[str, Any]],
    wordings: list[dict[str, Any]],
) -> None:
    for wording in wordings:
        issuer_id = wording["issuerId"]
        issuer = issuers.setdefault(
            issuer_id,
            {
                "id": issuer_id,
                "name": issuer_id,
                "defaultLocale": DEFAULT_SUPPORTED_LOCALES[0],
                "issuerModes": [],
                "supportedLocales": [],
            },
        )
        mode = wording["issuerMode"]
        if mode not in issuer["issuerModes"]:
            issuer["issuerModes"].append(mode)


def _apply_supported_locales(
    issuers: dict[str, dict[str, Any]],
    wordings: list[dict[str, Any]],
) -> None:
    locales_by_issuer: dict[str, set[str]] = {}
    for wording in wordings:
        locales_by_issuer.setdefault(wording["issuerId"], set()).add(wording["locale"])
    for issuer_id, issuer in issuers.items():
        if issuer_id == "default":
            issuer["supportedLocales"] = list(DEFAULT_SUPPORTED_LOCALES)
            continue
        locales = locales_by_issuer.get(issuer_id) or set(DEFAULT_SUPPORTED_LOCALES)
        issuer["supportedLocales"] = _sorted_locales(locales)


def _sorted_locales(locales: Iterable[str]) -> list[str]:
    values = set(locales)
    ordered = [locale for locale in DEFAULT_SUPPORTED_LOCALES if locale in values]
    return ordered + sorted(values.difference(ordered))


def _write_json_atomically(destination: Path, value: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)


def _required_text(row: dict[str, Any], column: str) -> str:
    value = _text(row.get(column))
    if not value:
        raise ValueError(f"Wording row is missing required value: {column}")
    return value


def _enabled(value: Any) -> bool:
    return _text(value).upper() in {"Y", "YES", "TRUE", "1"}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
