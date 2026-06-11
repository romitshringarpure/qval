(function () {
  "use strict";

  const state = {
    suites: [],
    runs: [],
    selectedSuites: new Set(),
    activeRun: null,
    selectedFindingId: null,
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

  function fmtDate(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  }

  function fmtSuiteName(name) {
    return String(name).replaceAll("_", " ");
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
    renderSuitePicker();
    updateRunSelectedLabel();
    renderRuns();
    renderRunPickers();
    bindKeyboardShortcuts();
  }

  /* ---------- navigation ---------- */

  function bindNavigation() {
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.addEventListener("click", () => showView(button.dataset.view));
    });
  }

  function showView(view) {
    document.querySelectorAll(".nav-button").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
    document.querySelectorAll(".view").forEach((section) => {
      section.classList.toggle("active", section.id === `view-${view}`);
    });
    // Make the workflow flow: entering a view loads what it needs.
    if (view === "review" && $("#review-run-select").value && !state.reviewQueue.length) {
      loadReviewQueue().catch(showTopError);
    }
    if (view === "signoff" && $("#signoff-run-select").value) {
      loadGate().catch(showTopError);
    }
  }

  function showTopError(err) {
    const main = $(".main");
    const existing = main.querySelector(".error-state");
    if (existing) existing.remove();
    main.prepend(node("div", "error-state", err.message || String(err)));
  }

  function bindActions() {
    $("#refresh-runs").addEventListener("click", loadRunsAndRender);
    $("#run-selected").addEventListener("click", () => {
      renderSuitePicker();
      showView("runs");
    });
    $("#refresh-review").addEventListener("click", () => loadReviewQueue().catch(showTopError));
    $("#review-run-select").addEventListener("change", () => {
      setDefaultBaseline("review");
      loadReviewQueue().catch(showTopError);
    });
    $("#review-baseline-select").addEventListener("change", () => loadReviewQueue().catch(showTopError));
    $("#evaluate-gate").addEventListener("click", () => loadGate().catch(showTopError));
    $("#signoff-run-select").addEventListener("change", () => {
      setDefaultBaseline("signoff");
      loadGate().catch(showTopError);
    });
    $("#signoff-baseline-select").addEventListener("change", () => loadGate().catch(showTopError));
    $("#submit-decision").addEventListener("click", submitModalDecision);
  }

  /* ---------- data loading ---------- */

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

  /* ---------- suite library ---------- */

  function toggleSuite(name, checked) {
    if (checked) state.selectedSuites.add(name);
    else state.selectedSuites.delete(name);
    renderSuites();
    renderSuitePicker();
    updateRunSelectedLabel();
  }

  function updateRunSelectedLabel() {
    const count = state.selectedSuites.size;
    $("#run-selected").textContent = count ? `Run selected (${count})` : "Run selected";
    $("#run-selected").disabled = !count;
  }

  function renderSuites() {
    const root = $("#suite-list");
    clear(root);
    if (!state.suites.length) {
      const empty = node("div", "empty-state");
      empty.appendChild(node("strong", "", "No suites found."));
      empty.appendChild(node("span", "", "Add *_tests.json files to your project's test_cases/ folder, or run qval init for starter suites."));
      root.appendChild(empty);
      return;
    }

    state.suites.forEach((suite) => {
      const card = node("article", "suite-card");

      const header = node("div", "suite-card-header");
      const title = node("label", "suite-title");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selectedSuites.has(suite.name);
      checkbox.addEventListener("change", () => toggleSuite(suite.name, checkbox.checked));
      title.append(checkbox, node("h3", "", fmtSuiteName(suite.name)));
      header.append(title, node("span", "count-chip", `${suite.case_count} cases`));
      card.appendChild(header);

      const sevCounts = {};
      suite.cases.forEach((testCase) => {
        sevCounts[testCase.severity] = (sevCounts[testCase.severity] || 0) + 1;
      });
      const badges = node("div", "badge-row");
      ["critical", "high", "medium", "low"].forEach((severity) => {
        if (sevCounts[severity]) {
          badges.appendChild(node("span", `chip sev-${severity}`, `${sevCounts[severity]} ${severity}`));
        }
      });
      suite.control_mappings.slice(0, 4).forEach((control) => {
        badges.appendChild(node("span", "chip chip-outline", control.control_id));
      });
      if (suite.control_mappings.length > 4) {
        badges.appendChild(node("span", "chip chip-outline", `+${suite.control_mappings.length - 4} controls`));
      }
      card.appendChild(badges);

      const details = document.createElement("details");
      const summary = node("summary", "", `View cases (${suite.cases.length})`);
      details.appendChild(summary);
      const cases = node("div", "case-list");
      let rendered = false;
      details.addEventListener("toggle", () => {
        if (!details.open || rendered) return;
        rendered = true;
        suite.cases.forEach((testCase) => cases.appendChild(renderSuiteCase(testCase)));
      });
      details.appendChild(cases);
      card.appendChild(details);

      root.appendChild(card);
    });
  }

  function renderSuiteCase(testCase) {
    const row = node("div", "case-row");
    row.appendChild(node("div", "case-name", `${testCase.id} — ${testCase.name}`));
    row.appendChild(node("div", "case-meta", testCase.description));
    const badges = node("div", "badge-row");
    badges.appendChild(node("span", `chip sev-${testCase.severity}`, testCase.severity));
    badges.appendChild(node("span", "chip chip-outline", testCase.category));
    testCase.control_ids.forEach((controlId) => {
      badges.appendChild(node("span", "chip chip-outline", controlId));
    });
    row.appendChild(badges);
    return row;
  }

  /* ---------- run form ---------- */

  function renderSuitePicker() {
    const root = $("#suite-picker");
    clear(root);
    state.suites.forEach((suite) => {
      const pill = node("label", "suite-pill");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selectedSuites.has(suite.name);
      pill.classList.toggle("checked", checkbox.checked);
      checkbox.addEventListener("change", () => {
        toggleSuite(suite.name, checkbox.checked);
      });
      pill.append(checkbox, node("span", "", fmtSuiteName(suite.name)));
      root.appendChild(pill);
    });
  }

  const TARGET_HINTS = {
    mock: "Offline mock provider — deterministic, no API key needed.",
    provider: "Calls the model API. The key is read from your environment (.env).",
    http: "Tests any HTTP service that wraps an AI — your internal chatbot, an API, a gateway.",
  };

  function bindTargetControls() {
    document.querySelectorAll('input[name="target-type"]').forEach((input) => {
      input.addEventListener("change", updateTargetFields);
    });
    updateTargetFields();
  }

  function updateTargetFields() {
    const type = targetType();
    $("#provider-fields").classList.toggle("hidden", type !== "provider");
    $("#http-fields").classList.toggle("hidden", type !== "http");
    $("#target-hint").textContent = TARGET_HINTS[type] || "";
    document.querySelectorAll("#target-segment label").forEach((label) => {
      const input = label.querySelector("input");
      label.classList.toggle("checked", input && input.checked);
    });
  }

  function targetType() {
    return document.querySelector('input[name="target-type"]:checked').value;
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

  function buildRunPayload() {
    const suites = Array.from(state.selectedSuites);
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

  /* ---------- progress ---------- */

  function showProgress(runId) {
    const panel = $("#progress-panel");
    panel.classList.remove("hidden");
    $("#progress-status").textContent = "Starting…";
    $("#progress-count").textContent = "";
    $("#progress-bar").style.width = "0%";
    $("#progress-case").textContent = runId;

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
      const statusLabel = {
        queued: "Queued",
        running: "Running…",
        completed: "Completed",
        failed: "Failed",
      }[progress.status] || progress.status;
      $("#progress-status").textContent = statusLabel;
      $("#progress-count").textContent = total ? `${completed} / ${total}` : "";
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

  /* ---------- run history ---------- */

  function statbar(pass, review, fail, total) {
    const bar = node("div", "statbar");
    const denominator = total || pass + review + fail || 1;
    [["sb-pass", pass], ["sb-rev", review], ["sb-fail", fail]].forEach(([cls, count]) => {
      if (!count) return;
      const span = node("span", cls);
      span.style.width = `${(count / denominator) * 100}%`;
      bar.appendChild(span);
    });
    return bar;
  }

  function renderRuns() {
    const root = $("#run-history");
    clear(root);
    if (!state.runs.length) {
      const empty = node("div", "empty-state");
      empty.appendChild(node("strong", "", "No runs yet."));
      empty.appendChild(node("span", "", "Pick your suites, keep the Mock target, and press Start run — it works offline, no API key needed."));
      root.appendChild(empty);
      return;
    }
    state.runs.forEach((run) => {
      const button = node("button", "run-row");
      button.type = "button";
      button.addEventListener("click", () => loadRunDetail(run.run_id).catch(showTopError));

      const top = node("div", "run-row-top");
      top.appendChild(node("span", "run-id", run.run_id));
      top.appendChild(node("span", "run-date", fmtDate(run.started_at || run.completed_at)));
      button.appendChild(top);

      button.appendChild(node("div", "run-meta",
        `${fmtSuiteName(run.suite)} · ${run.provider}${run.model ? ` / ${run.model}` : ""}`));

      const bottom = node("div", "run-row-bottom");
      bottom.appendChild(statbar(run.pass_count, run.needs_review_count, run.fail_count, run.total_tests));
      const rate = node("span", "run-rate", `${Math.round((run.pass_rate || 0) * 100)}%`);
      bottom.appendChild(rate);
      button.appendChild(bottom);

      button.appendChild(node("div", "run-counts",
        `${run.total_tests} tests · ${run.pass_count} passed · ${run.fail_count} failed · ${run.needs_review_count} need review`));

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
        option.textContent = `${run.run_id} — ${fmtSuiteName(run.suite)}`;
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
      option.textContent = `${run.run_id} — ${fmtSuiteName(run.suite)}`;
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

  /* ---------- run detail ---------- */

  async function loadRunDetail(runId) {
    const detail = await api(`/api/runs/${encodeURIComponent(runId)}`);
    state.activeRun = detail;
    state.selectedFindingId = null;
    state.filters = { status: "all", category: "all" };
    renderRunDetail();
    $("#run-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderRunDetail() {
    const root = $("#run-detail");
    root.classList.remove("hidden");
    clear(root);
    const run = state.activeRun;
    if (!run) return;

    const header = node("div", "detail-toolbar");
    const title = node("div");
    title.appendChild(node("h3", "", run.run_id));
    title.appendChild(node("p", "", `${fmtSuiteName(run.suite)} · ${run.provider}${run.model ? ` / ${run.model}` : ""}`));
    header.appendChild(title);
    header.appendChild(renderFilters(run));
    root.appendChild(header);

    const counts = { passed: 0, failed: 0, needs_review: 0 };
    run.findings.forEach((finding) => {
      if (finding.status in counts) counts[finding.status] += 1;
    });
    const barWrap = node("div");
    barWrap.style.marginTop = "12px";
    barWrap.appendChild(statbar(counts.passed, counts.needs_review, counts.failed, run.findings.length));
    const legend = node("div", "stat-legend");
    [["#22c55e", `${counts.passed} passed`], ["#8b5cf6", `${counts.needs_review} need review`], ["#ef4444", `${counts.failed} failed`]].forEach(([color, label]) => {
      const item = node("span");
      const swatch = node("i");
      swatch.style.background = color;
      item.append(swatch, document.createTextNode(label));
      legend.appendChild(item);
    });
    barWrap.appendChild(legend);
    root.appendChild(barWrap);

    const findings = filteredFindings(run);
    const table = node("table", "findings-table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    ["Case", "Status", "Severity", "Category", "Reason"].forEach((label) => {
      headerRow.appendChild(node("th", "", label));
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    findings.forEach((finding) => {
      const testCase = caseForFinding(run, finding);
      const row = document.createElement("tr");
      row.classList.toggle("selected", finding.finding_id === state.selectedFindingId);
      const caseCell = node("td");
      caseCell.appendChild(node("div", "case-name", finding.case_id));
      if (testCase) caseCell.appendChild(node("div", "case-meta", testCase.name));
      row.appendChild(caseCell);
      const statusCell = node("td");
      statusCell.appendChild(node("span", `chip st-${finding.status}`, finding.status.replace("_", " ")));
      row.appendChild(statusCell);
      const severityCell = node("td");
      severityCell.appendChild(node("span", `chip sev-${finding.severity}`, finding.severity));
      row.appendChild(severityCell);
      row.appendChild(node("td", "", testCase ? testCase.category : ""));
      row.appendChild(node("td", "", finding.reason));
      row.addEventListener("click", () => {
        state.selectedFindingId = finding.finding_id;
        renderRunDetail();
      });
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    root.appendChild(table);

    const selected = findings.find((finding) => finding.finding_id === state.selectedFindingId) || findings[0];
    if (selected) {
      renderDrawer(root, run, selected);
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
      option.textContent = value === "all" ? "All" : value.replace("_", " ");
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
    const head = node("div", "detail-toolbar");
    head.appendChild(node("h3", "", testCase ? `${finding.case_id} — ${testCase.name}` : finding.case_id));
    const chips = node("div", "badge-row");
    chips.appendChild(node("span", `chip st-${finding.status}`, finding.status.replace("_", " ")));
    chips.appendChild(node("span", `chip sev-${finding.severity}`, finding.severity));
    head.appendChild(chips);
    drawer.appendChild(head);

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

  /* ---------- review queue ---------- */

  async function loadReviewQueue() {
    const runId = $("#review-run-select").value;
    if (!runId) {
      renderReviewEmpty("Run a suite first — findings that need human judgment will queue here.");
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
    $("#review-count").textContent = "";
    $("#review-queue").appendChild(node("div", "empty-state", message));
  }

  function renderReviewQueue() {
    const list = $("#review-queue");
    clear(list);
    $("#review-count").textContent = state.reviewQueue.length
      ? `${state.reviewQueue.length} to review`
      : "";
    if (!state.reviewQueue.length) {
      const empty = node("div", "empty-state");
      empty.appendChild(node("strong", "", "Queue clear."));
      empty.appendChild(node("span", "", "No NEEDS_REVIEW findings in this run — head to Sign-off for the gate decision."));
      list.appendChild(empty);
      clear($("#review-detail"));
      $("#review-detail").appendChild(node("div", "empty-state", "Nothing to adjudicate."));
      return;
    }

    state.reviewQueue.forEach((item, index) => {
      const button = node("button", "review-item");
      button.type = "button";
      button.classList.toggle("active", index === state.activeReviewIndex);
      button.addEventListener("click", () => selectReviewIndex(index));
      const top = node("div", "review-item-top");
      top.appendChild(node("span", "case-name", item.finding_id));
      top.appendChild(node("span", `chip sev-${item.severity}`, item.severity));
      button.appendChild(top);
      button.appendChild(node("div", "case-meta", `${item.name} · ${item.category}`));
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
    title.appendChild(node("h3", "", item.name));
    const meta = node("div", "badge-row");
    meta.appendChild(node("span", "chip chip-outline", item.finding_id));
    meta.appendChild(node("span", `chip sev-${item.severity}`, item.severity));
    meta.appendChild(node("span", `chip st-${item.status}`, String(item.status).replace("_", " ")));
    title.appendChild(meta);
    const actions = node("div", "action-row");
    actions.appendChild(decisionButton("Approve", "approve", "primary-button"));
    actions.appendChild(decisionButton("Reject", "reject", "danger-button"));
    actions.appendChild(decisionButton("Waive…", "waive", "warn-button"));
    header.append(title, actions);
    root.appendChild(header);

    const grid = node("div", "drawer-grid");
    grid.appendChild(preBlock("Prompt", item.case.prompt));
    grid.appendChild(preBlock("Current response", item.finding.response || ""));
    grid.appendChild(preBlock("Expected behavior", item.case.expected_behavior || ""));
    grid.appendChild(preBlock("Detector rationale", item.detector_rationale || item.finding.reason || ""));
    root.appendChild(grid);

    if (item.judge && (item.judge.rationale || item.judge.confidence !== undefined)) {
      const judge = node("div", "judge-block");
      judge.appendChild(node("div", "muted-label", "Judge assist (advisory — your call is final)"));
      const suggestion = node("div", "case-name",
        `Suggests: ${item.judge.suggestion || "—"}${item.judge.confidence !== undefined ? ` · confidence ${item.judge.confidence}` : ""}`);
      suggestion.style.marginTop = "6px";
      judge.appendChild(suggestion);
      if (item.judge.rationale) {
        judge.appendChild(node("div", "case-meta", item.judge.rationale));
      }
      root.appendChild(judge);
    }

    if (item.baseline && item.baseline.response) {
      const compareTitle = node("h3", "", "Baseline comparison");
      compareTitle.style.marginTop = "14px";
      root.appendChild(compareTitle);
      const compare = node("div", "drawer-grid");
      compare.appendChild(preBlock("Baseline response", item.baseline.response));
      compare.appendChild(preBlock("Current response", item.finding.response || ""));
      root.appendChild(compare);
    }
  }

  function decisionButton(label, decision, cls) {
    const button = node("button", cls, label);
    button.type = "button";
    button.addEventListener("click", () => {
      if (decision === "waive") openDecisionModal(decision);
      else submitDecision(decision, "").catch(showTopError);
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
    $("#decision-title").textContent = decision === "waive"
      ? "Waive finding (ship with documented exception)"
      : `${decision[0].toUpperCase()}${decision.slice(1)} finding`;
    $("#decision-reviewer").value = reviewerName();
    $("#decision-notes").value = "";
    $("#decision-expiry").value = "";
    $("#decision-expiry-wrap").classList.toggle("hidden", decision !== "waive");
    modal.showModal();
  }

  async function submitModalDecision() {
    const decision = $("#decision-kind").value;
    const reviewer = $("#decision-reviewer").value.trim();
    if (reviewer) $("#reviewer-name").value = reviewer;
    try {
      await submitDecision(decision, $("#decision-notes").value, $("#decision-expiry").value);
      $("#decision-modal").close();
    } catch (err) {
      showTopError(err);
    }
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
        submitDecision("approve", "").catch(showTopError);
      } else if (event.key === "r") {
        event.preventDefault();
        submitDecision("reject", "").catch(showTopError);
      } else if (event.key === "w") {
        event.preventDefault();
        openDecisionModal("waive");
      }
    });
  }

  /* ---------- sign-off ---------- */

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

    let banner;
    if (gate.blocked_by_reviews) {
      banner = node("div", "decision-banner decision-review");
      const text = node("div");
      text.appendChild(node("div", "verdict-word", "Review required"));
      text.appendChild(node("p", "", `${gate.unresolved_review_count} finding(s) need a human decision before this release can be signed off.`));
      banner.appendChild(text);
      const link = node("button", "secondary-button spacer", "Open Review Queue");
      link.type = "button";
      link.addEventListener("click", () => showView("review"));
      banner.appendChild(link);
    } else {
      const verdict = gate.decision.verdict;
      banner = node("div", `decision-banner decision-${verdict.toLowerCase().replace(/[^a-z]/g, "")}`);
      const text = node("div");
      text.appendChild(node("div", "verdict-word", verdict));
      text.appendChild(node("p", "", `Evaluated against policy ${gate.policy_version}`));
      banner.appendChild(text);
    }
    root.appendChild(banner);

    root.appendChild(listBlock("Why", gate.triggering_policy_rules, "No policy rules were triggered."));
    root.appendChild(listBlock("Policy rules evaluated", gate.policy_rules, "No rules in policy."));
    root.appendChild(renderRegressionTable(gate.regressions || []));
    root.appendChild(renderExportButtons());
  }

  function listBlock(title, values, emptyText) {
    const wrap = node("section", "subsection");
    wrap.appendChild(node("h3", "", title));
    if (!values || !values.length) {
      wrap.appendChild(node("div", "case-meta", emptyText || "None"));
      return wrap;
    }
    const list = document.createElement("ul");
    values.forEach((value) => {
      list.appendChild(node("li", "", value));
    });
    wrap.appendChild(list);
    return wrap;
  }

  function renderRegressionTable(regressions) {
    const wrap = node("section", "subsection");
    wrap.appendChild(node("h3", "", "Regressions vs baseline"));
    if (!regressions.length) {
      wrap.appendChild(node("div", "case-meta", "No regressions against the selected baseline."));
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
      const severity = regression.severity || regression.to_severity;
      const sevCell = node("td");
      sevCell.appendChild(node("span", `chip sev-${severity}`, severity));
      row.appendChild(sevCell);
      row.appendChild(node("td", "", regression.reason || `${regression.from_status} → ${regression.to_status}`));
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
    [["HTML report", "html"], ["Markdown report", "markdown"], ["Evidence pack", "evidence-pack"]].forEach(([label, fmt]) => {
      const button = node("button", "secondary-button", label);
      button.type = "button";
      button.addEventListener("click", () => exportGate(fmt, wrap).catch(showTopError));
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

  /* ---------- shared bits ---------- */

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
    init().catch(showTopError);
  });
})();
