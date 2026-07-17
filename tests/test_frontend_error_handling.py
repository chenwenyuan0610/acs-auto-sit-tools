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

    assert 'class="tab-bar"' not in index_html
    assert 'class="tab-button' not in index_html
    assert 'id="caseList"' in index_html
    assert 'id="runSelectedCases"' in index_html
    assert 'id="runAllCases"' in index_html
    assert 'id="caseAdvancedPanel"' in index_html
    assert 'data-case-view="caseAdvancedPanel"' in index_html
    assert 'id="issuerMode"' in index_html
    for mode_id in (
        "sms_otp",
        "email_otp",
        "direct_oob",
        "selection_sms_oob",
        "selection_sms_email",
        "selection_sms_email_oob",
        "selection_email_oob",
        "default_oob_can_switch_otp",
    ):
        assert mode_id in index_html
        assert mode_id in app_js
    assert 'value="direct_otp"' not in index_html
    assert "selection_sms_otp" not in index_html
    assert 'id="preferredChallenge"' in index_html
    assert 'id="otpSourceMode"' in index_html
    assert 'id="otpLookupUrl"' in index_html
    assert 'id="transactionResultUrl"' in index_html
    assert 'id="successOtp"' in index_html
    assert 'id="failureOtp"' in index_html
    assert 'id="sitAreqUrl"' in index_html
    assert '<label class="wide-setting">\n            SIT AReq URL' in index_html
    assert 'id="validCardNumber"' in index_html
    assert 'id="invalidCardNumber"' in index_html
    assert 'id="otpFailureMaxAttempts"' in index_html
    assert 'id="caseDelaySeconds"' in index_html
    assert 'id="includeSlowCases"' in index_html
    assert 'id="otpExpiryWaitSeconds"' in index_html
    assert 'id="sitRunSummary"' in index_html
    assert "/api/sit/browser-cases" in app_js
    assert "/api/sit/issuer-modes" in app_js
    assert "/api/sit/run" in app_js
    assert 'mode: "live"' in app_js
    assert "issuerMode:" in app_js
    assert '|| "sms_otp"' in app_js
    assert "preferredChallenge:" in app_js
    assert 'preferredChallenge: preferredChallengeInput?.value || "auto"' in app_js
    assert "otpSourceMode:" in app_js
    assert "otpLookupUrl:" in app_js
    assert "transactionResultUrl:" in app_js
    assert "successOtp:" in app_js
    assert "failureOtp:" in app_js
    assert "validCardNumber:" in app_js
    assert "invalidCardNumber:" in app_js
    assert "otpFailureMaxAttempts:" in app_js
    assert "caseDelaySeconds:" in app_js
    assert "includeSlowCases:" in app_js
    assert "otpExpiryWaitSeconds:" in app_js
    assert 'includeSlowCasesInput?.addEventListener("change"' in app_js
    assert "renderSitRunSummary" in app_js
    assert 'classList.toggle("advanced-active"' in app_js


def test_preferred_challenge_uses_switch_to_otp_label():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert '<option value="otp">Switch to OTP</option>' in index_html
    assert 'otp: "Switch to OTP"' in app_js


def test_preferred_challenge_is_guarded_for_single_destination_modes():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "function updatePreferredChallengeGuard" in app_js
    assert "mode.requiresPreferredChallenge === false" in app_js
    assert 'preferredChallengeInput.value = "auto"' in app_js
    assert "preferredChallengeInput.disabled = true" in app_js
    assert 'preferredChallengeInput?.addEventListener("change", async () => {' in app_js
    assert "await loadSitCases()" in app_js
    assert "sitCases = result.cases || [];\n    caseResults = {};" in app_js
    assert 'selectedCaseId = sitCases[0]?.id || "";' in app_js


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
    assert "sourceFormat" in app_js
    assert "sourceSheets" in app_js
    assert "generatedCaseCount" in app_js
    assert "defaultSupportedLocales" in app_js
    assert "issuerId:" in app_js
    assert "availability?.enabled === false" in app_js
    assert ":not(:disabled)" in app_js
    assert ".wording-import-controls" in styles
    assert ".case-unavailable-reason" in styles
    assert 'id="wordingLocale"' in index_html
    assert '<option value="all"' in index_html
    assert '<option value="en_US"' in index_html
    assert "wordingLocaleInput" in app_js
    assert "wordingLocale:" in app_js
    assert 'wordingLocaleInput?.addEventListener("change"' in app_js
    assert 'issuerModeInput?.addEventListener("change", reloadCasesForIssuerMode)' in app_js
    assert 'class="wide-setting"' in index_html
    assert ".wide-setting" in styles
    assert "grid-column: 1 / -1" in styles


def test_sit_controls_use_execution_and_settings_sidebar():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'data-case-view="caseExecutionPanel"' in index_html
    assert 'data-case-view="caseSettingsPanel"' in index_html
    assert 'data-case-view="caseAdvancedPanel"' in index_html
    assert 'id="caseExecutionPanel"' in index_html
    assert 'id="caseSettingsPanel"' in index_html
    assert 'id="caseProgressSummary"' not in index_html
    assert "caseImplementation" not in app_js
    assert "function setCaseControlView" in app_js
    assert ".case-sidebar" in styles
    assert ".case-control-view:not(.active)" in styles
    assert ".sit-workspace.advanced-active" in styles
    assert ".advanced-active .case-detail-panel" in styles


def test_case_selection_checkboxes_use_large_click_targets():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert "#selectAllCases" in styles
    assert 'input[type="checkbox"]' in styles
    assert "height: 24px" in styles
    assert "width: 24px" in styles
    assert "grid-template-columns: 30px minmax(0, 1fr) 72px" in styles
    assert ".case-check" in styles


def test_frontend_uses_chinese_visible_labels():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    assert "進階工具" in index_html
    assert "執行案例" in index_html
    assert "送出 AReq" in index_html
    assert "執行選取案例" in index_html
    assert "發卡行模式" in index_html
    assert "OTP 來源" in index_html
    assert "執行完成" in app_js
    assert "通過" in app_js


def test_manual_runner_is_nested_as_an_advanced_tool():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'id="manualRunner"' not in index_html
    assert 'id="caseAdvancedPanel" class="workspace case-control-view advanced-tools-view"' in index_html
    assert 'casePanelContentEl?.appendChild(caseAdvancedPanelEl)' in app_js
    assert ".advanced-tools-view" in styles


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
    assert "const comparisonFields = details.comparison?.fields || []" in app_js
    assert "comparisonFields.map((field) => [field.name, field.actual ?? null])" in app_js
    assert "function promptVisibleTextSummary" in app_js
    assert "function collectResultDifferences" in app_js
    assert "function renderResultDifferences" in app_js
    assert "actualKeywords: promptVisibleTextSummary(details.prompt)" in app_js
    assert "const actualPromptText = promptVisibleTextSummary(details.prompt)" in app_js
    assert "emptyOtpValidation: details.emptyOtpValidation" in app_js
    assert 'className = "difference-item"' in app_js
    assert "textContent" in app_js
    assert ".difference-item" in styles
    assert "color: var(--danger)" in styles
    assert ".actual-result-output.has-differences" in styles


def test_frontend_shows_compact_excel_field_results_and_collapsed_technical_details():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert "function expectedResultForCase" in app_js
    assert "function promptFieldSummary" in app_js
    assert "function collectTechnicalRequests" in app_js
    assert "function dedupeTechnicalRequests" in app_js
    assert "function technicalRequestOrder" in app_js
    assert "function renderTechnicalDetails" in app_js
    assert "return dedupeTechnicalRequests(requests).sort" in app_js
    assert "title.textContent = `${index + 1}. ${request.label}`" in app_js
    assert 'url.className = "request-url"' in app_js
    assert 'url.textContent = request.url || "-"' in app_js
    assert "meta.textContent = `${request.label} · ${request.method}${request.status ? ` -> ${request.status}` : \"\"}`" in app_js
    assert "if (value.form || value.cres)" not in app_js
    assert 'addTechnicalRequest(requests, "Notification", null' not in app_js
    assert 'addTechnicalRequest(requests, "Notification", value.notification.http)' not in app_js
    assert 'notification: "Notification"' not in app_js
    assert '"AReq"' in app_js
    assert '"CReq"' in app_js
    assert 'otpSubmission: "OTP Submit"' in app_js
    assert 'otpSubmissions: "OTP Submit"' in app_js
    assert 'id="caseRequestTimeline"' in index_html
    assert ".request-timeline" in styles
    assert ".request-item" in styles
    assert 'rawHtml' not in app_js[app_js.index("function actualResultForCase"):app_js.index("function differenceValue")]
    assert '<details class="case-run-details">' in index_html
    assert '<details class="case-run-details" open>' not in index_html
    assert "技術細節" in index_html


def test_case_status_does_not_wrap_on_mobile():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    case_status_rule = styles[styles.index(".case-status {"):styles.index(".case-status.running")]
    assert "white-space: nowrap" in case_status_rule
    assert "flex-shrink: 0" in case_status_rule
    assert "@media (max-width: 600px)" in styles


def test_frontend_renders_returned_html_in_a_sandboxed_preview():
    index_html = Path("static/index.html").read_text(encoding="utf-8")
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert 'id="caseHtmlPreview"' in index_html
    assert index_html.index('id="caseHtmlPreview"') < index_html.index('id="caseComparisonTitle"')
    assert "function collectHtmlPreviews" in app_js
    assert "function renderHtmlPreviews" in app_js
    assert "function isUiValidationCase" in app_js
    assert 'startsWith("ui_")' in app_js
    assert 'action?.type === "assert_stage_ui"' in app_js
    assert 'frame.setAttribute("sandbox", "")' in app_js
    assert 'frame.setAttribute("referrerpolicy", "no-referrer")' in app_js
    assert "Content-Security-Policy" in app_js
    assert "default-src 'none'" in app_js
    assert "img-src data: http: https:" in app_js
    assert "baseUrl: value.formAction" in app_js
    assert "frame.srcdoc = sandboxedPreviewHtml(preview.html, preview.baseUrl)" in app_js
    assert 'copyButton.textContent = "Copy HTML"' in app_js
    assert "navigator.clipboard.writeText(preview.html)" in app_js
    assert ".html-preview-frame" in styles
    assert "height: 700px" in styles
    assert "width: 390px" in styles
    mobile_rules = styles[styles.index("@media (max-width: 600px)"):]
    assert ".detail-header" in mobile_rules
    assert "flex-direction: column" in mobile_rules
