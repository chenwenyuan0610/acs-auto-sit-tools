from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all ACS SIT browser cases against the local web server.")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="live_run_result.json")
    parser.add_argument("--timeout-seconds", default=15, type=int)
    parser.add_argument("--issuer-mode", default="selection_sms_otp")
    parser.add_argument("--preferred-challenge", default="auto")
    parser.add_argument("--case-delay-seconds", default=1.5, type=float)
    parser.add_argument("--cases", default="", help="Comma-separated case IDs. Defaults to all Browser cases.")
    args = parser.parse_args()

    index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    cases = _get_json(f"{args.server}/api/sit/browser-cases")["cases"]
    case_ids = [case_id.strip() for case_id in args.cases.split(",") if case_id.strip()]
    if not case_ids:
        case_ids = [case["id"] for case in cases]
    body = {
        "caseIds": case_ids,
        "mode": "live",
        "issuerMode": args.issuer_mode,
        "preferredChallenge": args.preferred_challenge,
        "transaction": _transaction_from_index(index_html, args.timeout_seconds, args.case_delay_seconds),
    }
    result = _post_json(f"{args.server}/api/sit/run", body, timeout=900)
    output_path = ROOT / args.output
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result.get("summary"), ensure_ascii=False))
    print(f"saved {output_path}")
    return 0


def _transaction_from_index(index_html: str, timeout_seconds: int, case_delay_seconds: float = 0) -> dict[str, Any]:
    return {
        "url": _input_value(index_html, "sitAreqUrl") or _input_value(index_html, "areqUrl"),
        "headers": json.loads(_textarea_value(index_html, "headers")),
        "payload": json.loads(_textarea_value(index_html, "areqPayload")),
        "timeoutSeconds": timeout_seconds,
        "autoSelectSms": True,
        "autoSubmitOtp": True,
        "simulatedOtp": _input_value(index_html, "simulatedOtp") or "123456",
        "otpSourceMode": "customer_generated",
        "successOtp": _input_value(index_html, "successOtp") or "123456",
        "failureOtp": _input_value(index_html, "failureOtp") or "000000",
        "validCardNumber": _input_value(index_html, "validCardNumber") or "5678910000000000",
        "invalidCardNumber": _input_value(index_html, "invalidCardNumber") or "4000000000000002",
        "otpFailureMaxAttempts": int(_input_value(index_html, "otpFailureMaxAttempts") or 5),
        "caseDelaySeconds": case_delay_seconds,
    }


def _input_value(index_html: str, element_id: str) -> str:
    match = re.search(rf'<input[^>]*id="{re.escape(element_id)}"[^>]*>', index_html)
    if not match:
        return ""
    value = re.search(r'value="([^"]*)"', match.group(0))
    return html.unescape(value.group(1)) if value else ""


def _textarea_value(index_html: str, element_id: str) -> str:
    match = re.search(rf'<textarea[^>]*id="{re.escape(element_id)}"[^>]*>(.*?)</textarea>', index_html, re.S)
    return html.unescape(match.group(1)) if match else "{}"


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, body: dict[str, Any], timeout: int) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
