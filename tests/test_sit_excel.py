from pathlib import Path

import openpyxl

from acs_auto_sit.sit_excel import load_browser_cases


def test_load_browser_cases_extracts_core_expected_results(tmp_path):
    workbook_path = tmp_path / "sit.xlsx"
    _write_workbook(
        workbook_path,
        [
            [
                "case01",
                "OTP transaction successful\nAuthorization check CAVV value - Correct",
                "1. Open the website\n2. Enter the correct verification code\n3. Click <SUBMIT>",
                '1. ACS 2.2 return CRes message\n'
                '   1.1 transStatus = "Y"\n'
                '2. ACS 2.2 return RReq message\n'
                '   2.1 transStatus = "Y"\n'
                '   2.2 ECI ="05"\n'
                "   2.3 CAVV is not null",
            ],
            [
                "case08",
                "Invalid card - PA",
                "1. Open the website\n2. Click <Pay Now>",
                'ACS 2.2 return ARes message\n'
                '1. transStatus = "N"\n'
                '2. transStatusReason = "08"\n'
                "3. ECI is null\n"
                "4. CAVV is null",
            ],
        ],
    )

    cases = load_browser_cases(workbook_path)

    assert [case["id"] for case in cases] == ["case01", "case08"]
    assert cases[0]["channel"] == "browser"
    assert cases[0]["steps"] == [
        "Open the website",
        "Enter the correct verification code",
        "Click <SUBMIT>",
    ]
    assert cases[0]["expected"]["messages"]["CRes"]["transStatus"] == "Y"
    assert cases[0]["expected"]["messages"]["RReq"]["transStatus"] == "Y"
    assert cases[0]["expected"]["messages"]["RReq"]["eci"] == "05"
    assert cases[0]["expected"]["messages"]["RReq"]["cavv"] == "not_null"
    assert "otp" in cases[0]["automation"]["tags"]
    assert cases[1]["expected"]["messages"]["ARes"]["transStatus"] == "N"
    assert cases[1]["expected"]["messages"]["ARes"]["transStatusReason"] == "08"
    assert cases[1]["expected"]["messages"]["ARes"]["eci"] == "null"
    assert cases[1]["expected"]["messages"]["ARes"]["cavv"] == "null"


def test_load_browser_cases_extracts_multi_transaction_expectations(tmp_path):
    workbook_path = tmp_path / "sit.xlsx"
    _write_workbook(
        workbook_path,
        [
            [
                "case03",
                "Verification code error - Exceeded maximum number of errors - initiate transaction again",
                "First transaction:\n1. Enter the wrong verification code\n\nSecond transaction:\n1. Enter the correct verification code",
                'First transaction:\n'
                '1. ACS 2.2 return CRes message\n'
                '   1.1 transStatus = "N"\n'
                '2. ACS 2.2 return RReq message\n'
                '   2.1 transStatus = "N"\n'
                '   2.2 transStatusReason = "19"\n'
                "   2.3 ECI is null\n"
                "   2.4 CAVV is null\n\n"
                "Second transaction:\n"
                "1. ACS 2.2 return CRes message\n"
                '   1.1 transStatus = "Y"\n'
                "2. ACS 2.2 return RReq message\n"
                '   2.1 transStatus = "Y"\n'
                '   2.2 ECI ="05"\n'
                "   2.3 CAVV is not null",
            ],
        ],
    )

    case = load_browser_cases(workbook_path)[0]

    transactions = case["expected"]["transactions"]
    assert [item["label"] for item in transactions] == ["First transaction", "Second transaction"]
    assert transactions[0]["messages"]["CRes"]["transStatus"] == "N"
    assert transactions[0]["messages"]["RReq"]["transStatusReason"] == "19"
    assert transactions[0]["messages"]["RReq"]["eci"] == "null"
    assert transactions[1]["messages"]["CRes"]["transStatus"] == "Y"
    assert transactions[1]["messages"]["RReq"]["eci"] == "05"
    assert "retry" in case["automation"]["tags"]


def _write_workbook(path: Path, rows: list[list[str]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Browser"
    sheet.append(
        [
            "ID",
            "System",
            "Module",
            "Function Point",
            "Test Points",
            "Steps",
            "Expected Results",
            "Actual Result",
            "Test Date",
            "Testers",
            "Remarks",
        ]
    )
    for case_id, function_point, steps, expected in rows:
        sheet.append(
            [
                case_id,
                "ACS 2.2",
                "Browser Transaction Verification Process",
                function_point,
                "CUP",
                steps,
                expected,
                "Pass",
                "2026-06-29",
                "Sasha",
                "",
            ]
        )
    workbook.save(path)
