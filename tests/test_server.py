import json
import socket
import base64
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs
from urllib import request

import pytest

import acs_auto_sit.server as server_module
from acs_auto_sit.server import _authentication_mode_value, create_server


class ChallengeAcsHandler(BaseHTTPRequestHandler):
    received_areq = {}
    received_creq = {}
    received_sms = {}
    received_otp = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        if self.path == "/creq":
            body = parse_qs(raw_body)
            self.__class__.received_creq = body
            creq = _decode_b64url_json(body["creq"][0])
            html = f"""
            <html><head><title>Authentication mode</title></head>
            <body>
              <form id="acs_challenge" action="http://127.0.0.1:{self.server.server_port}/process" method="POST">
                <input type="hidden" id="acsTransID" name="acsTransID" value="{creq["acsTransID"]}">
                <input type="radio" name="challengeValue" id="challengeValue1" value="1">
                <label for="challengeValue1">Send OTP via SMS</label>
              </form>
            </body></html>
            """
            self._send_html(html)
            return

        if self.path == "/process":
            body = parse_qs(raw_body)
            self.__class__.received_sms = body
            html = f"""
            <html><head><title>Transaction Verification</title></head>
            <body>
              <form id="acs_challenge" action="http://127.0.0.1:{self.server.server_port}/otp" method="POST">
                <input type="hidden" id="acsTransID" name="acsTransID" value="{body["acsTransID"][0]}">
                <input type="text" id="challengeValue" name="challengeValue" autocomplete="off">
              </form>
            </body></html>
            """
            self._send_html(html)
            return

        if self.path == "/otp":
            body = parse_qs(raw_body)
            self.__class__.received_otp = body
            response = {
                "messageType": "CRes",
                "messageVersion": "2.2.0",
                "acsTransID": body["acsTransID"][0],
                "transStatus": "Y",
            }
            encoded_cres = _b64url_json(response)
            self._send_html(
                f"""
                <html><body>
                  <form id="notification" action="{body.get("P_notificationURL", [""])[0]}" method="POST">
                    <input type="hidden" name="cres" value="{encoded_cres}">
                    <input type="hidden" name="threeDSSessionData" value="">
                  </form>
                </body></html>
                """
            )
            return

        body = json.loads(raw_body)
        self.__class__.received_areq = body
        response = {
            "messageType": "ARes",
            "messageVersion": "2.2.0",
            "transStatus": "C",
            "threeDSServerTransID": body["threeDSServerTransID"],
            "acsTransID": "acs-trans-1",
            "acsURL": f"http://127.0.0.1:{self.server.server_port}/creq",
        }
        self._send_json(response)

    def _send_html(self, value):
        encoded = value.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=UTF-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, response):
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


class MultiOtpChallengeAcsHandler(BaseHTTPRequestHandler):
    received_otps = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        if self.path == "/creq":
            body = parse_qs(raw_body)
            creq = _decode_b64url_json(body["creq"][0])
            self._send_html(
                f"""
                <html><body>
                  <form action="http://127.0.0.1:{self.server.server_port}/otp" method="POST">
                    <input type="hidden" name="acsTransID" value="{creq["acsTransID"]}">
                    <input type="text" name="challengeValue">
                  </form>
                </body></html>
                """
            )
            return

        if self.path == "/otp":
            body = parse_qs(raw_body)
            otp = body["challengeValue"][0]
            self.__class__.received_otps.append(otp)
            if otp != "123456":
                self._send_html(
                    f"""
                    <html><body>
                      <form action="http://127.0.0.1:{self.server.server_port}/otp" method="POST">
                        <input type="hidden" name="acsTransID" value="{body["acsTransID"][0]}">
                        <input type="text" name="challengeValue">
                        <p>Incorrect verification code.</p>
                      </form>
                    </body></html>
                    """
                )
                return

            response = {
                "messageType": "CRes",
                "messageVersion": "2.2.0",
                "acsTransID": body["acsTransID"][0],
                "transStatus": "Y",
            }
            self._send_html(
                f"""
                <html><body>
                  <form method="POST">
                    <input type="hidden" name="cres" value="{_b64url_json(response)}">
                  </form>
                </body></html>
                """
            )
            return

        body = json.loads(raw_body)
        response = {
            "messageType": "ARes",
            "messageVersion": "2.2.0",
            "transStatus": "C",
            "threeDSServerTransID": body["threeDSServerTransID"],
            "acsTransID": "acs-trans-2",
            "acsURL": f"http://127.0.0.1:{self.server.server_port}/creq",
        }
        self._send_json(response)

    def _send_html(self, value):
        encoded = value.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=UTF-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, response):
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


def test_areq_api_posts_to_acs_and_returns_creq_draft():
    acs_server = ThreadingHTTPServer(("127.0.0.1", 0), ChallengeAcsHandler)
    acs_thread = Thread(target=acs_server.serve_forever, daemon=True)
    acs_thread.start()

    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    payload = {
        "url": f"http://127.0.0.1:{acs_server.server_port}/areq",
        "headers": {"Content-Type": "application/json"},
        "autoSelectSms": True,
        "autoSubmitOtp": True,
        "simulatedOtp": "123456",
        "payload": {
            "messageType": "AReq",
            "messageVersion": "2.2.0",
            "threeDSServerTransID": "server-trans-1",
            "dsTransID": "ds-trans-1",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/areq",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        app_server.shutdown()
        acs_server.shutdown()
        app_thread.join(timeout=5)
        acs_thread.join(timeout=5)
        app_server.server_close()
        acs_server.server_close()

    assert ChallengeAcsHandler.received_areq["messageType"] == "AReq"
    assert ChallengeAcsHandler.received_areq["threeDSServerTransID"] != "server-trans-1"
    assert ChallengeAcsHandler.received_areq["dsTransID"] != "ds-trans-1"
    assert ChallengeAcsHandler.received_areq["notificationURL"].startswith(
        f"http://127.0.0.1:{app_server.server_port}/api/notification"
    )
    assert result["ares"]["transStatus"] == "C"
    assert result["ok"] is True
    assert result["creqDraft"]["messageType"] == "CReq"
    assert result["creqDraft"]["acsTransID"] == "acs-trans-1"
    assert _decode_b64url_json(ChallengeAcsHandler.received_creq["creq"][0])["messageType"] == "CReq"
    assert ChallengeAcsHandler.received_sms["challengeValue"] == ["1"]
    assert ChallengeAcsHandler.received_otp["challengeValue"] == ["123456"]
    assert result["autoCreq"]["challenge"]["type"] == "authentication_mode"
    assert result["autoCreq"]["smsSelection"]["selectedValue"] == "1"
    assert result["autoCreq"]["otpSubmission"]["simulatedOtpUsed"] is True
    assert result["autoCreq"]["cres"]["transStatus"] == "Y"
    assert result["autoCreq"]["otpSubmission"]["notification"]["ok"] is True
    assert (
        result["autoCreq"]["otpSubmission"]["notification"]["notification"]["cres"]["transStatus"]
        == "Y"
    )


def test_areq_api_can_submit_failure_otp_then_success_otp():
    MultiOtpChallengeAcsHandler.received_otps = []
    acs_server = ThreadingHTTPServer(("127.0.0.1", 0), MultiOtpChallengeAcsHandler)
    acs_thread = Thread(target=acs_server.serve_forever, daemon=True)
    acs_thread.start()

    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    payload = {
        "url": f"http://127.0.0.1:{acs_server.server_port}/areq",
        "headers": {"Content-Type": "application/json"},
        "autoSubmitOtp": True,
        "otpAttempts": ["failure", "success"],
        "successOtp": "123456",
        "failureOtp": "000000",
        "payload": {
            "messageType": "AReq",
            "messageVersion": "2.2.0",
            "threeDSServerTransID": "server-trans-1",
            "dsTransID": "ds-trans-1",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/areq",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        app_server.shutdown()
        acs_server.shutdown()
        app_thread.join(timeout=5)
        acs_thread.join(timeout=5)
        app_server.server_close()
        acs_server.server_close()

    assert MultiOtpChallengeAcsHandler.received_otps == ["000000", "123456"]
    assert [item["otpPurpose"] for item in result["autoCreq"]["otpSubmissions"]] == [
        "failure",
        "success",
    ]
    assert result["autoCreq"]["cres"]["transStatus"] == "Y"


def test_selection_sms_otp_mode_always_selects_sms_challenge_value():
    page = {
        "radioOptions": [
            {"name": "challengeValue", "value": "1", "label": "SMS"},
            {"name": "challengeValue", "value": "3", "label": "OOB"},
        ]
    }

    selected = _authentication_mode_value(
        page,
        {"id": "selection_sms_otp"},
        "oob",
    )

    assert selected == "1"


@pytest.mark.parametrize(
    ("preferred_challenge", "expected_value"),
    (("sms", "sms-x"), ("email", "email-x"), ("oob", "oob-x")),
)
def test_authentication_mode_selection_uses_option_labels(preferred_challenge, expected_value):
    page = {
        "radioOptions": [
            {"name": "challengeValue", "value": "oob-x", "label": "Mobile App approval"},
            {"name": "challengeValue", "value": "email-x", "label": "Email OTP"},
            {"name": "challengeValue", "value": "sms-x", "label": "SMS OTP"},
        ]
    }

    selected = _authentication_mode_value(
        page,
        {"id": "selection_sms_email_oob", "defaultPreferredChallenge": "sms"},
        preferred_challenge,
    )

    assert selected == expected_value


def test_visible_text_includes_page_returned_after_oob_switch():
    visible_text = server_module._visible_text_from_run_result(
        {
            "autoCreq": {
                "challenge": {"visibleText": ["Approve in app"]},
                "oobSubmission": {"challenge": {"visibleText": ["Enter SMS OTP"]}},
            }
        }
    )

    assert visible_text == ["Approve in app", "Enter SMS OTP"]


def test_notification_api_decodes_form_encoded_cres():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    cres = {
        "messageType": "CRes",
        "messageVersion": "2.2.0",
        "threeDSServerTransID": "server-trans-1",
        "acsTransID": "acs-trans-1",
        "challengeCompletionInd": "Y",
        "transStatus": "Y",
    }
    body = f"cres={_b64url_json(cres)}&threeDSSessionData=".encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/notification",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        app_server.shutdown()
        app_thread.join(timeout=5)
        app_server.server_close()

    assert result["ok"] is True
    assert result["notification"]["form"]["threeDSSessionData"] == ""
    assert result["notification"]["cres"]["transStatus"] == "Y"


def test_simulated_transaction_result_api_returns_cavv_by_acs_trans_id():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    body = json.dumps({"acsTransID": "acs-trans-1"}).encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/transaction-result/simulated",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        app_server.shutdown()
        app_thread.join(timeout=5)
        app_server.server_close()

    assert result["ok"] is True
    assert result["acsTransID"] == "acs-trans-1"
    assert result["transaction"]["transStatus"] == "Y"
    assert result["transaction"]["eci"] == "02"
    assert result["transaction"]["cavv"]
    assert result["checks"]["cavv"]["status"] == "pass"


def test_areq_api_marks_transport_error_as_not_ok():
    app_server = create_server("127.0.0.1", 0)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()

    closed_port = _find_closed_port()
    payload = {
        "url": f"http://127.0.0.1:{closed_port}/areq",
        "headers": {"Content-Type": "application/json"},
        "timeoutSeconds": 1,
        "payload": {
            "messageType": "AReq",
            "messageVersion": "2.2.0",
            "threeDSServerTransID": "server-trans-1",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/areq",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    finally:
        app_server.shutdown()
        app_thread.join(timeout=5)
        app_server.server_close()

    assert result["ok"] is False
    assert result["error"]
    assert result["ares"] is None


def test_wording_profile_import_and_issuer_case_catalog_api(tmp_path):
    destination = tmp_path / "wording_profiles.json"
    workbook_path = Path("outputs/challenge-ui-wording-work/acs_challenge_ui_wording_import.xlsx")
    body = json.dumps(
        {
            "fileName": workbook_path.name,
            "contentBase64": base64.b64encode(workbook_path.read_bytes()).decode("ascii"),
        }
    ).encode("utf-8")

    app_server = create_server("127.0.0.1", 0, wording_profiles_path=destination)
    app_thread = Thread(target=app_server.serve_forever, daemon=True)
    app_thread.start()
    import_request = request.Request(
        f"http://127.0.0.1:{app_server.server_port}/api/sit/wording-profiles/import",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(import_request, timeout=15) as response:
            imported = json.loads(response.read().decode("utf-8"))
        with request.urlopen(
            f"http://127.0.0.1:{app_server.server_port}/api/sit/wording-profiles",
            timeout=5,
        ) as response:
            profiles = json.loads(response.read().decode("utf-8"))
        with request.urlopen(
            f"http://127.0.0.1:{app_server.server_port}/api/sit/browser-cases?issuerId=default&issuerMode=direct_otp",
            timeout=5,
        ) as response:
            catalog = json.loads(response.read().decode("utf-8"))
    finally:
        app_server.shutdown()
        app_thread.join(timeout=5)
        app_server.server_close()

    assert destination.is_file()
    assert imported["ok"] is True
    assert imported["summary"]["issuerCount"] == 1
    assert profiles["imported"] is True
    assert profiles["defaultSupportedLocales"] == ["zh_TW", "en_US", "zh_CN"]
    assert profiles["issuers"][0]["id"] == "default"
    assert catalog["wordingProfile"]["enabled"] is True
    assert catalog["wordingProfile"]["supportedLocales"] == ["zh_TW", "en_US", "zh_CN"]
    assert "case23_zh_TW" in {case["id"] for case in catalog["cases"]}


def _find_closed_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _b64url_json(value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_b64url_json(value):
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
