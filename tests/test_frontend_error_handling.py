from pathlib import Path


def test_frontend_marks_areq_transport_failure_as_error():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "if (!result.ok)" in app_js
    assert 'setStatus("AReq 錯誤", true)' in app_js
    assert "throw new Error(result.error" in app_js


def test_frontend_has_notification_result_output():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert 'id="notificationOutput"' in index_html
    assert "notificationOutput" in app_js
    assert "otpSubmission?.notification" in app_js


def test_frontend_has_sit_runner_tab_and_controls():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert 'data-tab="sitRunner"' in index_html
    assert 'id="caseList"' in index_html
    assert 'id="runSelectedCases"' in index_html
    assert 'id="runAllCases"' in index_html
    assert 'id="caseProgressSummary"' in index_html
    assert 'id="issuerMode"' in index_html
    assert "selection_sms_otp" in index_html
    assert 'id="preferredChallenge"' in index_html
    assert 'id="otpSourceMode"' in index_html
    assert 'id="successOtp"' in index_html
    assert 'id="failureOtp"' in index_html
    assert "/api/sit/browser-cases" in app_js
    assert "/api/sit/issuer-modes" in app_js
    assert "/api/sit/run" in app_js
    assert 'mode: "live"' in app_js
    assert "issuerMode:" in app_js
    assert "selection_sms_otp" in app_js
    assert "preferredChallenge:" in app_js
    assert "otpSourceMode:" in app_js
    assert "successOtp:" in app_js
    assert "failureOtp:" in app_js
    assert "caseImplementation" in app_js
    assert "已編寫" in app_js
    assert "待編寫" in app_js


def test_frontend_uses_chinese_visible_labels():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "手動交易" in index_html
    assert "SIT 測試" in index_html
    assert "送出 AReq" in index_html
    assert "執行選取案例" in index_html
    assert "發卡行模式" in index_html
    assert "OTP 來源" in index_html
    assert "執行完成" in app_js
    assert "通過" in app_js
    assert "案例編寫進度" in index_html


def test_tab_panel_hidden_rule_overrides_workspace_layout():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert ".tab-panel:not(.active)" in styles
    assert styles.rfind(".tab-panel:not(.active)") > styles.rfind(".sit-workspace")
