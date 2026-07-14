const statusEl = document.querySelector("#status");
const sendAreqButton = document.querySelector("#sendAreq");
const sendCreqButton = document.querySelector("#sendCreq");
const areqUrlInput = document.querySelector("#areqUrl");
const creqUrlInput = document.querySelector("#creqUrl");
const headersInput = document.querySelector("#headers");
const timeoutInput = document.querySelector("#timeoutSeconds");
const autoSelectSmsInput = document.querySelector("#autoSelectSms");
const autoSubmitOtpInput = document.querySelector("#autoSubmitOtp");
const simulatedOtpInput = document.querySelector("#simulatedOtp");
const areqPayloadInput = document.querySelector("#areqPayload");
const creqPayloadInput = document.querySelector("#creqPayload");
const aresOutput = document.querySelector("#aresOutput");
const cresOutput = document.querySelector("#cresOutput");
const notificationOutput = document.querySelector("#notificationOutput");
const evidenceOutput = document.querySelector("#evidenceOutput");
const tabButtons = document.querySelectorAll(".tab-button");
const tabPanels = document.querySelectorAll(".tab-panel");
const caseViewButtons = document.querySelectorAll("[data-case-view]");
const caseViewPanels = document.querySelectorAll(".case-control-view");
const caseListEl = document.querySelector("#caseList");
const caseCountEl = document.querySelector("#caseCount");
const selectAllCasesInput = document.querySelector("#selectAllCases");
const runSelectedCasesButton = document.querySelector("#runSelectedCases");
const runAllCasesButton = document.querySelector("#runAllCases");
const issuerModeInput = document.querySelector("#issuerMode");
const issuerProfileInput = document.querySelector("#issuerProfile");
const wordingWorkbookInput = document.querySelector("#wordingWorkbook");
const importWordingWorkbookButton = document.querySelector("#importWordingWorkbook");
const wordingImportStatusEl = document.querySelector("#wordingImportStatus");
const preferredChallengeInput = document.querySelector("#preferredChallenge");
const otpSourceModeInput = document.querySelector("#otpSourceMode");
const otpLookupUrlInput = document.querySelector("#otpLookupUrl");
const successOtpInput = document.querySelector("#successOtp");
const failureOtpInput = document.querySelector("#failureOtp");
const sitAreqUrlInput = document.querySelector("#sitAreqUrl");
const validCardNumberInput = document.querySelector("#validCardNumber");
const invalidCardNumberInput = document.querySelector("#invalidCardNumber");
const otpFailureMaxAttemptsInput = document.querySelector("#otpFailureMaxAttempts");
const caseDelaySecondsInput = document.querySelector("#caseDelaySeconds");
const sitRunSummaryEl = document.querySelector("#sitRunSummary");
const caseTitleEl = document.querySelector("#caseTitle");
const caseSubtitleEl = document.querySelector("#caseSubtitle");
const caseStatusEl = document.querySelector("#caseStatus");
const caseAcsTransIdEl = document.querySelector("#caseAcsTransId");
const caseAcsTransIdValueEl = document.querySelector("#caseAcsTransIdValue");
const caseFunctionPointEl = document.querySelector("#caseFunctionPoint");
const caseModuleEl = document.querySelector("#caseModule");
const caseStepsListEl = document.querySelector("#caseStepsList");
const caseExpectedOutput = document.querySelector("#caseExpectedOutput");
const caseActualOutput = document.querySelector("#caseActualOutput");
const caseDiffOutput = document.querySelector("#caseDiffOutput");
const caseRunOutput = document.querySelector("#caseRunOutput");

let evidence = [];
let sitCases = [];
let issuerModes = [];
let selectedCaseId = "";
let caseResults = {};

function parseJsonField(field, label) {
  try {
    return JSON.parse(field.value || "{}");
  } catch (error) {
    throw new Error(`${label} JSON parse failed: ${error.message}`);
  }
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function acsTransIdForResult(result) {
  const details = result?.details || {};
  const transactionIds = (details.transactions || []).flatMap((transaction) => [
    transaction.ares?.acsTransID,
    transaction.cres?.acsTransID,
    transaction.notification?.notification?.cres?.acsTransID,
    transaction.notification?.cres?.acsTransID,
  ]);
  const candidates = [
    details.ares?.acsTransID,
    details.cres?.acsTransID,
    details.notification?.notification?.cres?.acsTransID,
    details.notification?.cres?.acsTransID,
    ...transactionIds,
  ];
  return candidates.find((value) => typeof value === "string" && value.trim())?.trim() || "";
}

function actualResultForCase(result) {
  if (!result) {
    return { message: "尚未執行" };
  }

  const details = result.details || {};
  const prompt = details.prompt
    ? {
        visibleText: details.prompt.visibleText || [],
        missing: details.prompt.missing || [],
      }
    : undefined;
  const transactions = Array.isArray(details.transactions)
    ? details.transactions.map((transaction) => ({
        label: transaction.label || `Transaction ${(transaction.index ?? 0) + 1}`,
        expectedStatus: transaction.expectedStatus,
        actualStatus: transaction.actualStatus,
        passed: transaction.passed,
      }))
    : undefined;

  return Object.fromEntries(
    Object.entries({
      status: statusLabel(result.status),
      reason: result.reason || undefined,
      ARes: details.ares,
      CRes: details.cres,
      notification: details.notification?.notification ?? details.notification,
      prompt,
      transactions,
      resendLimit: details.resendLimit,
      error: details.errorMatch?.actual ?? details.error,
    }).filter(([, value]) => value !== undefined && value !== null)
  );
}

function differenceValue(value) {
  if (value === undefined || value === null || value === "") {
    return "未回傳";
  }
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function collectResultDifferences(result) {
  if (!result || ["pending", "running"].includes(result.status)) {
    return [];
  }
  if (result.status === "skipped") {
    return [{ label: "略過原因", message: result.reason || "案例未執行", tone: "neutral" }];
  }
  if (result.status === "pass") {
    return [];
  }

  const details = result.details || {};
  const differences = [];
  const keys = new Set();
  const addDifference = (difference) => {
    const key = `${difference.label}|${differenceValue(difference.expected)}|${differenceValue(difference.actual)}`;
    if (!keys.has(key)) {
      keys.add(key);
      differences.push(difference);
    }
  };

  for (const [field, mismatch] of Object.entries(details.aresMismatches || {})) {
    addDifference({ label: `ARes ${field}`, expected: mismatch.expected, actual: mismatch.actual });
  }

  const expectedMessages = details.expected?.messages || {};
  for (const [messageName, actualMessage] of [
    ["ARes", details.ares],
    ["CRes", details.cres],
  ]) {
    for (const [field, expected] of Object.entries(expectedMessages[messageName] || {})) {
      const actual = actualMessage?.[field];
      if (expected !== actual) {
        addDifference({ label: `${messageName} ${field}`, expected, actual });
      }
    }
  }

  for (const prompt of details.prompt?.missing || []) {
    addDifference({ label: "缺少預期文字", expected: prompt, actual: "實際頁面未找到" });
  }

  const errorAliases = {
    code: "errorCode",
    component: "errorComponent",
    description: "errorDescription",
    detail: "errorDetail",
  };
  for (const field of details.errorMatch?.missing || []) {
    addDifference({
      label: `Erro ${field}`,
      expected: details.errorMatch?.expected?.[field],
      actual: details.errorMatch?.actual?.[errorAliases[field] || field],
    });
  }

  for (const transaction of details.transactions || []) {
    if (transaction.passed === false || transaction.expectedStatus !== transaction.actualStatus) {
      addDifference({
        label: transaction.label || `Transaction ${(transaction.index ?? 0) + 1}`,
        expected: transaction.expectedStatus,
        actual: transaction.actualStatus,
      });
    }
  }

  if (details.resendLimit && !details.resendLimit.reached) {
    addDifference({
      label: "OTP 重送上限",
      expected: "達到 ACS 重送上限",
      actual: details.resendLimit.reason || `重送 ${details.resendLimit.attemptCount || 0} 次後仍未達上限`,
    });
  }

  if (details.error) {
    addDifference({ label: "執行錯誤", message: differenceValue(details.error) });
  }
  if (differences.length === 0) {
    addDifference({ label: "執行結果", message: result.reason || "實際結果與預期不一致" });
  }
  return differences;
}

function renderResultDifferences(result) {
  const differences = collectResultDifferences(result);
  caseDiffOutput.replaceChildren();

  if (differences.length === 0) {
    const message = document.createElement("p");
    message.className = result?.status === "pass" ? "comparison-match" : "comparison-pending";
    message.textContent = result?.status === "pass" ? "實際結果符合預期" : "執行後將在此顯示差異";
    caseDiffOutput.appendChild(message);
    caseActualOutput.classList.remove("has-differences");
    return;
  }

  let hasDifferences = false;
  for (const difference of differences) {
    const item = document.createElement("div");
    item.className = "difference-item";
    if (difference.tone === "neutral") {
      item.classList.add("neutral");
    } else {
      hasDifferences = true;
    }

    const title = document.createElement("strong");
    title.textContent = difference.label;
    const detail = document.createElement("span");
    detail.textContent = difference.message || `預期：${differenceValue(difference.expected)}；實際：${differenceValue(difference.actual)}`;
    item.append(title, detail);
    caseDiffOutput.appendChild(item);
  }
  caseActualOutput.classList.toggle("has-differences", hasDifferences);
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

function renderSitRunSummary(summary) {
  if (!sitRunSummaryEl) {
    return;
  }
  const value = summary || { total: 0, completed: 0, pass: 0, fail: 0, skipped: 0, error: 0 };
  sitRunSummaryEl.innerHTML = `
    <strong>執行統計</strong>
    <span>完成 ${value.completed || 0}/${value.total || 0}，成功 ${value.pass || 0}，失敗 ${value.fail || 0}，略過 ${value.skipped || 0}，錯誤 ${value.error || 0}</span>
  `;
}

function pushEvidence(label, result) {
  evidence.unshift({
    label,
    at: new Date().toISOString(),
    statusCode: result.http?.status_code ?? null,
    elapsedMs: result.http?.elapsed_ms ?? null,
    error: result.http?.error ?? result.error ?? null,
    request: {
      method: result.http?.method,
      url: result.http?.url,
      body: result.http?.request_body,
    },
    response: result.http?.response_json ?? result.http?.response_text ?? result,
  });
  evidenceOutput.value = pretty(evidence);
}

function notificationFromAutoCreq(autoCreq) {
  return autoCreq?.otpSubmission?.notification ?? autoCreq?.notification ?? null;
}

async function postApi(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function getApi(path) {
  const response = await fetch(path, { headers: { "Accept": "application/json" } });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function readCommonEnvelope(url, payload) {
  return {
    url,
    headers: parseJsonField(headersInput, "Headers"),
    payload,
    timeoutSeconds: Number(timeoutInput.value || 30),
    autoSelectSms: Boolean(autoSelectSmsInput?.checked),
    autoSubmitOtp: Boolean(autoSubmitOtpInput?.checked),
    simulatedOtp: simulatedOtpInput?.value || "",
    otpSourceMode: otpSourceModeInput?.value || "customer_generated",
    otpLookupUrl:
      otpLookupUrlInput?.value ||
      "https://acscloud-test.hitrust-us.com/acs-sit-info/api/sit/otp/{acsTrandId}",
    successOtp: successOtpInput?.value || simulatedOtpInput?.value || "123456",
    failureOtp: failureOtpInput?.value || "000000",
    validCardNumber: validCardNumberInput?.value || "",
    invalidCardNumber: invalidCardNumberInput?.value || "",
    otpFailureMaxAttempts: Number(otpFailureMaxAttemptsInput?.value || 5),
    caseDelaySeconds: Number(caseDelaySecondsInput?.value || 0),
  };
}

function setActiveTab(tabId) {
  tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.id === tabId);
  });
}

function setCaseControlView(viewId) {
  caseViewButtons.forEach((button) => {
    const active = button.dataset.caseView === viewId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  caseViewPanels.forEach((panel) => {
    const active = panel.id === viewId;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function statusLabel(status) {
  const labels = {
    pending: "待執行",
    running: "執行中",
    pass: "通過",
    fail: "失敗",
    skipped: "略過",
    error: "錯誤",
  };
  return labels[status] || status || "待執行";
}

function statusForCase(caseItem) {
  return caseResults[caseItem.id]?.status || caseItem.status || "pending";
}

function issuerModeLabel(mode) {
  const labels = {
    selection_sms_oob: "有驗證選擇：SMS / OOB",
    selection_sms_otp: "有驗證選擇：選 SMS 進 OTP",
    direct_otp: "直接進 OTP",
    direct_oob: "直接進 OOB",
    default_oob_can_switch_otp: "預設 OOB，可切到 OTP",
  };
  return labels[mode.id] || mode.label || mode.id;
}

function preferredChallengeLabel(challenge) {
  const labels = {
    auto: "自動",
    sms: "SMS",
    oob: "OOB",
    otp: "OTP",
  };
  return labels[challenge.id] || challenge.label || challenge.id;
}

function renderCaseList() {
  if (!caseListEl) {
    return;
  }
  caseListEl.innerHTML = "";
  for (const caseItem of sitCases) {
    const status = statusForCase(caseItem);
    const unavailable = caseItem.availability?.enabled === false;
    const unavailableReason = caseItem.availability?.reason || "";
    const row = document.createElement("button");
    row.type = "button";
    row.className = `case-row ${selectedCaseId === caseItem.id ? "active" : ""} ${unavailable ? "unavailable" : ""}`;
    row.dataset.caseId = caseItem.id;
    row.innerHTML = `
      <input class="case-check" type="checkbox" aria-label="選取 ${escapeHtml(caseItem.id)}" data-case-id="${escapeHtml(caseItem.id)}" ${unavailable ? "disabled" : ""}>
      <span class="case-main">
        <span class="case-id">${escapeHtml(caseItem.id)}</span>
        <span class="case-name">${escapeHtml(caseItem.functionPoint)}</span>
        ${unavailable ? `<span class="case-unavailable-reason">${escapeHtml(unavailableReason)}</span>` : ""}
      </span>
      <span class="case-status ${status}">${statusLabel(status)}</span>
    `;
    row.addEventListener("click", (event) => {
      if (event.target?.classList?.contains("case-check")) {
        updateSelectAllState();
        return;
      }
      selectCase(caseItem.id);
    });
    caseListEl.appendChild(row);
  }
  updateSelectAllState();
}

function selectCase(caseId) {
  const caseItem = sitCases.find((item) => item.id === caseId);
  if (!caseItem) {
    return;
  }
  selectedCaseId = caseId;
  const result = caseResults[caseId];
  const status = result?.status || caseItem.status || "pending";
  caseTitleEl.textContent = `${caseItem.id} ${caseItem.functionPoint}`;
  caseSubtitleEl.textContent = caseItem.system || "瀏覽器 SIT";
  caseStatusEl.textContent = statusLabel(status);
  caseStatusEl.className = `case-status ${status}`;
  const acsTransId = acsTransIdForResult(result);
  caseAcsTransIdValueEl.textContent = acsTransId;
  caseAcsTransIdEl.hidden = !acsTransId;
  caseFunctionPointEl.textContent = caseItem.functionPoint || "-";
  caseModuleEl.textContent = caseItem.module || "-";

  caseStepsListEl.replaceChildren();
  for (const step of caseItem.steps || []) {
    const item = document.createElement("li");
    item.textContent = step;
    caseStepsListEl.appendChild(item);
  }
  if (!caseStepsListEl.children.length) {
    const item = document.createElement("li");
    item.textContent = "Excel 未提供測試步驟";
    caseStepsListEl.appendChild(item);
  }

  caseExpectedOutput.textContent = pretty(caseItem.expected || {});
  caseActualOutput.textContent = pretty(actualResultForCase(result));
  renderResultDifferences(result);
  caseRunOutput.textContent = pretty(result || {
    message: "尚未執行",
    automation: caseItem.automation,
  });
  renderCaseList();
}

function checkedCaseIds() {
  return Array.from(document.querySelectorAll(".case-check:checked")).map((input) => input.dataset.caseId);
}

function setCaseCheckboxes(checked) {
  document.querySelectorAll(".case-check:not(:disabled)").forEach((input) => {
    input.checked = checked;
  });
  updateSelectAllState();
}

function updateSelectAllState() {
  const checks = Array.from(document.querySelectorAll(".case-check:not(:disabled)"));
  if (!selectAllCasesInput || checks.length === 0) {
    return;
  }
  const checked = checks.filter((input) => input.checked).length;
  selectAllCasesInput.checked = checked === checks.length;
  selectAllCasesInput.indeterminate = checked > 0 && checked < checks.length;
}

async function loadSitCases() {
  if (!caseListEl) {
    return;
  }
  try {
    const params = new URLSearchParams({
      issuerId: issuerProfileInput?.value || "default",
      issuerMode: issuerModeInput?.value || "direct_otp",
    });
    const result = await getApi(`/api/sit/browser-cases?${params}`);
    sitCases = result.cases || [];
    caseCountEl.textContent = `${result.caseCount || sitCases.length} 個案例`;
    selectedCaseId = sitCases[0]?.id || "";
    renderCaseList();
    if (selectedCaseId) {
      selectCase(selectedCaseId);
    }
  } catch (error) {
    caseRunOutput.textContent = pretty({ error: error.message });
  }
}

async function loadWordingProfiles(preferredIssuerId = issuerProfileInput?.value || "default") {
  if (!issuerProfileInput) {
    return;
  }
  try {
    const result = await getApi("/api/sit/wording-profiles");
    const issuers = result.issuers || [];
    issuerProfileInput.replaceChildren();
    if (issuers.length === 0) {
      const option = document.createElement("option");
      option.value = "default";
      option.textContent = "預設發卡行";
      issuerProfileInput.appendChild(option);
    } else {
      for (const issuer of issuers) {
        const option = document.createElement("option");
        option.value = issuer.id;
        option.textContent = `${issuer.name || issuer.id} (${(issuer.supportedLocales || []).join(", ")})`;
        issuerProfileInput.appendChild(option);
      }
    }
    issuerProfileInput.value = Array.from(issuerProfileInput.options).some(
      (option) => option.value === preferredIssuerId
    ) ? preferredIssuerId : issuerProfileInput.options[0]?.value || "default";
    const summary = result.summary || {};
    wordingImportStatusEl.textContent = result.imported
      ? `${result.sourceFile || "話術設定"}：${summary.issuerCount || 0} 個發卡行、${summary.localeCount || 0} 種語言、${summary.wordingCount || 0} 筆話術`
      : "尚未匯入話術設定；目前使用原始案例內容";
    wordingImportStatusEl.classList.remove("error");
  } catch (error) {
    wordingImportStatusEl.textContent = error.message;
    wordingImportStatusEl.classList.add("error");
  }
}

async function importWordingWorkbook() {
  const file = wordingWorkbookInput?.files?.[0];
  if (!file) {
    wordingImportStatusEl.textContent = "請先選擇 .xlsx 話術檔";
    wordingImportStatusEl.classList.add("error");
    return;
  }
  importWordingWorkbookButton.disabled = true;
  wordingImportStatusEl.textContent = "匯入中...";
  wordingImportStatusEl.classList.remove("error");
  try {
    const result = await postApi("/api/sit/wording-profiles/import", {
      fileName: file.name,
      contentBase64: arrayBufferToBase64(await file.arrayBuffer()),
    });
    const preferredIssuerId = result.issuers?.[0]?.id || "default";
    await loadWordingProfiles(preferredIssuerId);
    await loadSitCases();
  } catch (error) {
    wordingImportStatusEl.textContent = error.message;
    wordingImportStatusEl.classList.add("error");
  } finally {
    importWordingWorkbookButton.disabled = false;
  }
}

async function loadIssuerModes() {
  if (!issuerModeInput || !preferredChallengeInput) {
    return;
  }
  try {
    const result = await getApi("/api/sit/issuer-modes");
    issuerModes = result.issuerModes || [];
    issuerModeInput.innerHTML = "";
    for (const mode of issuerModes) {
      const option = document.createElement("option");
      option.value = mode.id;
      option.textContent = issuerModeLabel(mode);
      issuerModeInput.appendChild(option);
    }
    issuerModeInput.value = result.defaultIssuerMode || "direct_otp";

    preferredChallengeInput.innerHTML = "";
    for (const challenge of result.preferredChallenges || []) {
      const option = document.createElement("option");
      option.value = challenge.id;
      option.textContent = preferredChallengeLabel(challenge);
      preferredChallengeInput.appendChild(option);
    }
    preferredChallengeInput.value = result.defaultPreferredChallenge || "auto";
  } catch (error) {
    caseRunOutput.textContent = pretty({ error: error.message });
  }
}

async function runSitCases(caseIds) {
  if (!caseIds.length) {
    setStatus("未選擇案例", true);
    return;
  }
  runSelectedCasesButton.disabled = true;
  runAllCasesButton.disabled = true;
  setStatus("執行 SIT 案例中");
  for (const caseId of caseIds) {
    caseResults[caseId] = { caseId, status: "running", reason: "執行中" };
  }
  renderSitRunSummary({ total: caseIds.length, completed: 0, pass: 0, fail: 0, skipped: 0, error: 0 });
  renderCaseList();
  if (selectedCaseId) {
    selectCase(selectedCaseId);
  }
  try {
    const result = await postApi("/api/sit/run", {
      caseIds,
      mode: "live",
      issuerId: issuerProfileInput?.value || "default",
      issuerMode: issuerModeInput?.value || "direct_otp",
      preferredChallenge: preferredChallengeInput?.value || "auto",
      transaction: readCommonEnvelope(
        sitAreqUrlInput?.value || areqUrlInput.value,
        parseJsonField(areqPayloadInput, "AReq")
      ),
    });
    for (const item of result.results || []) {
      caseResults[item.caseId] = item;
    }
    renderCaseList();
    selectCase(selectedCaseId || caseIds[0]);
    renderSitRunSummary(result.summary);
    setStatus(`執行完成 ${result.summary?.completed || 0}/${result.summary?.total || caseIds.length}，成功 ${result.summary?.pass || 0}，失敗 ${result.summary?.fail || 0}`);
  } catch (error) {
    caseRunOutput.textContent = pretty({ error: error.message });
    setStatus("SIT 執行錯誤", true);
  } finally {
    runSelectedCasesButton.disabled = false;
    runAllCasesButton.disabled = false;
  }
}

function refreshAreqTransactionIds(payload) {
  payload.threeDSServerTransID = crypto.randomUUID();
  payload.dsTransID = crypto.randomUUID();
  areqPayloadInput.value = pretty(payload);
  return payload;
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tab));
});

caseViewButtons.forEach((button) => {
  button.addEventListener("click", () => setCaseControlView(button.dataset.caseView));
});

selectAllCasesInput?.addEventListener("change", () => {
  setCaseCheckboxes(selectAllCasesInput.checked);
});

runSelectedCasesButton?.addEventListener("click", () => runSitCases(checkedCaseIds()));

runAllCasesButton?.addEventListener("click", () => runSitCases(
  sitCases
    .filter((caseItem) => caseItem.availability?.enabled !== false)
    .map((caseItem) => caseItem.id)
));

issuerProfileInput?.addEventListener("change", loadSitCases);
issuerModeInput?.addEventListener("change", loadSitCases);
importWordingWorkbookButton?.addEventListener("click", importWordingWorkbook);

sendAreqButton.addEventListener("click", async () => {
  sendAreqButton.disabled = true;
  setStatus("送出 AReq 中");
  try {
    const areqPayload = refreshAreqTransactionIds(parseJsonField(areqPayloadInput, "AReq"));
    const result = await postApi(
      "/api/areq",
      readCommonEnvelope(areqUrlInput.value, areqPayload)
    );
    aresOutput.value = pretty(result.ares ?? result.http?.response_text ?? result);
    if (result.http?.request_body) {
      areqPayloadInput.value = pretty(result.http.request_body);
    }
    pushEvidence("AReq", result);
    if (!result.ok) {
      throw new Error(result.error || result.http?.error || "AReq 傳輸失敗");
    }

    if (result.creqUrl) {
      creqUrlInput.value = result.creqUrl;
    }
    if (result.autoCreq) {
      cresOutput.value = pretty(result.autoCreq.cres ?? result.autoCreq.http?.response_text ?? result.autoCreq);
      notificationOutput.value = pretty(notificationFromAutoCreq(result.autoCreq) ?? {});
      pushEvidence("CReq", result.autoCreq);
      if (!result.autoCreq.ok) {
        throw new Error(result.autoCreq.error || result.autoCreq.http?.error || "CReq 傳輸失敗");
      }
      if (result.autoCreq.nextCreqDraft) {
        creqPayloadInput.value = pretty(result.autoCreq.nextCreqDraft);
        sendCreqButton.disabled = false;
        setStatus("繼續 Challenge");
        return;
      }
      setStatus(result.autoCreq.cres?.transStatus ? `CRes ${result.autoCreq.cres.transStatus}` : "Challenge 執行中");
      return;
    }
    if (result.creqDraft) {
      creqPayloadInput.value = pretty(result.creqDraft);
      sendCreqButton.disabled = false;
      setStatus("需要 Challenge");
    } else if (result.draftError) {
      setStatus("CReq 草稿錯誤", true);
      evidenceOutput.value = pretty([{ draftError: result.draftError }, ...evidence]);
    } else {
      setStatus(result.ares?.transStatus ? `ARes ${result.ares.transStatus}` : "AReq 完成");
    }
  } catch (error) {
    setStatus("AReq 錯誤", true);
    evidenceOutput.value = pretty([{ error: error.message }, ...evidence]);
  } finally {
    sendAreqButton.disabled = false;
  }
});

async function initializeSitRunner() {
  await loadIssuerModes();
  await loadWordingProfiles();
  await loadSitCases();
}

initializeSitRunner();
renderSitRunSummary(null);

sendCreqButton.addEventListener("click", async () => {
  sendCreqButton.disabled = true;
  setStatus("送出 CReq 中");
  try {
    const result = await postApi(
      "/api/creq",
      readCommonEnvelope(creqUrlInput.value, parseJsonField(creqPayloadInput, "CReq"))
    );
    cresOutput.value = pretty(result.cres ?? result.http?.response_text ?? result);
    pushEvidence("CReq", result);
    if (!result.ok) {
      throw new Error(result.error || result.http?.error || "CReq 傳輸失敗");
    }

    if (result.nextCreqDraft) {
      creqPayloadInput.value = pretty(result.nextCreqDraft);
      sendCreqButton.disabled = false;
      setStatus("繼續 Challenge");
    } else {
      setStatus(result.cres?.transStatus ? `CRes ${result.cres.transStatus}` : "CReq 完成");
    }
  } catch (error) {
    setStatus("CReq 錯誤", true);
    evidenceOutput.value = pretty([{ error: error.message }, ...evidence]);
    sendCreqButton.disabled = false;
  }
});
