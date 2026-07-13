import html
import json
import re
from pathlib import Path

from tools.run_live_sit import _transaction_from_index


def test_default_areq_payload_contains_full_browser_sample_fields():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<textarea id="areqPayload"[^>]*>(?P<payload>.*?)</textarea>',
        index_html,
        re.DOTALL,
    )

    assert match is not None
    payload = json.loads(html.unescape(match.group("payload")))

    assert payload["messageExtension"][0]["id"] == "A000000004-merchantData"
    assert payload["messageExtension"][1]["id"] == "A000000004-acsRBA"
    assert payload["browserUserAgent"].startswith("Mozilla/5.0")
    assert payload["purchaseAmount"] == "5520"
    assert payload["notificationURL"].startswith("https://hooks.stripe.com/")
    assert payload["acctNumber"] == "4771048901645588"
    assert payload["merchantName"] == "HiTRUST EMV Demo Merchant"
    assert payload["dsURL"] == "http://172.58.1.100:8020/api-proxy/challenge/2.2.0/001/rreq"


def test_default_areq_url_matches_current_target_endpoint():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    expected_url = (
        "https://acscloud-test.hitrust-us.com/acs-auth-v3/auth/V/220/"
        "eff82784-e641-8477-3b5b-f14c2ed2ee10/123/areq"
    )

    for element_id in ("areqUrl", "sitAreqUrl"):
        match = re.search(
            rf'<input id="{element_id}"[^>]*value="(?P<url>[^"]+)"',
            index_html,
        )
        assert match is not None
        assert html.unescape(match.group("url")) == expected_url


def test_default_invalid_card_changes_only_the_last_digit():
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    valid_match = re.search(
        r'<input id="validCardNumber"[^>]*value="(?P<card>[^"]+)"',
        index_html,
    )
    invalid_match = re.search(
        r'<input id="invalidCardNumber"[^>]*value="(?P<card>[^"]+)"',
        index_html,
    )

    assert valid_match is not None
    assert invalid_match is not None
    valid_card = html.unescape(valid_match.group("card"))
    invalid_card = html.unescape(invalid_match.group("card"))
    assert valid_card == "4771048901645588"
    assert invalid_card == "4771048901645589"
    assert invalid_card[:-1] == valid_card[:-1]


def test_live_runner_defaults_to_acs_generated_otp_lookup():
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    transaction = _transaction_from_index(index_html, timeout_seconds=30)

    assert transaction["otpSourceMode"] == "acs_generated"
    assert re.search(
        r'<option value="acs_generated"\s+selected>',
        index_html,
    )
