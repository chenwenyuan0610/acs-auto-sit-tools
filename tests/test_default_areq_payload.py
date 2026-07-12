import html
import json
import re
from pathlib import Path


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
    assert payload["acctNumber"] == "5678910000000000"
    assert payload["merchantName"] == "HiTRUST EMV Demo Merchant"
    assert payload["dsURL"] == "http://172.58.1.100:8020/api-proxy/challenge/2.2.0/001/rreq"


def test_default_areq_url_matches_current_target_endpoint():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<input id="areqUrl"[^>]*value="(?P<url>[^"]+)"',
        index_html,
    )

    assert match is not None
    assert (
        html.unescape(match.group("url"))
        == "https://acscloud-test.hitrust-us.com/acs-auth-v3/auth/M/220/0c57e472-e555-2c0a-e7cf-2d6a2455fbc8/123/areq"
    )
