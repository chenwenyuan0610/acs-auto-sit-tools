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
    assert 'id="issuerMode"' in index_html
    assert "selection_sms_otp" in index_html
    assert 'id="preferredChallenge"' in index_html
    assert 'id="otpSourceMode"' in index_html
    assert 'id="otpLookupUrl"' in index_html
    assert 'id="successOtp"' in index_html
    assert 'id="failureOtp"' in index_html
    assert 'id="sitAreqUrl"' in index_html
    assert 'id="validCardNumber"' in index_html
    assert 'id="invalidCardNumber"' in index_html
    assert 'id="otpFailureMaxAttempts"' in index_html
    assert 'id="caseDelaySeconds"' in index_html
    assert 'id="sitRunSummary"' in index_html
    assert "/api/sit/browser-cases" in app_js
    assert "/api/sit/issuer-modes" in app_js
    assert "/api/sit/run" in app_js
    assert 'mode: "live"' in app_js
    assert "issuerMode:" in app_js
    assert "selection_sms_otp" in app_js
    assert "preferredChallenge:" in app_js
    assert "otpSourceMode:" in app_js
    assert "otpLookupUrl:" in app_js
    assert "successOtp:" in app_js
    assert "failureOtp:" in app_js
    assert "validCardNumber:" in app_js
    assert "invalidCardNumber:" in app_js
    assert "otpFailureMaxAttempts:" in app_js
    assert "caseDelaySeconds:" in app_js
    assert "renderSitRunSummary" in app_js


def test_frontend_imports_wording_profiles_and_disables_unavailable_cases():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'id="issuerProfile"' in index_html
    assert 'id="wordingWorkbook"' in index_html
    assert 'accept=".xlsx"' in index_html
    assert 'id="importWordingWorkbook"' in index_html
    assert 'id="wordingImportStatus"' in index_html
    assert "/api/sit/wording-profiles/import" in app_js
    assert "/api/sit/wording-profiles" in app_js
    assert "contentBase64" in app_js
    assert "issuerId:" in app_js
    assert "availability?.enabled === false" in app_js
    assert ":not(:disabled)" in app_js
    assert ".wording-import-controls" in styles
    assert ".case-unavailable-reason" in styles


def test_sit_controls_use_execution_and_settings_sidebar():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'data-case-view="caseExecutionPanel"' in index_html
    assert 'data-case-view="caseSettingsPanel"' in index_html
    assert 'id="caseExecutionPanel"' in index_html
    assert 'id="caseSettingsPanel"' in index_html
    assert 'id="caseProgressSummary"' not in index_html
    assert "caseImplementation" not in app_js
    assert "function setCaseControlView" in app_js
    assert ".case-sidebar" in styles
    assert ".case-control-view:not(.active)" in styles


def test_select_all_checkbox_is_larger_than_case_checkboxes():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert "#selectAllCases" in styles
    assert "height: 20px" in styles
    assert "width: 20px" in styles
    assert ".case-check" in styles


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


def test_tab_panel_hidden_rule_overrides_workspace_layout():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert ".tab-panel:not(.active)" in styles
    assert styles.rfind(".tab-panel:not(.active)") > styles.rfind(".sit-workspace")


def test_sit_case_detail_orders_description_steps_and_result_comparison():
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    required_ids = (
        'id="caseDescription"',
        'id="caseFunctionPoint"',
        'id="caseModule"',
        'id="caseStepsList"',
        'id="caseExpectedOutput"',
        'id="caseActualOutput"',
        'id="caseDiffOutput"',
        'id="caseRunOutput"',
    )
    for element_id in required_ids:
        assert element_id in index_html

    assert 'id="caseTestPoint"' not in index_html
    assert 'id="caseAutomation"' not in index_html
    assert index_html.index('id="caseDescription"') < index_html.index('id="caseStepsList"')
    assert index_html.index('id="caseStepsList"') < index_html.index('id="caseExpectedOutput"')
    assert index_html.index('id="caseExpectedOutput"') < index_html.index('id="caseActualOutput"')


def test_sit_case_detail_displays_acs_trans_id_after_execution():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert 'id="caseAcsTransId"' in index_html
    assert "function acsTransIdForResult" in app_js
    assert "caseAcsTransIdValueEl.textContent" in app_js
    assert 'caseAcsTransIdEl.hidden = !acsTransId' in app_js


def test_frontend_renders_actual_results_and_red_differences():
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert "function actualResultForCase" in app_js
    assert "function collectResultDifferences" in app_js
    assert "function renderResultDifferences" in app_js
    assert 'className = "difference-item"' in app_js
    assert "textContent" in app_js
    assert ".difference-item" in styles
    assert "color: var(--danger)" in styles
    assert ".actual-result-output.has-differences" in styles
