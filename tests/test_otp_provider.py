import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from acs_auto_sit.otp_provider import OtpSettings, lookup_acs_generated_otp, simulated_otp_for_acs_trans_id


class OtpLookupHandler(BaseHTTPRequestHandler):
    received_path = ""

    def do_GET(self):
        self.__class__.received_path = self.path
        response = {"otp": "654321"}
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


class EmptyOtpLookupHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        response = {"message": "not ready"}
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


class NestedOtpLookupHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        response = {
            "acsTransID": "acs-trans-nested",
            "otp": {
                "code": "HJHK-137831",
                "status": "0",
                "issueCounter": 1,
            },
        }
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


def test_lookup_acs_generated_otp_uses_external_lookup_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), OtpLookupHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        otp, metadata = lookup_acs_generated_otp(
            "acs-trans-1",
            OtpSettings(
                source_mode="acs_generated",
                lookup_url_template=f"http://127.0.0.1:{server.server_port}/otp/{{acsTrandId}}",
            ),
            timeout_seconds=5,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert OtpLookupHandler.received_path == "/otp/acs-trans-1"
    assert otp == "654321"
    assert metadata["source"] == "lookup_api"
    assert metadata["lookupUsed"] is True
    assert metadata["http"]["method"] == "GET"


def test_lookup_acs_generated_otp_falls_back_to_simulated_value_when_lookup_has_no_otp():
    server = ThreadingHTTPServer(("127.0.0.1", 0), EmptyOtpLookupHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        otp, metadata = lookup_acs_generated_otp(
            "acs-trans-2",
            OtpSettings(
                source_mode="acs_generated",
                lookup_url_template=f"http://127.0.0.1:{server.server_port}/otp/{{acsTransID}}",
            ),
            timeout_seconds=5,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert otp == simulated_otp_for_acs_trans_id("acs-trans-2")
    assert metadata["source"] == "simulated_fallback"
    assert metadata["lookupUsed"] is True
    assert metadata["error"] == "OTP lookup response does not contain a usable OTP value."


def test_lookup_acs_generated_otp_extracts_verification_code_suffix_from_nested_otp_object():
    server = ThreadingHTTPServer(("127.0.0.1", 0), NestedOtpLookupHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        otp, metadata = lookup_acs_generated_otp(
            "acs-trans-nested",
            OtpSettings(
                source_mode="acs_generated",
                lookup_url_template=f"http://127.0.0.1:{server.server_port}/otp/{{acsTrandId}}",
            ),
            timeout_seconds=5,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert otp == "137831"
    assert metadata["resolvedOtp"] == "137831"
