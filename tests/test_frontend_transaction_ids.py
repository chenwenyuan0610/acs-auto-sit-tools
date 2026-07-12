from pathlib import Path


def test_frontend_regenerates_areq_transaction_ids_before_submit():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "refreshAreqTransactionIds" in app_js
    assert 'payload.threeDSServerTransID = crypto.randomUUID()' in app_js
    assert 'payload.dsTransID = crypto.randomUUID()' in app_js
    assert "areqPayloadInput.value = pretty(payload)" in app_js
    assert "areqPayloadInput.value = pretty(result.http.request_body)" in app_js


def test_frontend_displays_auto_creq_result_after_areq():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "result.autoCreq" in app_js
    assert 'pushEvidence("CReq", result.autoCreq)' in app_js
    assert "cresOutput.value = pretty(result.autoCreq.cres" in app_js
