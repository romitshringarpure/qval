(function () {
  "use strict";

  const state = {
    suites: [],
    runs: [],
    selectedSuites: new Set(),
    activeRun: null,
    reviewQueue: [],
    activeReviewIndex: 0,
    activeReviewRunId: "",
    gate: null,
    filters: { status: "all", category: "all" },
    pollTimer: null,
  };

  const $ = (selector) => document.querySelector(selector);

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  }

  function clear(el) {
    el.replaceChildren();
  }

  function api(path, options) {
    return fetch(path, options).then(async (resp) => {
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(payload.error || resp.statusText);
      }
      return payload;
    });
  }

  async function init() {
    bindNavigation();
    bindRunForm();
    bindTargetControls();
    bindActions();

    await Promise.all([loadProject(), loadSuites(), loadRuns()]);
    renderSuites();
    renderSuiteSelect();
    renderRuns();
    renderRunPickers();
    bindKeyboardShortcuts();
  }

  function bindNavigation() {
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.addEventListener("click", () => showView(button.dataset.view));
    });
  }

  function bindActions() {
    $("#refresh-runs").addEventListener("click", loadRunsAndRender);
    $("#run-selected").addEventListener("click", () => {
      syncSuiteSelectFromState();
      showView("runs");
    });
    $("#refresh-review").addEventListener("click", loadReviewQueue);
    $("#review-run-select").addEventListener("change", () => {
      setDefaultBaseline("review");
      loadReviewQueue();
    });
    $("#review-baseline-select").addEventListener("change", loadReviewQueue);
    $("#evaluate-gate").addEventListener("click", loadGate);
    $("#signoff-run-select").addEventListener("change", () => {
      setDefaultBaseline("signoff");
      loadGate();
    });
    $("#signoff-baseline-select").addEventListener("change", loadGate);
    $("#submit-decision").addEventListener("click", submitModalDecision);
  }

  function bindTargetControls() {
    document.querySelectorAll('input[name="target-type"]').forEach((input) => {
      input.addEventListener("change", updateTargetFields);
    });
    updateTargetFields();
  }

  function bindRunForm() {
    $("#run-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const payload = buildRunPayload();
        const started = await api("/api/runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        showProgress(started.run_id);
      } catch (err) {
        showProgressError(err.message);
      }
    });
  }

  function showView(view) {
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
    document.querySelectorAll(".view").forEach((section) => {
      section.classList.toggle("active", section.id === `view-${view}`);
    });
  }

  async function loadProject() {
    const project = await api("/api/project");
    $("#project-root").textContent = project.root;
  }

  async function loadSuites() {
    const payload = await api("/api/suites");
    state.suites = payload.suites || [];
    state.suites.forEach((suite) => state.selectedSuites.add(suite.name));
  }

  async function loadRuns() {
    const payload = await api("/api/runs");
    state.runs = payload.runs || [];
  }

  async function loadRunsAndRender() {
    await loadRuns();
    renderRuns();
    renderRunPickers();
  }

  function renderSuites() {
    const root = $("#suite-list");
    clear(root);
    if (!state.suites.length) {
      root.appendChild(node("div", "empty-state", "No suites found."));
      return;
    }

    state.suites.forEach((suite) => {
      const card = node("article", "suite-card");
      const header = node("div", "suite-card-header");
      const title = node("label", "suite-title");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selectedSuites.has(suite.name);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedSuites.add(suite.name);
        else state.selectedSuites.delete(suite.name);
        syncSuiteSelectFromState();
      });
      title.append(checkbox, node("h2", "", suite.name));
      header.append(title, node("span", "badge", `${suite.case_count} cases`));
      card.appendChild(header);

      const badges = node("div", "badge-row");
      suite.severities.forEach((severity) => {
        badges.appendChild(node("span", `badge severity-${severity}`, severity));
      });
      suite.control_mappings.forEach((control) => {
        badges.appendChild(node("span", "badge", control.control_id));
      });
      card.appendChild(badges);

      const cases = node("div", "case-list");
      suite.cases.slice(0, 8).forEach((testCase) => {
        cases.appendChild(renderSuiteCase(testCase));
      });
      if (suite.cases.length > 8) {
        cases.appendChild(node("div", "case-meta", `${suite.cases.length - 8} more cases`));
      }
      card.appendChild(cases);
      root.appendChild(card);
    });
  }

  function renderSuiteCase(testCase) {
    const row = node("div", "case-row");
    const main = node("div", "case-main");
    main.appendChild(node("div", "case-name", `${testCase.id} - ${testCase.name}`));
    main.appendChild(node("div", "case-meta", testCase.description));
    const badges = node("div", "badge-row");
    badges.appendChild(node("span", `badge severity-${testCase.severity}`, testCase.severity));
    badges.appendChild(node("span", "badge", testCase.category));
    testCase.control_ids.forEach((controlId) => {
      badges.appendChild(node("span", "badge", controlId));
    });
    row.append(main, badges);
    return row;
  }

  function renderSuiteSelect() {
    const select = $("#suite-select");
    clear(select);
    state.suites.forEach((suite) => {
      const option = document.createElement("option");
      option.value = suite.name;
      option.textContent = suite.name;
      option.selected = state.selectedSuites.has(suite.name);
      select.appendChild(option);
    });
    select.addEventListener("change", () => {
      state.selectedSuites = new Set(Array.from(select.selectedOptions).map((opt) => opt.value));
      renderSuites();
    });
  }

  function syncSuiteSelectFromState() {
    Array.from($("#suite-select").options).forEach((option) => {
      option.selected = state.selectedSuites.has(option.value);
    });
  }

  function renderRuns() {
    const root = $("#run-history");
    clear(root);
    if (!state.runs.length) {
      root.appendChild(node("div", "empty-state", "No runs yet."));
      return;
    }
    state.runs.forEach((run) => {
      const button = node("button", "run-row");
      button.type = "button";
      button.addEventListener("click", () => loadRunDetail(run.run_id));
      const main = node("div");
      main.appendChild(node("div", "run-id", run.run_id));
      main.appendChild(node("div", "run-meta", `${run.suite} - ${run.provider} / ${run.model}`));
      const metrics = node(
        "div",
        "run-meta",
        `${run.total_tests} tests, ${run.pass_count} passed, ${run.fail_count} failed`
      );
      button.append(main, metrics);
      root.appendChild(button);
    });
  }

  function renderRunPickers() {
    const runSelects = [$("#review-run-select"), $("#signoff-run-select")];
    runSelects.forEach((select) => {
      const previous = select.value;
      clear(select);
      state.runs.forEach((run) => {
        const option = document.createElement("option");
        option.value = run.run_id;
        option.textContent = `${run.run_id} - ${run.suite}`;
        select.appendChild(option);
      });
      if (previous && Array.from(select.options).some((opt) => opt.value === previous)) {
        select.value = previous;
      }
    });
    renderBaselinePicker("review");
    renderBaselinePicker("signoff");
    setDefaultBaseline("review");
    setDefaultBaseline("signoff");
  }

  function renderBaselinePicker(scope) {
    const runSelect = $(`#${scope}-run-select`);
    const baselineSelect = $(`#${scope}-baseline-select`);
    const previous = baselineSelect.value;
    clear(baselineSelect);
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "No baseline";
    baselineSelect.appendChild(empty);
    state.runs.forEach((run) => {
      if (run.run_id === runSelect.value) return;
      const option = document.createElement("option");
      option.value = run.run_id;
      option.textContent = `${run.run_id} - ${run.suite}`;
      baselineSelect.appendChild(option);
    });
    if (previous && Array.from(baselineSelect.options).some((opt) => opt.value === previous)) {
      baselineSelect.value = previous;
    }
  }

  function setDefaultBaseline(scope) {
    renderBaselinePicker(scope);
    const runSelect = $(`#${scope}-run-select`);
    const baselineSelect = $(`#${scope}-baseline-select`);
    if (!runSelect.value || baselineSelect.value) return;
    const current = state.runs.find((run) => run.run_id === runSelect.value);
    const prior = state.runs.find((run) => (
      run.run_id !== runSelect.value && current && run.suite === current.suite
    ));
    if (prior) baselineSelect.value = prior.run_id;
  }

  function updateTargetFields() {
    const type = targetType();
    $("#provider-fields").classList.toggle("hidden", type !== "provider");
    $("#http-fields").classList.toggle("hidden", type !== "http");
  }

  function targetType() {
    return document.querySelector('input[name="target-type"]:checked').value;
  }

  function buildRunPayload() {
    const suites = Array.from($("#suite-select").selectedOptions).map((opt) => opt.value);
    if (!suites.length) {
      throw new Error("Select at least one suite.");
    }

    const payload = {
      suites,
      target: buildTargetPayload(),
    };
    const limit = $("#run-limit").value.trim();
    const seed = $("#run-seed").value.trim();
    if (limit) payload.limit = Number(limit);
    if (seed) payload.seed = Number(seed);
    return payload;
  }

  function buildTargetPayload() {
    const type = targetType();
    if (type === "mock") {
      return { type: "mock" };
    }
    if (type === "provider") {
      return {
        type: "provider",
        provider: $("#provider-name").value.trim() || "openai",
        model: $("#provider-model").value.trim(),
      };
    }

    const target = {
      type: "http",
      url: $("#http-url").value.trim(),
      method: $("#http-method").value,
      body_template: $("#http-body").value,
      response_path: $("#http-response-path").value.trim(),
    };
    const headers = $("#http-headers").value.trim();
    if (headers) {
      target.headers = JSON.parse(headers);
    }
    return target;
  }

  function showProgress(runId) {
    const panel = $("#progress-panel");
    panel.classList.remove("hidden");
    $("#progress-status").textContent = `Run ${runId}`;
    $("#progress-count").textContent = "queued";
    $("#progress-bar").style.width = "0%";
    $("#progress-case").textContent = "";

    if (state.pollTimer) window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(() => pollProgress(runId), 600);
    pollProgress(runId);
  }

  function showProgressError(message) {
    const panel = $("#progress-panel");
    panel.classList.remove("hidden");
    $("#progress-status").textContent = "Run failed to start";
    $("#progress-count").textContent = "";
    $("#progress-bar").style.width = "0%";
    $("#progress-case").textContent = message;
  }

  async function pollProgress(runId) {
    try {
      const progress = await api(`/api/runs/${encodeURIComponent(runId)}/progress`);
      const total = progress.total || 0;
      const completed = progress.completed || 0;
      const percent = total ? Math.round((completed / total) * 100) : 0;
      $("#progress-status").textContent = progress.status;
      $("#progress-count").textContent = total ? `${completed}/${total}` : "";
      $("#progress-bar").style.width = `${percent}%`;
      $("#progress-case").textContent = progress.current_case_id
        ? `Current case: ${progress.current_case_id}`
        : progress.error || "";

      if (progress.status === "completed" || progress.status === "failed") {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
        await loadRunsAndRender();
        if (progress.status === "completed") {
          await loadRunDetail(runId);
        }
      }
    } catch (err) {
      showProgressError(err.message);
      if (state.pollTimer) window.clearInterval(state.pollTimer);
    }
  }

  async function loadRunDetail(runId) {
    const detail = await api(`/api/runs/${encodeURIComponent(runId)}`);
    state.activeRun = detail;
    state.filters = { status: "all", category: "all" };
    renderRunDetail();
  }

  function renderRunDetail() {
    const root = $("#run-detail");
    root.classList.remove("hidden");
    clear(root);
    const run = state.activeRun;
    if (!run) return;

    const header = node("div", "detail-toolbar");
    const title = node("div");
    title.appendChild(node("h2", "", run.run_id));
    title.appendChild(node("p", "", `${run.suite} - ${run.provider} / ${run.model}`));
    header.appendChild(title);
    header.appendChild(renderFilters(run));
    root.appendChild(header);

    const findings = filteredFindings(run);
    const table = node("table", "findings-table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["Case", "Status", "Severity", "Category", "Score", "Reason"].forEach((label) => {
      headerRow.appendChild(node("th", "", label));
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    findings.forEach((finding) => {
      const testCase = caseForFinding(run, finding);
      const row = document.createElement("tr");
      row.appendChild(node("td", "", `${finding.case_id} - ${testCase ? testCase.name : ""}`));
      row.appendChild(node("td", `status-${finding.status}`, finding.status));
      row.appendChild(node("td", `severity-${finding.severity}`, finding.severity));
      row.appendChild(node("td", "", testCase ? testCase.category : ""));
      row.appendChild(node("td", "", finding.score === null ? "" : finding.score));
      row.appendChild(node("td", "", finding.reason));
      row.addEventListener("click", () => renderDrawer(root, run, finding));
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    root.appendChild(table);

    if (findings.length) {
      renderDrawer(root, run, findings[0]);
    }
  }

  function renderFilters(run) {
    const filters = node("div", "filters");
    const statuses = unique(run.findings.map((finding) => finding.status));
    const categories = unique(run.cases.map((testCase) => testCase.category));

    const statusSelect = filterSelect("status-filter", ["all"].concat(statuses), state.filters.status);
    statusSelect.addEventListener("change", () => {
      state.filters.status = statusSelect.value;
      renderRunDetail();
    });
    const categorySelect = filterSelect("category-filter", ["all"].concat(categories), state.filters.category);
    categorySelect.addEventListener("change", () => {
      state.filters.category = categorySelect.value;
      renderRunDetail();
    });
    filters.append(statusSelect, categorySelect);
    return filters;
  }

  function filterSelect(id, values, selected) {
    const select = document.createElement("select");
    select.id = id;
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = value === selected;
      select.appendChild(option);
    });
    return select;
  }

  function filteredFindings(run) {
    return run.findings.filter((finding) => {
      const testCase = caseForFinding(run, finding);
      const statusOk = state.filters.status === "all" || finding.status === state.filters.status;
      const categoryOk = state.filters.category === "all" ||
        (testCase && testCase.category === state.filters.category);
      return statusOk && categoryOk;
    });
  }

  function renderDrawer(root, run, finding) {
    const old = root.querySelector(".drawer");
    if (old) old.remove();

    const testCase = caseForFinding(run, finding);
    const drawer = node("section", "drawer");
    drawer.appendChild(node("h3", "", testCase ? testCase.name : finding.case_id));

    const grid = node("div", "drawer-grid");
    grid.appendChild(preBlock("Prompt", testCase ? testCase.prompt : ""));
    grid.appendChild(preBlock("Response", finding.response || ""));
    grid.appendChild(preBlock("Expected behavior", testCase ? testCase.expected_behavior : ""));
    grid.appendChild(preBlock("Detector rationale", detectorText(finding)));
    drawer.appendChild(grid);

    if (testCase && transcriptMessages(testCase.extra).length) {
      const transcript = node("div");
      transcript.appendChild(node("h3", "", "Conversation"));
      transcript.appendChild(renderTranscript(testCase.extra));
      drawer.appendChild(transcript);
    }
    root.appendChild(drawer);
  }

  async function loadReviewQueue() {
    const runId = $("#review-run-select").value;
    if (!runId) {
      renderReviewEmpty("No run selected.");
      return;
    }
    const baseline = $("#review-baseline-select").value;
    const query = baseline ? `?baseline=${encodeURIComponent(baseline)}` : "";
    const payload = await api(`/api/review/${encodeURIComponent(runId)}${query}`);
    state.reviewQueue = payload.items || [];
    state.activeReviewIndex = 0;
    state.activeReviewRunId = runId;
    renderReviewQueue();
  }

  function renderReviewEmpty(message) {
    clear($("#review-queue"));
    clear($("#review-detail"));
    $("#review-queue").appendChild(node("div", "empty-state", message));
  }

  function renderReviewQueue() {
    const list = $("#review-queue");
    clear(list);
    if (!state.reviewQueue.length) {
      list.appendChild(node("div", "empty-state", "No NEEDS_REVIEW findings."));
      clear($("#review-detail"));
      $("#review-detail").appendChild(node("div", "empty-state", "Select another run or baseline."));
      return;
    }

    state.reviewQueue.forEach((item, index) => {
      const button = node("button", "review-item");
      button.type = "button";
      button.classList.toggle("active", index === state.activeReviewIndex);
      button.addEventListener("click", () => selectReviewIndex(index));
      const title = node("div", "case-name", `${item.finding_id} - ${item.name}`);
      const meta = node("div", "case-meta", item.category);
      const chip = node("span", `badge severity-${item.severity}`, item.severity);
      button.append(title, meta, chip);
      list.appendChild(button);
    });
    renderReviewDetail();
  }

  function selectReviewIndex(index) {
    if (!state.reviewQueue.length) return;
    state.activeReviewIndex = Math.max(0, Math.min(index, state.reviewQueue.length - 1));
    renderReviewQueue();
  }

  function renderReviewDetail() {
    const root = $("#review-detail");
    clear(root);
    const item = state.reviewQueue[state.activeReviewIndex];
    if (!item) {
      root.appendChild(node("div", "empty-state", "No item selected."));
      return;
    }

    const header = node("div", "detail-toolbar");
    const title = node("div");
    title.appendChild(node("h2", "", item.name));
    title.appendChild(node("p", "", `${item.finding_id} - ${item.status}`));
    const actions = node("div", "action-row");
    actions.appendChild(decisionButton("Approve", "approve"));
    actions.appendChild(decisionButton("Reject", "reject"));
    actions.appendChild(decisionButton("Waive", "waive"));
    header.append(title, actions);
    root.appendChild(header);

    const grid = node("div", "drawer-grid");
    grid.appendChild(preBlock("Prompt", item.case.prompt));
    grid.appendChild(preBlock("Current response", item.finding.response || ""));
    grid.appendChild(preBlock("Expected behavior", item.case.expected_behavior || ""));
    grid.appendChild(preBlock("Detector rationale", item.detector_rationale || item.finding.reason || ""));
    root.appendChild(grid);

    if (item.judge && (item.judge.rationale || item.judge.confidence !== undefined)) {
      const judge = preBlock(
        "Judge assist",
        `${item.judge.suggestion || "suggestion"} confidence=${item.judge.confidence ?? ""}\n${item.judge.rationale || ""}`
      );
      root.appendChild(judge);
    }

    if (item.baseline && item.baseline.response) {
      const compare = node("div", "drawer-grid");
      compare.appendChild(preBlock("Baseline response", item.baseline.response));
      compare.appendChild(preBlock("Current response", item.finding.response || ""));
      root.appendChild(compare);
    }
  }

  function decisionButton(label, decision) {
    const button = node("button", decision === "approve" ? "primary-button" : "secondary-button", label);
    button.type = "button";
    button.addEventListener("click", () => {
      if (decision === "waive") openDecisionModal(decision);
      else submitDecision(decision, "");
    });
    return button;
  }

  function reviewerName() {
    return $("#reviewer-name").value.trim() || "QA Reviewer";
  }

  async function submitDecision(decision, notes, expiresAt) {
    const item = state.reviewQueue[state.activeReviewIndex];
    if (!item) return;
    await api(`/api/review/${encodeURIComponent(state.activeReviewRunId)}/${encodeURIComponent(item.finding_id)}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        reviewer: reviewerName(),
        notes: notes || "",
        expires_at: expiresAt || "",
      }),
    });
    await loadReviewQueue();
  }

  function openDecisionModal(decision) {
    const modal = $("#decision-modal");
    $("#decision-kind").value = decision;
    $("#decision-title").textContent = `${decision[0].toUpperCase()}${decision.slice(1)} finding`;
    $("#decision-reviewer").value = reviewerName();
    $("#decision-notes").value = "";
    $("#decision-expiry").value = "";
    modal.showModal();
  }

  async function submitModalDecision() {
    const decision = $("#decision-kind").value;
    const reviewer = $("#decision-reviewer").value.trim();
    if (reviewer) $("#reviewer-name").value = reviewer;
    await submitDecision(decision, $("#decision-notes").value, $("#decision-expiry").value);
    $("#decision-modal").close();
  }

  function bindKeyboardShortcuts() {
    document.addEventListener("keydown", (event) => {
      if (!$("#view-review").classList.contains("active")) return;
      if ($("#decision-modal").open) return;
      const tag = event.target.tagName.toLowerCase();
      if (["input", "textarea", "select"].includes(tag)) return;
      if (event.key === "j") {
        event.preventDefault();
        selectReviewIndex(state.activeReviewIndex + 1);
      } else if (event.key === "k") {
        event.preventDefault();
        selectReviewIndex(state.activeReviewIndex - 1);
      } else if (event.key === "a") {
        event.preventDefault();
        submitDecision("approve", "");
      } else if (event.key === "r") {
        event.preventDefault();
        submitDecision("reject", "");
      } else if (event.key === "w") {
        event.preventDefault();
        openDecisionModal("waive");
      }
    });
  }

  async function loadGate() {
    const runId = $("#signoff-run-select").value;
    if (!runId) return;
    const baseline = $("#signoff-baseline-select").value;
    const query = baseline ? `?baseline=${encodeURIComponent(baseline)}` : "";
    state.gate = await api(`/api/gate/${encodeURIComponent(runId)}${query}`);
    renderGate();
  }

  function renderGate() {
    const root = $("#gate-panel");
    root.classList.remove("hidden");
    clear(root);
    const gate = state.gate;
    if (!gate) {
      root.appendChild(node("div", "empty-state", "No gate result loaded."));
      return;
    }

    const banner = node("div", `decision-banner decision-${gate.decision.verdict.toLowerCase().replace(/[^a-z]/g, "")}`);
    banner.appendChild(node("h2", "", gate.blocked_by_reviews ? "Review required before sign-off" : gate.decision.verdict));
    banner.appendChild(node("p", "", gate.blocked_by_reviews
      ? `${gate.unresolved_review_count} unresolved review item(s).`
      : `Policy ${gate.policy_version}`));
    if (gate.blocked_by_reviews) {
      const link = node("button", "secondary-button", "Open Review Queue");
      link.type = "button";
      link.addEventListener("click", () => showView("review"));
      banner.appendChild(link);
    }
    root.appendChild(banner);

    root.appendChild(listBlock("Triggering Rules", gate.triggering_policy_rules));
    root.appendChild(listBlock("Policy Source", gate.policy_rules));
    root.appendChild(renderRegressionTable(gate.regressions || []));
    root.appendChild(renderExportButtons());
  }

  function listBlock(title, values) {
    const wrap = node("section", "subsection");
    wrap.appendChild(node("h3", "", title));
    const list = document.createElement("ul");
    (values && values.length ? values : ["None"]).forEach((value) => {
      list.appendChild(node("li", "", value));
    });
    wrap.appendChild(list);
    return wrap;
  }

  function renderRegressionTable(regressions) {
    const wrap = node("section", "subsection");
    wrap.appendChild(node("h3", "", "Regressions"));
    if (!regressions.length) {
      wrap.appendChild(node("div", "empty-state", "No regressions."));
      return wrap;
    }
    const table = node("table", "findings-table");
    const thead = document.createElement("thead");
    const tr = document.createElement("tr");
    ["Type", "Case", "Severity", "Reason"].forEach((label) => tr.appendChild(node("th", "", label)));
    thead.appendChild(tr);
    table.appendChild(thead);
    const tbody = document.createElement("tbody");
    regressions.forEach((regression) => {
      const row = document.createElement("tr");
      row.appendChild(node("td", "", regression.type));
      row.appendChild(node("td", "", regression.case_id));
      row.appendChild(node("td", `severity-${regression.severity || regression.to_severity}`, regression.severity || regression.to_severity));
      row.appendChild(node("td", "", regression.reason || `${regression.from_status} -> ${regression.to_status}`));
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderExportButtons() {
    const wrap = node("section", "subsection");
    wrap.appendChild(node("h3", "", "Export"));
    const row = node("div", "action-row");
    ["html", "markdown", "evidence-pack"].forEach((fmt) => {
      const button = node("button", "secondary-button", fmt);
      button.type = "button";
      button.addEventListener("click", () => exportGate(fmt, wrap));
      row.appendChild(button);
    });
    wrap.appendChild(row);
    return wrap;
  }

  async function exportGate(format, root) {
    const runId = $("#signoff-run-select").value;
    const result = await api(`/api/export/${encodeURIComponent(runId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    });
    let status = root.querySelector(".export-status");
    if (!status) {
      status = node("div", "export-status");
      root.appendChild(status);
    }
    status.textContent = result.file_path;
  }

  function preBlock(label, text) {
    const wrap = node("div");
    wrap.appendChild(node("div", "muted-label", label));
    const pre = document.createElement("pre");
    pre.textContent = text || "";
    wrap.appendChild(pre);
    return wrap;
  }

  function detectorText(finding) {
    const detectors = (finding.extra && finding.extra.detectors) || [];
    if (!detectors.length) {
      return finding.reason || "";
    }
    return detectors.map((detector) => {
      const matches = detector.matches && detector.matches.length
        ? ` matches=${detector.matches.join(", ")}`
        : "";
      return `${detector.name}: triggered=${Boolean(detector.triggered)}${matches} ${detector.notes || ""}`.trim();
    }).join("\n");
  }

  function renderTranscript(extra) {
    const wrap = node("div", "transcript");
    transcriptMessages(extra).forEach((message) => {
      const item = node("div", "message");
      item.appendChild(node("div", "message-role", message.role || "message"));
      item.appendChild(node("div", "", message.content || message.text || ""));
      wrap.appendChild(item);
    });
    return wrap;
  }

  function transcriptMessages(extra) {
    if (!extra || typeof extra !== "object") return [];
    const candidate = extra.conversation || extra.transcript || extra.messages;
    if (!Array.isArray(candidate)) return [];
    return candidate.filter((item) => item && typeof item === "object");
  }

  function caseForFinding(run, finding) {
    return run.cases.find((testCase) => testCase.case_id === finding.case_id);
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean))).sort();
  }

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((err) => {
      const main = $(".main");
      const error = node("div", "error-state", err.message);
      main.prepend(error);
    });
  });
})();
