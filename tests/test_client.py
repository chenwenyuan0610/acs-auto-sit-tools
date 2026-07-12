import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from acs_auto_sit.client import post_payload


class RecordingAcsHandler(BaseHTTPRequestHandler):
    received_method = ""
    received_body = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        self.__class__.received_method = "POST"
        self.__class__.received_body = json.loads(raw_body)

        response = {
            "messageType": "ARes",
            "transStatus": "C",
            "acsTransID": "acs-trans-1",
        }
        encoded = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


def test_post_payload_sends_json_post_and_parses_json_response():
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingAcsHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/areq"

    try:
        result = post_payload(
            url,
            {"messageType": "AReq"},
            headers={"Content-Type": "application/json"},
            timeout_seconds=5,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert RecordingAcsHandler.received_method == "POST"
    assert RecordingAcsHandler.received_body == {"messageType": "AReq"}
    assert result.status_code == 200
    assert result.response_json["transStatus"] == "C"


def test_post_payload_bypasses_system_proxy_by_default(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingAcsHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    closed_port = _find_closed_port()
    url = f"http://127.0.0.1:{server.server_port}/areq"

    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")

    try:
        result = post_payload(url, {"messageType": "AReq"}, timeout_seconds=5)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert result.status_code == 200
    assert result.error is None


def _find_closed_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
