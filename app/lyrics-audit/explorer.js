const state = { catalog: null, data: null, filter: "all", query: "", selected: null, selectedDecision: null, comparisonDimension: "normalization", baselineRunId: null, candidateRunId: null, showIds: false, requestId: 0 };

const COMPARISON_DIMENSIONS = [
  { id: "normalization", label: "Normalization & elision", description: "Compare the observed or normalized form produced for the same token occurrence." },
  { id: "routing", label: "Word routing", description: "Compare proper-name, noise, vocabulary, foreign-word, and review routing decisions." },
  { id: "wsd", label: "Sense assignment", description: "Compare the selected dictionary analysis and sense for the same occurrence." },
  { id: "consolidation", label: "Card inclusion", description: "Compare whether the occurrence became a study example and card." },
];

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const shortId = (value) => value ? `${value.slice(0, 8)}…` : "not preserved";

function resolvedRoutes(clean) {
  return (clean?.routes || []).map((route) => {
    const profile = route.profile_id ? state.data.routing_profiles?.[route.profile_id] : null;
    return profile ? { ...profile.decision, route_id: route.route_id, analysis_unit_id: route.analysis_unit_id } : route;
  });
}

function resolvedComparisons(clean) {
  return (clean?.routes || []).map((route) => state.data.routing_profiles?.[route.profile_id]?.comparison).filter(Boolean);
}

function resolvedLexical(clean) {
  return (clean?.lexical_candidates || []).map((candidate) => {
    const profile = candidate.profile_id ? state.data.lexical_profiles?.[candidate.profile_id] : null;
    return profile ? { ...profile, lexical_candidate_id: candidate.lexical_candidate_id, analysis_unit_id: candidate.analysis_unit_id } : candidate;
  });
}

function resolvedWsd(clean) {
  return (clean?.wsd_results || []).map((reference) => {
    const profile = state.data.wsd_result_profiles?.[reference.result_id];
    return profile ? { ...profile, result_id: reference.result_id, analysis_unit_id: reference.analysis_unit_id } : reference;
  });
}

function wsdAssignmentEvidence(clean, result) {
  if (!result || result.status !== "assigned") return { kind: "unassigned", optionCount: 0 };
  const lexical = resolvedLexical(clean).find((candidate) =>
    (candidate.analyses || []).some((analysis) => analysis.menu_analysis_id === result.menu_analysis_id)
  );
  const optionCount = (lexical?.analyses || []).reduce(
    (count, analysis) => count + (analysis.senses || []).length,
    0,
  );
  return {
    kind: optionCount === 1 ? "automatic" : "disambiguated",
    optionCount,
  };
}

function resolvedConsolidation(clean) {
  return (clean?.consolidations || []).map((reference) => ({
    ...reference,
    disposition: state.data.consolidation_dispositions?.[reference.disposition_id],
    example: reference.example_id ? state.data.consolidated_examples?.[reference.example_id] : null,
    card: reference.card_id ? state.data.consolidated_cards?.[reference.card_id] : null,
  }));
}

function runsForDimension(dimensionId = state.comparisonDimension) {
  return (state.data?.runs || []).filter((run) => (run.dimensions || ["normalization"]).includes(dimensionId));
}

function selectedComparisonRuns() {
  const available = runsForDimension("normalization");
  const baseline = available.find((run) => run.run_id === state.baselineRunId) || available.find((run) => run.role === "baseline") || available[0] || {};
  const candidate = available.find((run) => run.run_id === state.candidateRunId) || available.find((run) => run.role === "candidate") || available[1] || baseline;
  return [baseline, candidate];
}

function runOptionLabel(run) {
  return run.short_label || run.label || run.method_id || run.run_id;
}

function renderComparisonControls() {
  const dimension = COMPARISON_DIMENSIONS.find((item) => item.id === state.comparisonDimension) || COMPARISON_DIMENSIONS[0];
  const available = runsForDimension(dimension.id);
  const baselineSelect = $("comparisonBaseline");
  const candidateSelect = $("comparisonCandidate");
  $("comparisonDimension").innerHTML = COMPARISON_DIMENSIONS.map((item) => {
    const count = runsForDimension(item.id).length;
    return `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)} · ${count} run${count === 1 ? "" : "s"}</option>`;
  }).join("");
  $("comparisonDimension").value = dimension.id;
  const options = available.map((run) => `<option value="${escapeHtml(run.run_id)}">${escapeHtml(runOptionLabel(run))}</option>`).join("");
  baselineSelect.innerHTML = options || `<option>No preserved run</option>`;
  candidateSelect.innerHTML = options || `<option>No preserved run</option>`;
  baselineSelect.disabled = available.length < 2;
  candidateSelect.disabled = available.length < 2;
  if (available.length >= 2) {
    if (!available.some((run) => run.run_id === state.baselineRunId)) state.baselineRunId = available.find((run) => run.role === "baseline")?.run_id || available[0].run_id;
    if (!available.some((run) => run.run_id === state.candidateRunId)) state.candidateRunId = available.find((run) => run.role === "candidate")?.run_id || available[1].run_id;
    baselineSelect.value = state.baselineRunId;
    candidateSelect.value = state.candidateRunId;
  }
  const baseline = available.find((run) => run.run_id === state.baselineRunId);
  const candidate = available.find((run) => run.run_id === state.candidateRunId);
  $("comparisonSummary").textContent = available.length >= 2
    ? `${dimension.label}: ${runOptionLabel(baseline)} → ${runOptionLabel(candidate)}`
    : `${dimension.label}: history only`;
  $("comparisonSummaryDetail").textContent = "Choose runs and comparison dimension";
  $("comparisonDescription").textContent = dimension.description;
  $("comparisonAvailability").innerHTML = available.length >= 2
    ? `<strong>${available.length} comparable runs preserved.</strong> Choose the older and newer snapshots below.`
    : `<strong>No run pair is preserved for this dimension.</strong> Individual word histories still show the ${available.length || "current"} observation available; nothing is inferred.`;
  $("comparisonRunDetails").innerHTML = available.length ? available.map((run) => `<article class="comparison-run-detail">
    <span>${escapeHtml(run.role || "preserved run")}</span>
    <strong>${escapeHtml(run.label)}</strong>
    <p>${escapeHtml(run.description || "No human-readable description was preserved for this run.")}</p>
    <code>${escapeHtml(run.method_id || run.run_id)}</code>
    <small>${escapeHtml(run.run_id)}</small>
  </article>`).join("") : `<div class="no-evidence">Future runs that declare <code>${escapeHtml(dimension.id)}</code> support will appear here automatically.</div>`;
}

function likelyAssignments(assignments, token) {
  const normalized = (token.clean_processing?.normalized_form || Object.values(token.states || {}).at(-1)?.normalized_form)?.toLocaleLowerCase();
  return assignments.filter((item) => [item.word, item.lemma].filter(Boolean).some((value) => value.toLocaleLowerCase() === normalized));
}

function classificationDecisions(token, line) {
  const clean = token.clean_processing;
  const routes = resolvedRoutes(clean);
  const comparisons = resolvedComparisons(clean);
  const lexical = resolvedLexical(clean);
  const wsd = resolvedWsd(clean);
  const consolidations = resolvedConsolidation(clean);
  const assignments = likelyAssignments(line.app_assignments, token);
  const currentRun = clean ? { label: "Clean recomputation", run_id: clean.occurrence_id } : null;
  const decisions = [];
  const push = (decision) => decisions.push({ status: decision.history.at(-1)?.value || "No record", ...decision });

  const normalizationHistory = state.data.runs.map((run) => {
    const snapshot = token.states[run.run_id] || {};
    return {
      run: run.label,
      run_id: run.run_id,
      value: snapshot.normalized_form || "not preserved",
      detail: snapshot.method_id || "Method was not preserved in this snapshot.",
      provenance: snapshot.claim_id || snapshot.input_fingerprint,
    };
  });
  if (clean) normalizationHistory.push({
    run: currentRun.label,
    run_id: currentRun.run_id,
    value: clean.normalized_form,
    detail: clean.normalizer_method,
    provenance: clean.occurrence_id,
  });
  push({ id: "normalization", label: "Normalization", history: normalizationHistory });

  if (clean?.units?.length) clean.units.forEach((unit, index) => {
    const isElision = unit.operation === "restore" || String(unit.reason_code || "").includes("elision");
    push({
      id: `transform-${index}`,
      label: isElision ? "Elision restoration" : "Token transform",
      history: [{
        run: currentRun.label,
        run_id: currentRun.run_id,
        value: `${unit.operation}: ${unit.normalized_form}`,
        detail: unit.reason_code,
        provenance: unit.analysis_unit_id,
      }],
    });
  });
  else push({ id: "transform", label: "Token transform", history: [] });

  const routeHistory = [];
  if (comparisons[0]?.baseline) routeHistory.push({
    run: "Legacy routing snapshot",
    run_id: comparisons[0].baseline.run_id || "legacy snapshot",
    value: comparisons[0].baseline.bucket,
    detail: "Only the resulting bucket was preserved; its earlier rule trace is unavailable.",
  });
  if (routes[0]) routeHistory.push({
    run: currentRun?.label || "Current snapshot",
    run_id: currentRun?.run_id || routes[0].route_id,
    value: `${routes[0].status}: ${routes[0].bucket}`,
    detail: (routes[0].reason_codes || []).join(" + ") || "No reason code recorded.",
    provenance: routes[0].route_id,
  });
  if (!routeHistory.length && token.current_route) routeHistory.push({
    run: "Current audit snapshot",
    run_id: token.occurrence_id,
    value: `${token.current_route.status}: ${token.current_route.label}`,
    detail: token.current_route.evidence_kind || "No evidence kind recorded.",
  });
  push({ id: "routing", label: "Word routing", history: routeHistory });

  (routes[0]?.policy_trace || []).forEach((policy, index) => push({
    id: `route-policy-${index}`,
    label: `Rule · ${policy.policy_id}`,
    history: [{
      run: currentRun?.label || "Current snapshot",
      run_id: currentRun?.run_id || routes[0].route_id,
      value: policy.outcome,
      detail: `${policy.inputs?.join(" + ") || "no external input"} · ${JSON.stringify(policy.evidence || {})}`,
      provenance: routes[0].route_id,
    }],
  }));

  if (lexical.length) lexical.forEach((candidate, index) => push({
    id: `lexical-${index}`,
    label: "Lexical menu",
    history: [{
      run: currentRun?.label || "Current snapshot",
      run_id: currentRun?.run_id || candidate.lexical_candidate_id,
      value: candidate.status === "ready" ? `${candidate.lookup_form}: ${(candidate.analyses || []).length} analyses` : candidate.status,
      detail: (candidate.reason_codes || []).join(" + ") || `${candidate.provider?.source_adapter || "unknown provider"} lookup`,
      provenance: candidate.lexical_candidate_id,
    }],
  }));
  else push({ id: "lexical", label: "Lexical menu", history: [] });

  if (wsd.length) wsd.forEach((result, index) => {
    const assignment = wsdAssignmentEvidence(clean, result);
    const label = assignment.kind === "automatic" ? "Automatic sense assignment" : "WSD sense assignment";
    push({
      id: `wsd-${index}`,
      label: result.status === "assigned" ? label : "Sense assignment",
      history: [{
        run: currentRun?.label || "Current snapshot",
        run_id: currentRun?.run_id || result.result_id,
        value: result.status === "assigned" ? `${result.selected_tuple?.headword || "headword unavailable"} → ${result.selected_sense_id}` : result.status,
        detail: result.status === "assigned"
          ? assignment.kind === "automatic"
            ? "Automatic assignment: the exact lexical menu contained one sense, so no ambiguity had to be resolved."
            : `WSD chose among ${assignment.optionCount || "multiple"} menu senses · confidence ${Number(result.confidence).toFixed(4)} · ${(result.decision_path || []).join(" → ")}`
          : (result.evidence?.reason_codes || []).join(" + ") || "No sense assigned.",
        provenance: result.result_id,
      }],
    });
  });
  else if (clean?.wsd_requests?.length) clean.wsd_requests.forEach((request, index) => push({
    id: `wsd-request-${index}`,
    label: "WSD eligibility",
    history: [{
      run: currentRun?.label || "Current snapshot",
      run_id: currentRun?.run_id || request.request_id,
      value: `${request.eligibility}: ${request.execution_status}`,
      detail: request.translation_available ? "Aligned translation available." : "Source context only.",
      provenance: request.request_id,
    }],
  }));
  else push({ id: "wsd", label: "Sense assignment", history: [] });

  if (consolidations.length) consolidations.forEach(({ disposition, example, card }, index) => push({
    id: `consolidation-${index}`,
    label: "Card inclusion",
    history: disposition ? [{
      run: currentRun?.label || "Current snapshot",
      run_id: currentRun?.run_id || disposition.disposition_id,
      value: disposition.study_status,
      detail: `${disposition.route_bucket}${example?.selection_reason ? ` · ${example.selection_reason}` : ""}${card?.display_form ? ` · card ${card.display_form}` : ""}`,
      provenance: disposition.disposition_id,
    }] : [],
  }));
  else push({ id: "consolidation", label: "Card inclusion", history: [] });

  push({
    id: "release",
    label: "App assignment",
    history: assignments.map((assignment) => ({
      run: "Retained Artist release",
      run_id: assignment.prompt_id || "release snapshot",
      value: `${assignment.word} → ${assignment.sense?.translation || `sense ${Number(assignment.sense_index) + 1}`}`,
      detail: assignment.assignment_method || "Assignment method not recorded.",
      provenance: assignment.prompt_id,
    })),
  });
  return decisions;
}

function decisionHistoryHtml(decision) {
  if (!decision) return "";
  if (!decision.history.length) return `<div class="decision-history-empty"><strong>No classification record preserved</strong><p>This stage is visible so absence cannot be mistaken for a successful decision. A future run can add history here without changing the auditor.</p></div>`;
  const entries = decision.history.map((entry, index) => {
    const previous = decision.history[index - 1];
    const changed = previous && previous.value !== entry.value;
    return `<article class="history-entry ${changed ? "changed" : ""}">
      <div class="history-marker"></div>
      <div class="history-entry-body">
        <div class="history-run"><strong>${escapeHtml(entry.run)}</strong><span>${changed ? "changed" : index ? "unchanged" : "first preserved"}</span></div>
        <div class="history-value">${escapeHtml(entry.value)}</div>
        <p>${escapeHtml(entry.detail || "No additional decision evidence was preserved.")}</p>
        <code>${escapeHtml(entry.provenance || entry.run_id || "provenance not preserved")}</code>
      </div>
    </article>`;
  }).join("");
  const boundary = decision.history.length === 1
    ? `<p class="history-boundary">This is the only preserved observation for this classification. No earlier history is available.</p>`
    : `<p class="history-boundary">Showing all ${decision.history.length} preserved observations. Changes are highlighted.</p>`;
  return `${boundary}<div class="history-timeline">${entries}</div>`;
}

function renderDecisionInspector(decisions) {
  const selected = decisions.find((decision) => decision.id === state.selectedDecision) || decisions[0];
  if (!selected) return;
  state.selectedDecision = selected.id;
  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.classList.toggle("active", button.dataset.decision === selected.id);
    button.setAttribute("aria-pressed", button.dataset.decision === selected.id ? "true" : "false");
  });
  $("decisionHistoryTitle").textContent = selected.label;
  $("decisionHistoryContent").innerHTML = decisionHistoryHtml(selected);
}

function bindDecisionInspector(decisions) {
  document.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => {
    state.selectedDecision = button.dataset.decision;
    renderDecisionInspector(decisions);
  }));
  renderDecisionInspector(decisions);
}

function tokenClasses(token) {
  const classes = ["token"];
  if (token.changed) classes.push("changed");
  if (token.restored) classes.push("restored");
  if (token.current_route?.status === "excluded") classes.push("excluded");
  if (routeChanged(token)) classes.push("route-changed");
  const wsd = tokenWsdState(token);
  if (wsd.status === "assigned") classes.push("wsd-assigned", `wsd-${wsd.kind}`);
  if (state.selected === token.occurrence_id) classes.push("selected");
  return classes.join(" ");
}

function tokenWsdState(token) {
  const results = resolvedWsd(token.clean_processing);
  const assigned = results.find((result) => result.status === "assigned");
  if (assigned) {
    const assignment = wsdAssignmentEvidence(token.clean_processing, assigned);
    return {
      status: "assigned",
      kind: assignment.kind,
      optionCount: assignment.optionCount,
      label: assignment.kind === "automatic"
        ? `Automatic assignment: only one menu sense${assigned.selected_tuple?.headword ? ` (${assigned.selected_tuple.headword})` : ""}`
        : `WSD chose among ${assignment.optionCount || "multiple"} senses${assigned.selected_tuple?.headword ? ` (${assigned.selected_tuple.headword})` : ""}`,
    };
  }
  if (results.length) return { status: results[0].status || "unassigned", label: `WSD ${results[0].status || "unassigned"}` };
  const request = token.clean_processing?.wsd_requests?.[0];
  if (request) return { status: request.execution_status || "not_run", label: `WSD ${request.execution_status || "not run"}` };
  return { status: "unavailable", label: "No WSD evidence" };
}

function tokenWsdBadgeHtml(token) {
  const wsd = tokenWsdState(token);
  if (wsd.status !== "assigned") return "";
  const badge = wsd.kind === "automatic" ? "1" : "W";
  return `<span class="token-wsd ${escapeHtml(wsd.kind)}" title="${escapeHtml(wsd.label)}" aria-label="${escapeHtml(wsd.label)}">${badge}</span>`;
}

function routeChanged(token) {
  return resolvedComparisons(token.clean_processing).some((item) => item.classification !== "match");
}

function tokenMatches(token) {
  if (state.filter === "changed" && !token.changed) return false;
  if (state.filter === "restored" && !token.restored) return false;
  if (state.filter === "route-changed" && !routeChanged(token)) return false;
  if (state.filter === "excluded" && token.current_route?.status !== "excluded") return false;
  if (state.filter === "unresolved" && token.current_route?.status !== "unresolved") return false;
  if (state.filter === "no-menu" && !resolvedLexical(token.clean_processing).some((item) => item.status === "no_menu")) return false;
  if (state.filter === "wsd-assigned" && tokenWsdState(token).status !== "assigned") return false;
  if (state.filter === "wsd-automatic" && tokenWsdState(token).kind !== "automatic") return false;
  if (state.filter === "wsd-disambiguated" && tokenWsdState(token).kind !== "disambiguated") return false;
  const searchable = [
    token.surface,
    token.clean_processing?.surface,
    token.clean_processing?.normalized_form,
    ...Object.values(token.states || {}).map((snapshot) => snapshot.normalized_form),
  ].filter(Boolean).join(" ").toLocaleLowerCase();
  return !state.query || searchable.includes(state.query);
}

function tokenDisplayHtml(token) {
  const runSnapshots = Object.values(token.states || {});
  const sourceSurface = token.clean_processing?.surface || runSnapshots[0]?.normalized_form || token.surface;
  const restoredSurface = token.clean_processing?.normalized_form || runSnapshots.at(-1)?.normalized_form || sourceSurface;
  if (sourceSurface.toLocaleLowerCase() === restoredSurface.toLocaleLowerCase()) return `<span class="token-source">${escapeHtml(sourceSurface)}</span>`;
  return `<span class="token-source">${escapeHtml(sourceSurface)}</span><span class="token-change-arrow">→</span><span class="token-restored">${escapeHtml(restoredSurface)}</span>`;
}

function lexicalHtml(clean) {
  const candidates = resolvedLexical(clean);
  if (!candidates.length) return `<div class="no-evidence">No clean lexical-menu record is attached to this token. Nothing is inferred from the old app assignment.</div>`;
  return candidates.map((candidate) => {
    if (candidate.status !== "ready") {
      const lookup = candidate.lookup_form ? ` Lookup attempted as <strong>${escapeHtml(candidate.lookup_form)}</strong>.` : " No dictionary lookup was attempted.";
      return `<div class="lexical-candidate"><div class="state-box"><small>${escapeHtml(candidate.status)} · no sense assigned</small><strong>${escapeHtml((candidate.reason_codes || []).join(" + "))}</strong></div><div class="no-evidence">${lookup} This explicit state continues downstream; it is not a dropped token.</div></div>`;
    }
    const analyses = (candidate.analyses || []).map((analysis) => {
      const senses = (analysis.senses || []).map((sense) => `<li><strong>${escapeHtml(sense.translation || "No translation")}</strong>${sense.definition ? `<span>${escapeHtml(sense.definition)}</span>` : ""}<code>${escapeHtml(sense.sense_id)} · ${escapeHtml(sense.source_reference)}</code></li>`).join("");
      return `<details class="menu-analysis"><summary><strong>${escapeHtml(analysis.headword || "No headword")}</strong><span>${escapeHtml(analysis.part_of_speech || "POS unavailable")} · ${(analysis.senses || []).length} options</span></summary><ol>${senses}</ol></details>`;
    }).join("");
    return `<div class="lexical-candidate"><div class="state-box"><small>lookup form · ${escapeHtml(candidate.provider.source_adapter)}</small><strong>${escapeHtml(candidate.lookup_form)}</strong></div>${analyses}<div class="menu-warning">Menu options only. WSD has not selected any analysis or sense.</div></div>`;
  }).join("");
}

function wsdHtml(clean) {
  const results = resolvedWsd(clean);
  if (results.length) return results.map((result) => {
    if (result.status !== "assigned") {
      return `<div class="wsd-request"><div class="state-box"><small>${escapeHtml(result.status)} · explicit final disposition</small><strong>No sense assigned</strong></div><div class="route-reason">${escapeHtml((result.evidence?.reason_codes || []).join(" + ") || "No model execution required")}</div><code>${escapeHtml(result.result_id)}</code></div>`;
    }
    const lexical = resolvedLexical(clean).find((candidate) => (candidate.analyses || []).some((analysis) => analysis.menu_analysis_id === result.menu_analysis_id));
    const analysis = lexical?.analyses?.find((item) => item.menu_analysis_id === result.menu_analysis_id);
    const sense = analysis?.senses?.find((item) => item.sense_id === result.selected_sense_id);
    const calibration = result.evidence?.calibration || {};
    const vote = result.evidence?.token_tuple_vote || {};
    const top = (result.evidence?.gloss_top || []).map((candidate) => `<li><strong>${escapeHtml(candidate.sense_id)}</strong><span>raw ${Number(candidate.raw).toFixed(4)} · with prior ${Number(candidate.adjusted).toFixed(4)}</span><code>${escapeHtml(candidate.analysis_id)}</code></li>`).join("");
    const decisions = (result.decision_path || []).map((step) => `<span class="decision-pill">${escapeHtml(step.replaceAll("_", " "))}</span>`).join("");
    const assignment = wsdAssignmentEvidence(clean, result);
    const assignmentLabel = assignment.kind === "automatic"
      ? "Automatic · one menu sense"
      : `WSD decision · ${assignment.optionCount || "multiple"} menu senses`;
    return `<div class="wsd-result assigned">
      <div class="state-box"><small>${escapeHtml(assignmentLabel)} · ${escapeHtml(result.selected_tuple?.part_of_speech || "POS unavailable")}</small><strong>${escapeHtml(result.selected_tuple?.headword || "No headword")} → ${escapeHtml(sense?.translation || result.selected_sense_id)}</strong></div>
      ${sense?.definition ? `<p class="wsd-definition">${escapeHtml(sense.definition)}</p>` : ""}
      ${assignment.kind === "automatic" ? `<p class="wsd-definition">No ambiguity was resolved: this exact menu offered only one sense.</p>` : `<div class="decision-path">${decisions}</div>`}
      <div class="wsd-facts"><span>${assignment.kind === "automatic" ? "deterministic default" : `confidence ${Number(result.confidence).toFixed(4)}`}</span><span>${assignment.kind === "automatic" ? "model choice not required" : `BETO ${escapeHtml(vote.status || "not recorded")}${Number.isFinite(vote.gap) ? ` · gap ${Number(vote.gap).toFixed(4)}` : ""}`}</span></div>
      <details class="policy-trace"><summary>Inspect top gloss evidence and exact IDs</summary><ol>${top}</ol><div class="mono-block">result: ${escapeHtml(result.result_id)}<br>analysis: ${escapeHtml(result.menu_analysis_id)}<br>sense: ${escapeHtml(result.selected_sense_id)}</div></details>
    </div>`;
  }).join("");
  const requests = clean?.wsd_requests || [];
  if (!requests.length) return `<div class="no-evidence">No WSD request exists for this token in the selected run.</div>`;
  return requests.map((request) => `<div class="wsd-request"><div class="state-box"><small>${escapeHtml(request.eligibility)} · ${request.translation_available ? "aligned translation available" : "source context only"}</small><strong>Prepared — model not run</strong></div><code>${escapeHtml(request.request_id)}</code></div>`).join("");
}

function consolidationHtml(clean) {
  const records = resolvedConsolidation(clean);
  if (!records.length) return `<div class="no-evidence">No clean consolidation record exists for this token. The current app release remains separate.</div>`;
  return records.map(({ disposition, example, card }) => {
    if (!disposition) return `<div class="no-evidence">The consolidation reference is unresolved and must be repaired before release assembly.</div>`;
    if (disposition.study_status !== "included") {
      return `<div class="consolidation-result"><div class="state-box"><small>${escapeHtml(disposition.wsd_status)} · retained disposition</small><strong>Not included as a study card</strong></div><div class="route-reason">${escapeHtml(disposition.route_bucket)}${disposition.reason_codes?.length ? ` · ${escapeHtml(disposition.reason_codes.join(" + "))}` : ""}</div><code>${escapeHtml(disposition.disposition_id)}</code></div>`;
    }
    return `<div class="consolidation-result included">
      <div class="state-box"><small>surface card · rank ${escapeHtml(card?.rank || "pending")}</small><strong>${escapeHtml(card?.display_form || disposition.normalized_form)}</strong></div>
      <div class="wsd-facts"><span>${example?.selected_for_study ? "selected for study" : "retained outside selected cap"}</span><span>${escapeHtml(example?.selection_reason || "selection unavailable")}</span></div>
      <div class="mono-block">card: ${escapeHtml(card?.card_id)}<br>example: ${escapeHtml(example?.example_id)}<br>disposition: ${escapeHtml(disposition.disposition_id)}</div>
    </div>`;
  }).join("");
}

function routingHtml(clean, token) {
  const routes = resolvedRoutes(clean);
  if (!routes.length) {
    return `<div class="state-box"><small>${escapeHtml(token.current_route.status)}</small><strong>${escapeHtml(token.current_route.label)}</strong></div>`;
  }
  const route = routes[0];
  const comparison = resolvedComparisons(clean)[0];
  const decision = comparison ? `
    <div class="comparison route-comparison">
      <div class="state-box"><small>legacy snapshot</small><strong>${escapeHtml(comparison.baseline.bucket)}</strong></div>
      <span>→</span>
      <div class="state-box"><small>${escapeHtml(comparison.classification)}</small><strong>${escapeHtml(comparison.current.bucket)}</strong></div>
    </div>` : `<div class="state-box"><small>${escapeHtml(route.status)}</small><strong>${escapeHtml(route.bucket)}</strong></div>`;
  const policies = (route.policy_trace || []).map((policy) => `
    <li class="policy ${escapeHtml(policy.outcome)}">
      <div><strong>${escapeHtml(policy.policy_id)}</strong><span>${escapeHtml(policy.outcome)}</span></div>
      <small>${escapeHtml(policy.inputs?.length ? policy.inputs.join(" + ") : "no external input")}</small>
      <code>${escapeHtml(JSON.stringify(policy.evidence || {}))}</code>
    </li>`).join("");
  return `${decision}
    <div class="route-reason">${escapeHtml((route.reason_codes || []).join(" + "))}</div>
    <details class="policy-trace"><summary>Evaluated ${(route.policy_trace || []).length} named policies</summary><ol>${policies}</ol></details>`;
}

function lineMatches(line) {
  if (state.query && line.text.toLocaleLowerCase().includes(state.query)) return true;
  return line.occurrences.some(tokenMatches);
}

function renderSong() {
  const container = $("songLines");
  container.classList.toggle("show-ids", state.showIds);
  const lines = state.data.song.lines.filter(lineMatches);
  $("emptyState").hidden = lines.length > 0;
  container.innerHTML = lines.map((line) => {
    const visibleTokens = line.occurrences.filter((token) => state.filter === "all" || tokenMatches(token));
    const tokens = visibleTokens.map((token) => `
      <button class="${tokenClasses(token)}" data-occurrence="${escapeHtml(token.occurrence_id)}" type="button">
        ${tokenDisplayHtml(token)}${tokenWsdBadgeHtml(token)}<span class="token-id">${escapeHtml(shortId(token.occurrence_id))}</span>
      </button>`).join(" ");
    const translationText = line.translation?.text || line.translation?.english;
    const translation = translationText ? `<p class="line-translation">${escapeHtml(translationText)}</p>` : "";
    const meta = [
      line.vocalists?.length ? escapeHtml(line.vocalists.join(" + ")) : null,
      line.app_assignments.length ? `${line.app_assignments.length} deck assignment${line.app_assignments.length === 1 ? "" : "s"}` : null,
      `${line.occurrences.filter((token) => token.changed).length} changed`,
    ].filter(Boolean).map((item) => `<span>${item}</span>`).join("");
    return `<article class="line-row" data-segment="${escapeHtml(line.segment_id)}">
      <span class="line-number">${String(line.source_position + 1).padStart(2, "0")}</span>
      <div><div class="token-flow">${tokens}</div>${translation}<div class="line-meta">${meta}</div></div>
    </article>`;
  }).join("");

  container.querySelectorAll("[data-occurrence]").forEach((button) => {
    button.addEventListener("click", () => selectToken(button.dataset.occurrence));
  });
}

function findToken(occurrenceId) {
  for (const line of state.data.song.lines) {
    const token = line.occurrences.find((item) => item.occurrence_id === occurrenceId);
    if (token) return { token, line };
  }
  return null;
}

function assignmentHtml(assignments, token) {
  const likely = likelyAssignments(assignments, token);
  if (!assignments.length) return `<div class="no-evidence">This line is not materialized as an example in the selected Artist release. That absence is visible rather than inferred as a failed WSD decision.</div>`;
  if (!likely.length) return `<div class="no-evidence">This line has ${assignments.length} deck assignment${assignments.length === 1 ? "" : "s"}, but the legacy output does not preserve a safe link from this token occurrence to one of them. Nothing is guessed here.</div>`;
  return likely.slice(0, 6).map((item) => `<div class="assignment">
    <strong>${escapeHtml(item.word)}</strong>
    <p>${escapeHtml(item.sense.translation || "Sense record has no translation")}${item.sense.context ? ` · ${escapeHtml(item.sense.context)}` : ""}</p>
    <small>${escapeHtml(item.assignment_method || "method not recorded")} · sense ${item.sense_index + 1}${item.prompt_id ? ` · ${escapeHtml(item.prompt_id)}` : ""}</small>
  </div>`).join("");
}

function renderTrace(token, line) {
  const [baseline, candidate] = selectedComparisonRuns();
  const before = token.states[baseline.run_id] || {};
  const after = token.states[candidate.run_id] || {};
  const source = line.source_ingest;
  const clean = token.clean_processing;
  const decisions = classificationDecisions(token, line);
  const decisionPill = (decision) => `<button class="classification-pill" data-decision="${escapeHtml(decision.id)}" type="button" aria-pressed="false"><span>${escapeHtml(decision.label)}</span><strong>${escapeHtml(decision.status)}</strong><small>${decision.history.length} preserved</small></button>`;
  const coreDecisions = decisions.filter((decision) => !decision.id.startsWith("route-policy-"));
  const ruleDecisions = decisions.filter((decision) => decision.id.startsWith("route-policy-"));
  const decisionPills = coreDecisions.map(decisionPill).join("");
  const rulePills = ruleDecisions.map(decisionPill).join("");
  const sourceSurface = clean?.surface || before.normalized_form || token.surface;
  const restoredSurface = clean?.normalized_form || after.normalized_form || sourceSurface;
  const traceTitle = sourceSurface.toLocaleLowerCase() === restoredSurface.toLocaleLowerCase()
    ? escapeHtml(sourceSurface)
    : `${escapeHtml(sourceSurface)} <span>→ ${escapeHtml(restoredSurface)}</span>`;
  const sourceStage = source ? `
          <div class="stage"><div class="stage-title"><strong>Acquire + extract line</strong><span class="evidence-kind">new direct lineage</span></div><div class="mono-block">${escapeHtml(source.line_id)} · span ${escapeHtml(source.source_span?.join(":"))}<br>${escapeHtml(source.section?.label || "No labelled section")}</div></div>
          <div class="stage ${source.alignment ? "current" : ""}"><div class="stage-title"><strong>Align translation</strong><span class="evidence-kind">${source.alignment ? "optional snapshot" : "graceful absence"}</span></div>${source.alignment ? `<div class="state-box"><small>${escapeHtml(source.alignment.source.provider || source.alignment.source.adapter)}</small><strong>${escapeHtml(source.alignment.target.text)}</strong></div>` : `<div class="no-evidence">No translation alignment exists for this line. The lyric remains valid and continues through the pipeline.</div>`}</div>` : "";
  const badges = [
    token.changed ? `<span class="badge changed">direct change</span>` : `<span class="badge">unchanged</span>`,
    token.restored ? `<span class="badge restored">elision restored</span>` : "",
    `<span class="badge route">${escapeHtml(token.current_route.label)}</span>`,
  ].join("");
  $("traceContent").innerHTML = `
    <header class="trace-header">
      <div class="trace-header-top"><div><p class="eyebrow">Token journey</p><h2 class="trace-surface">${traceTitle}</h2></div><span class="line-number">line ${line.source_position + 1}</span></div>
      <code class="trace-id">${escapeHtml(token.occurrence_id)}</code><div class="badges">${badges}</div>
    </header>
    <div class="trace-body">
      <section class="trace-section classification-section">
        <h3>Classification decisions <span>select any decision</span></h3>
        <div class="classification-pills" role="group" aria-label="Classification decisions for ${escapeHtml(sourceSurface)}">${decisionPills}</div>
        ${ruleDecisions.length ? `<details class="decision-rule-group"><summary><span>Routing rule evaluations</span><small>${ruleDecisions.length} decisions</small></summary><div class="classification-pills rule-pills" role="group" aria-label="Routing rule decisions for ${escapeHtml(sourceSurface)}">${rulePills}</div></details>` : ""}
        <div class="decision-history" aria-live="polite">
          <div class="decision-history-heading"><span>Decision history</span><strong id="decisionHistoryTitle">—</strong></div>
          <div id="decisionHistoryContent"></div>
        </div>
      </section>
      <details class="audit-group pipeline-group">
        <summary><span>Full pipeline evidence</span><small>${token.changed ? "first divergence: normalize" : "no divergence"}</small></summary>
        <div class="audit-group-body"><div class="stage-list">
          ${sourceStage}
          <div class="stage"><div class="stage-title"><strong>Source occurrence</strong><span class="evidence-kind">direct ledger</span></div><div class="mono-block">${escapeHtml(line.segment_id)} · span ${escapeHtml(token.span?.join(":"))}<br>${escapeHtml(line.text)}</div></div>
          <div class="stage ${token.changed ? "diverged" : ""}"><div class="stage-title"><strong>Normalize</strong><span class="evidence-kind">direct comparison</span></div>
            <div class="comparison"><div class="state-box"><small>${escapeHtml(baseline.label)}</small><strong>${escapeHtml(before.normalized_form)}</strong></div><span>→</span><div class="state-box"><small>${escapeHtml(candidate.label)}</small><strong>${escapeHtml(after.normalized_form)}</strong></div></div>
          </div>
          ${clean ? `<div class="stage current"><div class="stage-title"><strong>Clean recomputation</strong><span class="evidence-kind">new direct lineage</span></div><div class="comparison"><div class="state-box"><small>${escapeHtml(clean.surface)} · ${escapeHtml(clean.tokenizer_method)}</small><strong>${escapeHtml(clean.normalized_form)}</strong></div><span>→</span><div class="state-box"><small>${escapeHtml(clean.units.map((unit) => unit.reason_code).join(" + "))}</small><strong>${escapeHtml(clean.units.map((unit) => unit.operation).join(" + "))}</strong></div></div></div>` : ""}
          <div class="stage current"><div class="stage-title"><strong>Route</strong><span class="evidence-kind">${resolvedRoutes(clean)[0]?.evidence_kind === "direct" ? "direct policy trace" : resolvedRoutes(clean)[0]?.evidence_kind === "human_review" ? "attributed human override" : "current snapshot"}</span></div>${routingHtml(clean, token)}</div>
          <div class="stage current"><div class="stage-title"><strong>Build lexical menu</strong><span class="evidence-kind">direct · pre-WSD</span></div>${lexicalHtml(clean)}</div>
          <div class="stage ${resolvedWsd(clean).length ? "current" : ""}"><div class="stage-title"><strong>Disambiguate sense</strong><span class="evidence-kind">${resolvedWsd(clean).length ? "direct immutable result" : "explicitly not run"}</span></div>${wsdHtml(clean)}</div>
          <div class="stage ${resolvedConsolidation(clean).length ? "current" : ""}"><div class="stage-title"><strong>Consolidate occurrence</strong><span class="evidence-kind">${resolvedConsolidation(clean).length ? "direct card candidate" : "not yet run"}</span></div>${consolidationHtml(clean)}</div>
          <div class="stage current"><div class="stage-title"><strong>Materialize in app</strong><span class="evidence-kind">current release</span></div>${assignmentHtml(line.app_assignments, token)}</div>
        </div></div>
      </details>
      <details class="audit-group provenance-group">
        <summary><span>Claim provenance</span><small>exact IDs and methods</small></summary>
        <div class="audit-group-body"><div class="mono-block">baseline claim: ${escapeHtml(before.claim_id || "not preserved")}<br>candidate claim: ${escapeHtml(after.claim_id || "not preserved")}<br>candidate method: ${escapeHtml(after.method_id || "not preserved")}<br>input: ${escapeHtml(after.input_fingerprint || "not preserved")}${clean ? `<br>clean occurrence: ${escapeHtml(clean.occurrence_id)}<br>clean normalizer: ${escapeHtml(clean.normalizer_method)}<br>clean router: ${escapeHtml(clean.router_method)}` : ""}</div></div>
      </details>
    </div>`;
  bindDecisionInspector(decisions);
}

function selectToken(occurrenceId) {
  if (state.selected !== occurrenceId) state.selectedDecision = null;
  state.selected = occurrenceId;
  const found = findToken(occurrenceId);
  if (!found) return;
  $("traceEmpty").hidden = true;
  $("traceContent").hidden = false;
  renderSong();
  renderTrace(found.token, found.line);
  if (window.innerWidth < 1080) $("tracePane").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderHeader() {
  const { data } = state;
  $("songTitle").textContent = data.song.title;
  $("artistName").textContent = data.artist.name;
  $("languageLabel").textContent = data.language.toUpperCase();
  renderComparisonControls();
  $("lineCount").textContent = data.comparison.line_count.toLocaleString();
  $("tokenCount").textContent = data.comparison.occurrence_count.toLocaleString();
  $("changeCount").textContent = data.comparison.changed_occurrence_count.toLocaleString();
  $("restoreCount").textContent = data.comparison.restored_occurrence_count.toLocaleString();
  $("alignmentCount").textContent = data.comparison.aligned_line_count.toLocaleString();
  const assignedTokens = data.song.lines.flatMap((line) => line.occurrences).map(tokenWsdState).filter((wsd) => wsd.status === "assigned");
  $("automaticCount").textContent = assignedTokens.filter((wsd) => wsd.kind === "automatic").length.toLocaleString();
  $("wsdCount").textContent = assignedTokens.filter((wsd) => wsd.kind === "disambiguated").length.toLocaleString();
  $("cleanCardCount").textContent = (data.comparison.consolidation_card_count || 0).toLocaleString();
  const hasCleanProcessing = data.comparison.process_lineage_event_count > 0;
  $("evidenceHeadline").textContent = hasCleanProcessing
    ? "Clean processing, routing, WSD and release evidence available"
    : "Legacy normalization and release evidence only";
  $("evidenceSummary").innerHTML = hasCleanProcessing
    ? `<strong>Evidence boundary:</strong> historical normalization is compared from two preserved runs. ${escapeHtml(data.evidence.routing)}, while app assignments remain current release records.`
    : "<strong>Evidence boundary:</strong> this song currently has the preserved legacy normalization comparison and current release records. Clean source and processing lineage have not been generated for it yet.";
  $("evidenceList").innerHTML = Object.entries(data.evidence).map(([key, value]) => `<div><strong>${escapeHtml(key)}</strong><span>${escapeHtml(value)}</span></div>`).join("");
  $("limitationsList").innerHTML = data.limitations.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function bindControls() {
  $("searchInput").addEventListener("input", (event) => { state.query = event.target.value.trim().toLocaleLowerCase(); renderSong(); });
  document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button));
    state.filter = button.dataset.filter;
    renderSong();
  }));
  $("idsToggle").addEventListener("change", (event) => { state.showIds = event.target.checked; renderSong(); });
  $("limitationsButton").addEventListener("click", () => $("limitationsDialog").showModal());
  $("dialogClose").addEventListener("click", () => $("limitationsDialog").close());
  $("themeButton").addEventListener("click", () => document.documentElement.classList.toggle("high-contrast"));
  $("songSelect").addEventListener("change", (event) => loadSong(event.target.value));
  $("comparisonButton").addEventListener("click", () => $("comparisonDialog").showModal());
  $("comparisonClose").addEventListener("click", () => $("comparisonDialog").close());
  $("comparisonDone").addEventListener("click", () => $("comparisonDialog").close());
  $("comparisonDimension").addEventListener("change", (event) => {
    state.comparisonDimension = event.target.value;
    state.baselineRunId = null;
    state.candidateRunId = null;
    renderComparisonControls();
    renderSong();
  });
  $("comparisonBaseline").addEventListener("change", (event) => {
    state.baselineRunId = event.target.value;
    renderComparisonControls();
    if (state.selected) selectToken(state.selected);
  });
  $("comparisonCandidate").addEventListener("change", (event) => {
    state.candidateRunId = event.target.value;
    renderComparisonControls();
    if (state.selected) selectToken(state.selected);
  });
}

function resetSongView() {
  state.selected = null;
  state.selectedDecision = null;
  state.comparisonDimension = "normalization";
  state.baselineRunId = null;
  state.candidateRunId = null;
  state.query = "";
  state.filter = "all";
  $("searchInput").value = "";
  document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item.dataset.filter === "all"));
  $("traceEmpty").hidden = false;
  $("traceContent").hidden = true;
}

async function loadSong(songId) {
  const entry = state.catalog.songs.find((song) => song.song_id === songId);
  if (!entry) throw new Error(`Unknown song ${songId}`);
  const requestId = ++state.requestId;
  const picker = $("songSelect");
  picker.disabled = true;
  $("songTitle").textContent = `Loading ${entry.title}…`;
  try {
    const response = await fetch(`data/${entry.bundle}?v=17`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const bundle = await response.json();
    if (requestId !== state.requestId) return;
    if (String(bundle.song.id) !== entry.song_id) throw new Error("Audit catalog and bundle song IDs do not match");
    state.data = bundle;
    resetSongView();
    picker.value = entry.song_id;
    renderHeader();
    renderSong();
    const firstChanged = state.data.song.lines.flatMap((line) => line.occurrences).find((token) => token.changed);
    const firstToken = state.data.song.lines.flatMap((line) => line.occurrences)[0];
    if (firstChanged || firstToken) selectToken((firstChanged || firstToken).occurrence_id);
    const url = new URL(window.location.href);
    url.searchParams.set("song", entry.song_id);
    window.history.replaceState({}, "", url);
  } catch (error) {
    if (requestId !== state.requestId) return;
    $("songTitle").textContent = "Could not load audit bundle";
    $("artistName").textContent = error.message;
  } finally {
    if (requestId === state.requestId) picker.disabled = false;
  }
}

async function start() {
  if (window.location.protocol === "file:") {
    const servedUrl = "http://127.0.0.1:4173/lyrics-audit/?v=17";
    $("songTitle").textContent = "Local server required";
    $("artistName").innerHTML = `This explorer loads its audit bundle over HTTP. <a href="${servedUrl}">Open the working explorer</a>.`;
    return;
  }
  try {
    const response = await fetch("data/catalog.json?v=17", { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.catalog = await response.json();
    const picker = $("songSelect");
    picker.innerHTML = state.catalog.songs.map((song) => `<option value="${escapeHtml(song.song_id)}">${escapeHtml(song.title)} — ${escapeHtml(song.coverage)}</option>`).join("");
    bindControls();
    const requested = new URLSearchParams(window.location.search).get("song");
    const initial = state.catalog.songs.some((song) => song.song_id === requested) ? requested : state.catalog.default_song_id;
    await loadSong(initial);
  } catch (error) {
    $("songTitle").textContent = "Could not load audit bundle";
    $("artistName").textContent = error.message;
  }
}

start();
