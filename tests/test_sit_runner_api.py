import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib import request

import acs_auto_sit.server as server_module
from acs_auto_sit.client import PostResult
from acs_auto_sit.issuer_modes import resolve_issuer_mode
from acs_auto_sit.server import create_server


def test_browser_cases_api_returns_case_list():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    try:
        with request.urlopen(
            f"http://127.0.0.1:{app_server.server_port}/api/sit/browser-cases",
            timeout=5,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        _stop_server(app_server, app_thread)

    assert result["ok"] is True
    assert result["caseCount"] == 50
    assert result["cases"][0]["id"] == "case01"
    assert result["cases"][0]["status"] == "pending"
    assert result["cases"][0]["caseImplementation"]["status"] == "partial"
    assert result["cases"][0]["caseImplementation"]["directOtp"]["status"] == "completed"
    assert result["cases"][0]["caseImplementation"]["selectionSmsOtp"]["status"] == "completed"
    assert result["cases"][0]["functionPoint"].startswith("OTP transaction successful")
    assert result["cases"][0]["expected"]["messages"]["CRes"]["transStatus"] == "Y"


def test_issuer_modes_api_returns_manual_mode_choices():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    try:
        with request.urlopen(
            f"http://127.0.0.1:{app_server.server_port}/api/sit/issuer-modes",
            timeout=5,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        _stop_server(app_server, app_thread)

    assert result["ok"] is True
    assert [item["id"] for item in result["issuerModes"]] == [
        "selection_sms_oob",
        "selection_sms_otp",
        "direct_otp",
        "direct_oob",
        "default_oob_can_switch_otp",
    ]
    assert result["defaultIssuerMode"] == "direct_otp"


def test_sit_run_api_dry_run_marks_selected_cases_without_network():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    body = json.dumps({"caseIds": ["case01", "case50"], "mode": "dryRun"}).encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/sit/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        _stop_server(app_server, app_thread)

    assert result["ok"] is True
    assert [item["caseId"] for item in result["results"]] == ["case01", "case50"]
    assert result["results"][0]["status"] == "skipped"
    assert result["results"][0]["reason"] == "Dry run only; live execution was not requested."
    assert result["results"][1]["status"] == "skipped"
    assert "manual_or_slow" in result["results"][1]["reason"]


def test_sit_run_api_live_mode_skips_unsupported_case_without_network():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    body = json.dumps(
        {
            "caseIds": ["case50"],
            "mode": "live",
            "issuerMode": "direct_oob",
            "preferredChallenge": "oob",
            "transaction": {
                "url": "http://127.0.0.1/not-used",
                "headers": {"Content-Type": "application/json"},
                "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
                "timeoutSeconds": 1,
                "simulatedOtp": "123456",
            },
        }
    ).encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/sit/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        _stop_server(app_server, app_thread)

    assert result["ok"] is True
    assert result["mode"] == "live"
    assert result["issuerMode"]["id"] == "direct_oob"
    assert result["results"][0]["caseId"] == "case50"
    assert result["results"][0]["status"] == "skipped"
    assert "manual_or_slow" in result["results"][0]["reason"]
    assert result["results"][0]["details"]["issuerMode"]["id"] == "direct_oob"


def test_live_runner_runs_case02_failure_then_success_otp_flow(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case01", "case02"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert len(calls) == 2
    assert results[0]["caseId"] == "case01"
    assert results[0]["status"] == "pass"
    assert results[1]["caseId"] == "case02"
    assert results[1]["status"] == "pass"
    assert calls[1]["otpAttempts"] == ["failure", "success"]
    assert results[1]["details"]["caseAreq"]["caseId"] == "case02"
    assert results[1]["details"]["caseAreq"]["payloadTemplate"]["messageType"] == "AReq"
    assert results[1]["details"]["caseAreq"]["actualRequestBody"]["messageType"] == "AReq"


def test_live_runner_applies_case_run_card_settings(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "N", "transStatusReason": "08"},
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case08", "case10"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0", "acctNumber": "original"},
            "timeoutSeconds": 1,
            "validCardNumber": "5678910000000000",
            "invalidCardNumber": "4000000000000002",
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["payload"]["acctNumber"] for call in calls] == ["4000000000000002", "4000000000000002"]
    assert [result["details"]["caseAreq"]["actualRequestBody"]["acctNumber"] for result in results] == [
        "4000000000000002",
        "4000000000000002",
    ]


def test_live_runner_runs_case03_retry_transaction_then_success_transaction(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        trans_status = "N" if len(calls) == 1 else "Y"
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": trans_status}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case03"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert len(calls) == 2
    assert calls[0]["otpAttempts"] == ["failure", "failure", "failure", "failure", "failure"]
    assert calls[1]["otpAttempts"] == ["success"]
    assert results[0]["caseId"] == "case03"
    assert results[0]["status"] == "pass"
    assert [item["actualStatus"] for item in results[0]["details"]["transactions"]] == ["N", "Y"]


def test_live_runner_uses_configured_otp_failure_limit_for_max_failure_case(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "N" if len(calls) == 1 else "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case03"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
            "otpFailureMaxAttempts": 5,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert calls[0]["otpAttempts"] == ["failure", "failure", "failure", "failure", "failure"]
    assert calls[1]["otpAttempts"] == ["success"]
    assert result["status"] == "pass"


def test_live_runner_failure_reason_includes_expected_and_actual(monkeypatch):
    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "N"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case01"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert result["status"] == "fail"
    assert "預期" in result["reason"]
    assert "實際" in result["reason"]
    assert "Y" in result["reason"]
    assert "N" in result["reason"]


def test_live_runner_cres_failure_reports_acs_error_reason(monkeypatch):
    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": True,
            "ares": {
                "messageType": "Erro",
                "errorCode": "403",
                "errorDescription": "Transient system failure!",
                "errorDetail": "A slowly processing back-end system!",
            },
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case01"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert result["status"] == "fail"
    assert "ACS Erro 403" in result["reason"]


def test_sit_run_summary_counts_result_statuses():
    results = [
        {"caseId": "case01", "status": "pass"},
        {"caseId": "case02", "status": "fail"},
        {"caseId": "case03", "status": "skipped"},
        {"caseId": "case04", "status": "error"},
    ]

    assert server_module._summarize_sit_results(results) == {
        "total": 4,
        "completed": 4,
        "pass": 1,
        "fail": 1,
        "skipped": 1,
        "error": 1,
    }


def test_live_runner_runs_prompt_cases_with_expected_otp_attempts(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {
                "cres": None,
                "otpSubmission": {
                    "challenge": {
                        "visibleText": [
                            "We just sent you a verification code to your mobile application or your number ******5666.",
                            "Merchant: HiTRUST EMV Demo Merchant",
                            "Amount: 1.00 TWD",
                            "Transaction time: 2026-06-29 03:48:16",
                            "Card number: ************2574",
                            "Incorrect verification code. You have 4 attempt(s) remaining.",
                        ]
                    }
                },
            },
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case04", "case05", "case06"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["otpAttempts"] for call in calls] == [["empty"], ["alpha"], ["special"]]
    assert [result["status"] for result in results] == ["pass", "pass", "pass"]
    assert all(not result["details"]["prompt"]["missing"] for result in results)


def test_prompt_text_matching_uses_all_challenge_stages_and_ignores_dynamic_values():
    run_result = {
        "autoCreq": {
            "smsSelection": {
                "challenge": {
                    "visibleText": [
                        "Purchase Authentication",
                        "Merchant: HiTRUST EMV Demo Merchant",
                        "Amount: 1.00 TWD",
                        "Card number: ************2574",
                        "Enter verification code:",
                    ],
                },
            },
            "otpSubmission": {
                "challenge": {
                    "visibleText": [
                        "Incorrect verification code. You have 4 attempt(s) remaining.",
                    ],
                },
            },
        },
    }
    expected_prompts = [
        "UI and page format display correctly",
        "Title： Purchase Authentication",
        "Merchant: HiTRUST EMV Demo Merchant",
        "Amount: 10000.00 TWD",
        "Transaction time: 2026-06-29 03:48:16",
        "Card number: ************0164",
        "Incorrect verification code. You have 4 attempt(s) remaining.",
        "Input Prompt: Enter verification code:",
    ]

    visible_text = server_module._visible_text_from_run_result(run_result)

    assert "Purchase Authentication" in visible_text
    assert "Incorrect verification code. You have 4 attempt(s) remaining." in visible_text
    assert server_module._missing_prompt_text(expected_prompts, visible_text) == []


def test_prompt_text_matching_ignores_dynamic_merchant_and_help_content():
    visible_text = [
        "交易验证",
        "验证码已通过短信发送至******7342",
        "商店: TEST ZOHO CORP PTY",
        "请输入验证码:",
        "提交",
        "重新获取验证码",
        "帮助",
        "如果你需要帮助，请联系我们的+886 916478999",
    ]
    expected_prompts = [
        "Title：交易验证",
        "商店: HiTRUST EMV Demo Merchant",
        "Input Prompt: 请输入验证码:",
        "Submit OTP button: 提交",
        "Resend OTP button: 重新获取验证码",
        "Help Title: 收不到验证码？",
        "Help Content: 如您有其他疑问，请致电我们的客服中心 093 988 983 / 089 988 983。",
    ]

    assert server_module._missing_prompt_text(expected_prompts, visible_text) == []


def test_areq_flow_retries_transient_slow_backend_error(monkeypatch):
    calls = []

    class FakeHttp:
        def __init__(self, response_json):
            self.response_json = response_json
            self.response_text = json.dumps(response_json)
            self.error = None

        def to_dict(self):
            return {
                "status_code": 200,
                "error": None,
                "request_body": {"messageType": "AReq"},
                "response_json": self.response_json,
                "response_text": self.response_text,
            }

    responses = [
        {
            "messageType": "Erro",
            "errorCode": "403",
            "errorDescription": "Transient system failure!",
            "errorDetail": "A slowly processing back-end system!",
        },
        {"messageType": "ARes", "transStatus": "Y"},
    ]

    def fake_post_payload(url, payload, headers=None, timeout_seconds=30):
        calls.append(payload)
        return FakeHttp(responses.pop(0))

    monkeypatch.setattr(server_module, "post_payload", fake_post_payload)
    monkeypatch.setattr(server_module.time, "sleep", lambda seconds: None)

    result = server_module._run_areq_flow(
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
    )

    assert len(calls) == 2
    assert result["ares"]["messageType"] == "ARes"
    assert result["httpAttempts"][0]["response_json"]["messageType"] == "Erro"


def test_areq_flow_uses_exponential_waits_for_transient_slow_backend_error(monkeypatch):
    calls = []
    sleeps = []

    class FakeHttp:
        def __init__(self, response_json):
            self.response_json = response_json
            self.response_text = json.dumps(response_json)
            self.error = None

        def to_dict(self):
            return {
                "status_code": 200,
                "error": None,
                "request_body": {"messageType": "AReq"},
                "response_json": self.response_json,
                "response_text": self.response_text,
            }

    slow_error = {
        "messageType": "Erro",
        "errorCode": "403",
        "errorDescription": "Transient system failure!",
        "errorDetail": "A slowly processing back-end system!",
    }

    def fake_post_payload(url, payload, headers=None, timeout_seconds=30):
        calls.append(payload)
        return FakeHttp(slow_error if len(calls) < 4 else {"messageType": "ARes", "transStatus": "Y"})

    monkeypatch.setattr(server_module, "post_payload", fake_post_payload)
    monkeypatch.setattr(server_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = server_module._run_areq_flow(
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
    )

    assert len(calls) == 4
    assert sleeps == [1.0, 2.0, 4.0]
    assert result["ares"]["messageType"] == "ARes"
    assert len(result["httpAttempts"]) == 4


def test_live_runner_waits_between_live_case_executions(monkeypatch):
    calls = []
    sleeps = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)
    monkeypatch.setattr(server_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    results = server_module._run_live_sit_cases(
        ["case01", "case02"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
            "caseDelaySeconds": 1.5,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert len(calls) == 2
    assert [result["status"] for result in results] == ["pass", "pass"]
    assert sleeps == [1.5]


def test_live_runner_runs_case07_success_challenge(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case07"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert calls[0]["otpAttempts"] == ["success"]
    assert result["caseId"] == "case07"
    assert result["status"] == "pass"


def test_live_runner_matches_case08_ares_only_result(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "N", "transStatusReason": "08"},
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case08"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert calls[0]["autoSubmitOtp"] is False
    assert result["caseId"] == "case08"
    assert result["status"] == "pass"
    assert result["details"]["ares"]["transStatus"] == "N"


def test_ares_only_result_reports_acs_error_reason(monkeypatch):
    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": True,
            "ares": {
                "messageType": "Erro",
                "errorCode": "303",
                "errorDescription": "Access Denied, Invalid Endpoint",
                "errorDetail": "Cardholder Account Number is not in a range belonging to CardScheme.",
            },
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case08"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert result["status"] == "fail"
    assert "ACS Erro 303" in result["reason"]
    assert "Cardholder Account Number" in result["reason"]


def test_transaction_for_case_sets_browser_language_from_case_name():
    base_transaction = {
        "payload": {
            "messageType": "AReq",
            "messageVersion": "2.2.0",
            "browserLanguage": "en-NZ",
        }
    }
    cases = server_module.browser_cases_by_id()

    chinese = server_module._transaction_for_case(cases["case24"], base_transaction)
    thai = server_module._transaction_for_case(cases["case25"], base_transaction)
    khmer = server_module._transaction_for_case(cases["case26"], base_transaction)
    english = server_module._transaction_for_case(cases["case35"], base_transaction)

    assert chinese["payload"]["browserLanguage"] == "zh-CN"
    assert thai["payload"]["browserLanguage"] == "th-TH"
    assert khmer["payload"]["browserLanguage"] == "km-KH"
    assert english["payload"]["browserLanguage"] == "en-US"


def test_live_runner_runs_case09_success_challenge(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case09"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert calls[0]["otpAttempts"] == ["success"]
    assert result["caseId"] == "case09"
    assert result["status"] == "pass"


def test_live_runner_matches_case10_to_case12_ares_only_results(monkeypatch):
    responses = [
        {"transStatus": "N", "transStatusReason": "08"},
        {"transStatus": "Y"},
        {"transStatus": "N", "transStatusReason": "08"},
    ]

    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": True,
            "ares": responses.pop(0),
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case10", "case11", "case12"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [result["caseId"] for result in results] == ["case10", "case11", "case12"]
    assert [result["status"] for result in results] == ["pass", "pass", "pass"]


def test_live_runner_runs_case14_cancel_challenge(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "N"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case14"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert calls[0]["challengeAction"] == "cancel"
    assert calls[0]["autoSubmitOtp"] is False
    assert result["caseId"] == "case14"
    assert result["status"] == "pass"


def test_live_runner_matches_error_cases_15_17_21(monkeypatch):
    responses = [
        {
            "errorCode": "303",
            "errorDescription": "Access Denied, Invalid Endpoint",
            "errorDetail": "Issuer(issuer oid) does not support for Card Scheme(C)!",
        },
        {
            "errorCode": "304",
            "errorDescription": "ISO code not valid",
            "errorDetail": "ISO code not valid - purchaseExponent!",
        },
        {
            "errorCode": "304",
            "errorComponent": "A",
            "errorDescription": "ISO code not valid",
            "errorDetail": "ISO code not valid - purchaseCurrency!",
        },
    ]

    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": True,
            "ares": responses.pop(0),
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case15", "case17", "case21"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [result["caseId"] for result in results] == ["case15", "case17", "case21"]
    assert [result["status"] for result in results] == ["pass", "pass", "pass"]
    assert [result["details"]["errorMatch"]["expected"]["code"] for result in results] == ["303", "304", "304"]


def test_live_runner_runs_currency_success_cases_16_18_to_20(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case16", "case18", "case19", "case20"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["otpAttempts"] for call in calls] == [["success"], ["success"], ["success"], ["success"]]
    assert [result["caseId"] for result in results] == ["case16", "case18", "case19", "case20"]
    assert [result["status"] for result in results] == ["pass", "pass", "pass", "pass"]


def test_live_runner_runs_localized_otp_page_prompt_cases(monkeypatch):
    case_ids = ["case24", "case25", "case26", "case28", "case29", "case30"]
    cases = server_module.browser_cases_by_id()
    visible_texts = [
        cases[case_id]["expected"]["prompts"]
        for case_id in case_ids
    ]
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {
                "smsSelection": {
                    "challenge": {
                        "visibleText": visible_texts.pop(0),
                    },
                },
            },
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        case_ids,
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["autoSubmitOtp"] for call in calls] == [False, False, False, False, False, False]
    assert [result["status"] for result in results] == ["pass"] * len(case_ids)
    assert all(not result["details"]["prompt"]["missing"] for result in results)


def test_live_runner_runs_localized_incorrect_otp_prompt_cases(monkeypatch):
    case_ids = ["case32", "case33", "case34"]
    cases = server_module.browser_cases_by_id()
    visible_texts = [
        cases[case_id]["expected"]["prompts"]
        for case_id in case_ids
    ]
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {
                "otpSubmission": {
                    "challenge": {
                        "visibleText": visible_texts.pop(0),
                    },
                },
            },
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        case_ids,
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["otpAttempts"] for call in calls] == [["failure"], ["failure"], ["failure"]]
    assert [result["status"] for result in results] == ["pass", "pass", "pass"]
    assert all(not result["details"]["prompt"]["missing"] for result in results)


def test_live_runner_runs_resend_prompt_cases(monkeypatch):
    case_ids = [
        "case35",
        "case36",
        "case37",
        "case38",
        "case39",
        "case40",
        "case41",
        "case42",
    ]
    cases = server_module.browser_cases_by_id()
    visible_texts = [cases[case_id]["expected"]["prompts"] for case_id in case_ids]
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {
                "resendSubmission": {
                    "challenge": {
                        "visibleText": visible_texts.pop(0),
                    },
                },
            },
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        case_ids,
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["challengeAction"] for call in calls] == ["resend"] * len(case_ids)
    assert [call["autoSubmitOtp"] for call in calls] == [False] * len(case_ids)
    assert [result["status"] for result in results] == ["pass"] * len(case_ids)
    assert all(not result["details"]["prompt"]["missing"] for result in results)


def test_challenge_advance_submits_resend_code_control(monkeypatch):
    forms = []

    def fake_post_form(url, form, headers=None, timeout_seconds=30, use_system_proxy=False):
        forms.append(form)
        return PostResult(
            method="POST",
            url=url,
            request_headers={},
            request_body=form,
            status_code=200,
            response_headers={},
            response_text="""
            <html><body>
              <form action="/otp" method="POST">
                <input type="hidden" name="acsTransID" value="acs-trans-1">
                <input type="text" name="challengeValue" value="">
                <button type="submit" name="resendCode" value="Y">RESEND CODE</button>
              </form>
              Verification code was resend.
            </body></html>
            """,
            response_json=None,
            elapsed_ms=1,
            error=None,
        )

    monkeypatch.setattr(server_module, "post_form", fake_post_form)
    page = server_module.parse_challenge_page(
        """
        <html><body>
          <form action="/otp" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="text" name="challengeValue" value="">
            <button type="submit" name="resendCode" value="Y">RESEND CODE</button>
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )
    response = {"otpSubmissions": []}

    server_module._advance_challenge_response(
        response,
        page,
        {"acsTransID": "acs-trans-1"},
        1,
        False,
        "123456",
        [],
        server_module.OtpSettings(
            source_mode="customer_generated",
            success_otp="123456",
            failure_otp="000000",
        ),
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("direct_otp"),
        "auto",
        "resend",
    )

    assert forms == [{"acsTransID": "acs-trans-1", "challengeValue": "", "resendCode": "Y"}]
    assert response["resendSubmission"]["action"] == "resend"
    assert "Verification code was resend." in response["resendSubmission"]["challenge"]["visibleText"]


def test_live_runner_runs_resend_limit_cases(monkeypatch):
    case_ids = ["case43", "case44", "case45", "case46"]
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {
                "resendSubmissions": [
                    {"action": "resend"},
                    {"action": "resend"},
                    {"action": "resend"},
                ],
                "resendLimitReached": True,
                "resendLimitReason": "Resend control is no longer available.",
            },
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        case_ids,
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert [call["challengeAction"] for call in calls] == ["resend_limit"] * len(case_ids)
    assert [call["resendMaxAttempts"] for call in calls] == [10] * len(case_ids)
    assert [call["autoSubmitOtp"] for call in calls] == [False] * len(case_ids)
    assert [result["status"] for result in results] == ["pass"] * len(case_ids)
    assert [result["details"]["resendLimit"]["attemptCount"] for result in results] == [3, 3, 3, 3]


def test_challenge_advance_resends_until_resend_control_disappears(monkeypatch):
    forms = []
    pages = [
        """
        <html><body>
          <form action="/otp" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="text" name="challengeValue" value="">
            <button type="submit" name="resendCode" value="Y">RESEND CODE</button>
          </form>
          Verification code was resend.
        </body></html>
        """,
        """
        <html><body>
          <form action="/otp" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="text" name="challengeValue" value="">
          </form>
          Resend limit reached.
        </body></html>
        """,
    ]

    def fake_post_form(url, form, headers=None, timeout_seconds=30, use_system_proxy=False):
        forms.append(form)
        return PostResult(
            method="POST",
            url=url,
            request_headers={},
            request_body=form,
            status_code=200,
            response_headers={},
            response_text=pages.pop(0),
            response_json=None,
            elapsed_ms=1,
            error=None,
        )

    monkeypatch.setattr(server_module, "post_form", fake_post_form)
    page = server_module.parse_challenge_page(
        """
        <html><body>
          <form action="/otp" method="POST">
            <input type="hidden" name="acsTransID" value="acs-trans-1">
            <input type="text" name="challengeValue" value="">
            <button type="submit" name="resendCode" value="Y">RESEND CODE</button>
          </form>
        </body></html>
        """,
        "https://acs.example.test/challenge",
    )
    response = {"otpSubmissions": []}

    server_module._advance_challenge_response(
        response,
        page,
        {"acsTransID": "acs-trans-1"},
        1,
        False,
        "123456",
        [],
        server_module.OtpSettings(
            source_mode="customer_generated",
            success_otp="123456",
            failure_otp="000000",
        ),
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("direct_otp"),
        "auto",
        "resend_limit",
    )

    assert forms == [
        {"acsTransID": "acs-trans-1", "challengeValue": "", "resendCode": "Y"},
        {"acsTransID": "acs-trans-1", "challengeValue": "", "resendCode": "Y"},
    ]
    assert len(response["resendSubmissions"]) == 2
    assert response["resendLimitReached"] is True
    assert response["resendLimitReason"] == "Resend control is no longer available."


def test_live_runner_skips_unsupported_cases_even_when_action_plan_exists(monkeypatch):
    calls = []

    def fake_run_areq_flow(envelope, notification_url):
        calls.append(envelope)
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    results = server_module._run_live_sit_cases(
        ["case01", "case13"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )

    assert len(calls) == 1
    assert results[0]["caseId"] == "case01"
    assert results[0]["status"] == "pass"
    assert results[1]["caseId"] == "case13"
    assert results[1]["status"] == "skipped"
    assert "CRes transStatus=Y" in results[1]["reason"]
    assert results[1]["details"]["caseAreq"]["caseId"] == "case13"
    assert results[1]["details"]["caseAreq"]["payloadTemplate"]["messageType"] == "AReq"
    assert results[1]["details"]["caseAreq"]["actualRequestBody"] is None


def test_case_areq_record_is_shared_across_issuer_modes(monkeypatch):
    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": True,
            "ares": {"transStatus": "C"},
            "autoCreq": {"cres": {"transStatus": "Y"}},
            "http": {
                "request_body": {
                    **envelope["payload"],
                    "threeDSServerTransID": "fresh-server-trans-id",
                    "dsTransID": "fresh-ds-trans-id",
                }
            },
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)
    transaction = {
        "url": "http://127.0.0.1/not-used",
        "headers": {"Content-Type": "application/json"},
        "payload": {"messageType": "AReq", "messageVersion": "2.2.0", "acctNumber": "5678910000000000"},
        "timeoutSeconds": 1,
    }

    direct_result = server_module._run_live_sit_cases(
        ["case02"],
        transaction,
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("direct_otp"),
        "auto",
    )[0]
    selection_result = server_module._run_live_sit_cases(
        ["case02"],
        transaction,
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert direct_result["details"]["caseAreq"]["payloadTemplate"] == selection_result["details"]["caseAreq"]["payloadTemplate"]


def test_prompt_case_reports_acs_error_without_runner_exception(monkeypatch):
    def fake_run_areq_flow(envelope, notification_url):
        return {
            "ok": False,
            "ares": {
                "messageType": "Erro",
                "errorCode": "403",
                "errorDescription": "Transient system failure!",
                "errorDetail": "A slowly processing back-end system!",
            },
            "autoCreq": None,
            "http": {"request_body": envelope["payload"]},
        }

    monkeypatch.setattr(server_module, "_run_areq_flow", fake_run_areq_flow)

    result = server_module._run_live_sit_cases(
        ["case04"],
        {
            "url": "http://127.0.0.1/not-used",
            "headers": {"Content-Type": "application/json"},
            "payload": {"messageType": "AReq", "messageVersion": "2.2.0"},
            "timeoutSeconds": 1,
        },
        "http://127.0.0.1/api/notification",
        resolve_issuer_mode("selection_sms_otp"),
        "auto",
    )[0]

    assert result["status"] == "fail"
    assert "ACS Erro 403" in result["reason"]
    assert "slowly processing" in result["reason"]
    assert result["details"]["ares"]["messageType"] == "Erro"


def _stop_server(app_server: ThreadingHTTPServer, app_thread: Thread) -> None:
    app_server.shutdown()
    app_thread.join(timeout=5)
    app_server.server_close()
