from io import BytesIO
import json

import pytest
from openpyxl import Workbook

from acs_auto_sit.sit_runner import load_browser_case_catalog
from acs_auto_sit.wording_profiles import (
    DEFAULT_SUPPORTED_LOCALES,
    build_localized_wording_cases,
    import_wording_workbook,
    load_wording_profiles,
)


ISSUER_HEADERS = (
    "啟用",
    "發卡行代號",
    "發卡行名稱",
    "Issuer Mode",
    "預設語言",
    "OTP 來源",
    "成功 OTP",
    "失敗 OTP",
    "備註",
)
WORDING_HEADERS = (
    "啟用匯入",
    "發卡行代號",
    "發卡行名稱",
    "Issuer Mode",
    "設備通道",
    "訊息類別",
    "來源頁籤",
    "編碼代號",
    "語言代碼",
    "欄位代號",
    "欄位名稱",
    "選項序號",
    "話術內容",
    "Placeholder",
    "完成狀態",
    "備註",
)


def _workbook_bytes(wording_rows=(), *, include_wording_sheet=True):
    workbook = Workbook()
    issuer_sheet = workbook.active
    issuer_sheet.title = "發卡行設定"
    issuer_sheet.append(ISSUER_HEADERS)
    issuer_sheet.append(
        ("Y", "default", "預設發卡行", "direct_otp", "zh_TW", "客戶產客戶驗", "123456", "000000", "")
    )
    issuer_sheet.append(("Y", None, None, "selection_sms_otp", "zh_TW", "我們產我們驗", None, None, ""))

    if include_wording_sheet:
        wording_sheet = workbook.create_sheet("話術匯入")
        wording_sheet.append(WORDING_HEADERS)
        for row in wording_rows:
            wording_sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _wording_row(locale, field_key, content, *, issuer_id=None):
    return (
        "Y",
        issuer_id,
        None,
        "direct_otp",
        "BROWSER",
        "PA",
        "SMS",
        "SEND_SMS_OTP",
        locale,
        field_key,
        field_key,
        None,
        content,
        None,
        "Pass",
        None,
    )


def test_import_normalizes_and_persists_workbook(tmp_path):
    destination = tmp_path / "wording_profiles.json"
    content = _workbook_bytes(
        (
            _wording_row("zh_TW", "challenge_title", "交易驗證"),
            _wording_row("en_US", "challenge_title", "Transaction Verification"),
            _wording_row("zh_CN", "challenge_title", "交易验证"),
        )
    )

    imported = import_wording_workbook(content, destination, source_file="issuer-wording.xlsx")

    assert destination.is_file()
    assert imported["defaultSupportedLocales"] == list(DEFAULT_SUPPORTED_LOCALES)
    assert imported["issuers"]["default"]["issuerModes"] == ["direct_otp", "selection_sms_otp"]
    assert imported["issuers"]["default"]["supportedLocales"] == list(DEFAULT_SUPPORTED_LOCALES)
    assert imported["wordings"][0] == {
        "issuerId": "default",
        "issuerMode": "direct_otp",
        "deviceChannel": "BROWSER",
        "messageCategory": "PA",
        "wordingCode": "SEND_SMS_OTP",
        "locale": "zh_TW",
        "fieldKey": "challenge_title",
        "content": "交易驗證",
        "placeholders": [],
    }
    assert imported["summary"] == {
        "issuerCount": 1,
        "localeCount": 3,
        "wordingCount": 3,
    }
    assert load_wording_profiles(destination) == json.loads(destination.read_text(encoding="utf-8"))


def test_import_rejects_missing_required_sheet(tmp_path):
    with pytest.raises(ValueError, match="話術匯入"):
        import_wording_workbook(
            _workbook_bytes(include_wording_sheet=False),
            tmp_path / "wording_profiles.json",
        )


def test_import_rejects_duplicate_wording_key_without_replacing_valid_file(tmp_path):
    destination = tmp_path / "wording_profiles.json"
    destination.write_text('{"version": 0}', encoding="utf-8")
    duplicate = _wording_row("en_US", "challenge_title", "Transaction Verification")
    conflict = _wording_row("en_US", "challenge_title", "Different title")

    with pytest.raises(ValueError, match="Duplicate wording key"):
        import_wording_workbook(
            _workbook_bytes((duplicate, conflict)),
            destination,
        )

    assert json.loads(destination.read_text(encoding="utf-8")) == {"version": 0}


def _normalized_profiles(*, omit_code=None):
    scenarios = (
        ("PA", "SEND_SMS_OTP"),
        ("NPA", "SEND_SMS_OTP"),
        ("PA", "INCORRECT_SMS_OTP"),
        ("PA", "RESEND_SMS_OTP"),
        ("PA", "RESEND_SMS_GAP_LIMIT"),
        ("PA", "RESEND_SMS_LIMIT_EXCEED"),
        ("PA", "SMS_PASSCODE_EXPIRED"),
    )
    wordings = []
    for category, code in scenarios:
        if code == omit_code:
            continue
        for locale in DEFAULT_SUPPORTED_LOCALES:
            for field_key, content in (
                ("challenge_title", f"{code} {locale}"),
                ("challenge_message", f"{code} message {locale}"),
            ):
                wordings.append(
                    {
                        "issuerId": "default",
                        "issuerMode": "direct_otp",
                        "deviceChannel": "BROWSER",
                        "messageCategory": category,
                        "wordingCode": code,
                        "locale": locale,
                        "fieldKey": field_key,
                        "content": content,
                        "placeholders": [],
                    }
                )
    return {
        "defaultSupportedLocales": list(DEFAULT_SUPPORTED_LOCALES),
        "issuers": {
            "default": {
                "id": "default",
                "name": "Default Issuer",
                "defaultLocale": "zh_TW",
                "issuerModes": ["direct_otp"],
                "supportedLocales": list(DEFAULT_SUPPORTED_LOCALES),
            }
        },
        "wordings": wordings,
    }


def _source_templates():
    return [
        {
            "id": case_id,
            "functionPoint": f"Legacy {case_id}",
            "steps": ["Open challenge"],
            "expected": {"prompts": ["legacy"]},
            "automation": {"status": "automatable", "tags": ["otp", "pa"]},
        }
        for case_id in ("case23", "case27", "case31", "case35", "case39", "case43", "case47")
    ]


def test_build_localized_cases_expands_seven_scenarios_for_default_locales():
    cases = build_localized_wording_cases(_normalized_profiles(), _source_templates())

    assert len(cases) == 21
    assert [case["id"] for case in cases[:3]] == ["case23_zh_TW", "case23_en_US", "case23_zh_CN"]
    assert cases[0]["baseCaseId"] == "case23"
    assert cases[0]["locale"] == "zh_TW"
    assert cases[0]["browserLanguage"] == "zh-TW"
    assert cases[0]["wording"]["code"] == "SEND_SMS_OTP"
    assert cases[0]["expected"]["uiFields"] == {
        "challenge_title": "SEND_SMS_OTP zh_TW",
        "challenge_message": "SEND_SMS_OTP message zh_TW",
    }
    assert cases[0]["expected"]["prompts"] == [
        "SEND_SMS_OTP zh_TW",
        "SEND_SMS_OTP message zh_TW",
    ]
    assert cases[0]["availability"] == {"enabled": True, "reason": ""}


def test_build_localized_cases_disables_missing_wording_scenario():
    cases = build_localized_wording_cases(
        _normalized_profiles(omit_code="RESEND_SMS_LIMIT_EXCEED"),
        _source_templates(),
    )

    missing = [case for case in cases if case["baseCaseId"] == "case43"]
    assert len(missing) == 3
    assert all(case["availability"]["enabled"] is False for case in missing)
    assert all("RESEND_SMS_LIMIT_EXCEED" in case["availability"]["reason"] for case in missing)


def test_build_localized_cases_prefers_issuer_wording_over_shared_default():
    profiles = _normalized_profiles()
    profiles["issuers"]["bank_a"] = {
        "id": "bank_a",
        "name": "Bank A",
        "defaultLocale": "zh_TW",
        "issuerModes": ["direct_otp"],
        "supportedLocales": list(DEFAULT_SUPPORTED_LOCALES),
    }
    profiles["wordings"].append(
        {
            "issuerId": "bank_a",
            "issuerMode": "direct_otp",
            "deviceChannel": "BROWSER",
            "messageCategory": "PA",
            "wordingCode": "SEND_SMS_OTP",
            "locale": "zh_TW",
            "fieldKey": "challenge_title",
            "content": "Bank A 交易驗證",
            "placeholders": [],
        }
    )

    cases = build_localized_wording_cases(profiles, _source_templates(), issuer_id="bank_a")
    cases_by_id = {case["id"]: case for case in cases}

    assert cases_by_id["case23_zh_TW"]["expected"]["prompts"][0] == "Bank A 交易驗證"
    assert cases_by_id["case23_en_US"]["expected"]["prompts"][0] == "SEND_SMS_OTP en_US"


def test_build_localized_cases_disables_incomplete_required_fields():
    profiles = _normalized_profiles()
    profiles["wordings"] = [
        wording
        for wording in profiles["wordings"]
        if not (
            wording["messageCategory"] == "PA"
            and wording["wordingCode"] == "SEND_SMS_OTP"
            and wording["locale"] == "zh_TW"
            and wording["fieldKey"] == "challenge_message"
        )
    ]

    cases = build_localized_wording_cases(profiles, _source_templates())
    case = next(case for case in cases if case["id"] == "case23_zh_TW")

    assert case["availability"]["enabled"] is False
    assert "challenge_message" in case["availability"]["reason"]


def test_browser_catalog_replaces_legacy_localized_cases_when_profile_exists(tmp_path):
    profile_path = tmp_path / "wording_profiles.json"
    profile_path.write_text(json.dumps(_normalized_profiles()), encoding="utf-8")

    catalog = load_browser_case_catalog(
        progress_path=tmp_path / "missing-progress.json",
        wording_profiles_path=profile_path,
        issuer_id="default",
        issuer_mode="direct_otp",
    )
    case_ids = [case["id"] for case in catalog["cases"]]

    assert "case20" in case_ids
    assert "case23" not in case_ids
    assert "case23_zh_TW" in case_ids
    assert "case47_zh_CN" in case_ids
    assert len([case_id for case_id in case_ids if "_zh_" in case_id or case_id.endswith("_en_US")]) == 21
    assert catalog["wordingProfile"] == {
        "enabled": True,
        "issuerId": "default",
        "issuerMode": "direct_otp",
        "supportedLocales": list(DEFAULT_SUPPORTED_LOCALES),
    }
