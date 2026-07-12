import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib import request

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


def _stop_server(app_server: ThreadingHTTPServer, app_thread: Thread) -> None:
    app_server.shutdown()
    app_thread.join(timeout=5)
    app_server.server_close()
