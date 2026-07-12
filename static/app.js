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
const caseListEl = document.querySelector("#caseList");
const caseCountEl = document.querySelector("#caseCount");
const caseProgressSummaryEl = document.querySelector("#caseProgressSummary");
const selectAllCasesInput = document.querySelector("#selectAllCases");
const runSelectedCasesButton = document.querySelector("#runSelectedCases");
const runAllCasesButton = document.querySelector("#runAllCases");
const issuerModeInput = document.querySelector("#issuerMode");
const preferredChallengeInput = document.querySelector("#preferredChallenge");
const otpSourceModeInput = document.querySelector("#otpSourceMode");
const successOtpInput = document.querySelector("#successOtp");
const failureOtpInput = document.querySelector("#failureOtp");
const caseTitleEl = document.querySelector("#caseTitle");
const caseSubtitleEl = document.querySelector("#caseSubtitle");
const caseStatusEl = document.querySelector("#caseStatus");
const caseStepsOutput = document.querySelector("#caseStepsOutput");
const caseExpectedOutput = document.querySelector("#caseExpectedOutput");
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

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
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
    successOtp: successOtpInput?.value || simulatedOtpInput?.value || "123456",
    failureOtp: failureOtpInput?.value || "000000",
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

function implementationStatusLabel(caseItem) {
  const status = caseItem.caseImplementation?.directOtp?.status;
  if (status === "completed") {
    return "已編寫";
  }
  return "待編寫";
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
    const row = document.createElement("button");
    row.type = "button";
    row.className = `case-row ${selectedCaseId === caseItem.id ? "active" : ""}`;
    row.dataset.caseId = caseItem.id;
    row.innerHTML = `
      <input class="case-check" type="checkbox" aria-label="選取 ${caseItem.id}" data-case-id="${caseItem.id}">
      <span class="case-main">
        <span class="case-id">${caseItem.id}</span>
        <span class="case-name">${caseItem.functionPoint}</span>
        <span class="case-implementation">${implementationStatusLabel(caseItem)}</span>
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
  caseSubtitleEl.textContent = `${caseItem.system} · ${caseItem.module}`;
  caseStatusEl.textContent = statusLabel(status);
  caseStatusEl.className = `case-status ${status}`;
  caseStepsOutput.value = (caseItem.steps || []).join("\n");
  caseExpectedOutput.value = pretty(caseItem.expected || {});
  caseRunOutput.value = pretty(result || {
    message: "尚未執行",
    automation: caseItem.automation,
    caseImplementation: caseItem.caseImplementation,
  });
  renderCaseList();
}

function checkedCaseIds() {
  return Array.from(document.querySelectorAll(".case-check:checked")).map((input) => input.dataset.caseId);
}

function setCaseCheckboxes(checked) {
  document.querySelectorAll(".case-check").forEach((input) => {
    input.checked = checked;
  });
  updateSelectAllState();
}

function updateSelectAllState() {
  const checks = Array.from(document.querySelectorAll(".case-check"));
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
    const result = await getApi("/api/sit/browser-cases");
    sitCases = result.cases || [];
    caseCountEl.textContent = `${result.caseCount || sitCases.length} 個案例`;
    if (caseProgressSummaryEl) {
      const progress = result.caseProgress || {};
      caseProgressSummaryEl.textContent = `direct_otp 已編寫 ${progress.directOtpCompleted || 0}/${progress.total || 0}；selection_sms_otp 已編寫 ${progress.selectionSmsOtpCompleted || 0}/${progress.total || 0}；其他模式待編寫`;
    }
    selectedCaseId = sitCases[0]?.id || "";
    renderCaseList();
    if (selectedCaseId) {
      selectCase(selectedCaseId);
    }
  } catch (error) {
    caseRunOutput.value = pretty({ error: error.message });
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
    caseRunOutput.value = pretty({ error: error.message });
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
  renderCaseList();
  if (selectedCaseId) {
    selectCase(selectedCaseId);
  }
  try {
    const result = await postApi("/api/sit/run", {
      caseIds,
      mode: "live",
      issuerMode: issuerModeInput?.value || "direct_otp",
      preferredChallenge: preferredChallengeInput?.value || "auto",
      transaction: readCommonEnvelope(
        areqUrlInput.value,
        parseJsonField(areqPayloadInput, "AReq")
      ),
    });
    for (const item of result.results || []) {
      caseResults[item.caseId] = item;
    }
    renderCaseList();
    selectCase(selectedCaseId || caseIds[0]);
    setStatus("執行完成");
  } catch (error) {
    caseRunOutput.value = pretty({ error: error.message });
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

selectAllCasesInput?.addEventListener("change", () => {
  setCaseCheckboxes(selectAllCasesInput.checked);
});

runSelectedCasesButton?.addEventListener("click", () => runSitCases(checkedCaseIds()));

runAllCasesButton?.addEventListener("click", () => runSitCases(sitCases.map((caseItem) => caseItem.id)));

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

loadSitCases();
loadIssuerModes();

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
