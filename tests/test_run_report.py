from acs_auto_sit.run_report import html_report_filename, render_html_report


def _valid_run():
    return {
        "schemaVersion": 1,
        "runId": "run-1",
        "startedAt": "2026-07-20T00:15:30+08:00",
        "finishedAt": "2026-07-20T00:16:00+08:00",
        "execution": {
            "cardScheme": "V",
            "issuerOid": "issuer-1",
            "issuerMode": "sms_otp",
            "effectivePreferredChallenge": "sms",
            "wordingLocale": "zh_TW",
            "selectedCaseIds": ["case01"],
        },
        "summary": {
            "total": 1,
            "completed": 1,
            "pass": 0,
            "fail": 1,
            "skipped": 0,
            "error": 0,
        },
        "results": [
            {
                "caseId": "case01",
                "status": "fail",
                "reason": "<script>alert(1)</script>",
                "areqSentAt": "2026-07-20T00:15:30.214+08:00",
                "durationMs": 2400,
                "acsTransID": "acs-1",
                "transactionResult": {
                    "lookupStatus": "succeeded",
                    "transStatus": "N",
                    "eci": "",
                    "cavvPresent": False,
                    "validationStatus": "fail",
                    "raw": {},
                },
                "details": {"returnedHtml": "<b>unsafe evidence</b>"},
            }
        ],
    }


def test_render_html_report_is_self_contained_and_escaped():
    report = render_html_report(_valid_run()).decode("utf-8")

    assert "<!doctype html>" in report.lower()
    assert "Issuer OID" in report and "issuer-1" in report
    assert "acs-1" in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "<script>alert(1)</script>" not in report
    assert "https://" not in report
    assert "<script" not in report.lower()
    assert "<details>" in report


def test_single_case_report_filename_is_deterministic():
    assert html_report_filename(_valid_run()) == (
        "sit-report-V-case01-20260720-001530.html"
    )


def test_multi_case_filename_and_unicode_are_stable():
    run = _valid_run()
    run["execution"]["selectedCaseIds"] = ["case01", "case02"]
    run["results"][0]["reason"] = "驗證失敗"

    assert html_report_filename(run) == (
        "sit-report-V-2-cases-20260720-001530.html"
    )
    assert "驗證失敗" in render_html_report(run).decode("utf-8")


def test_report_filename_sanitizes_card_scheme():
    run = _valid_run()
    run["execution"]["cardScheme"] = "V / unsafe"

    assert html_report_filename(run).startswith("sit-report-V-unsafe-case01-")

