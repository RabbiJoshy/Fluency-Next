const state = { catalog: null, data: null, filter: "all", query: "", selected: null, showIds: false, requestId: 0 };

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

function resolvedConsolidation(clean) {
  return (clean?.consolidations || []).map((reference) => ({
    ...reference,
    disposition: state.data.consolidation_dispositions?.[reference.disposition_id],
    example: reference.example_id ? state.data.consolidated_examples?.[reference.example_id] : null,
    card: reference.card_id ? state.data.consolidated_cards?.[reference.card_id] : null,
  }));
}

function tokenClasses(token) {
  const classes = ["token"];
  if (token.changed) classes.push("changed");
  if (token.restored) classes.push("restored");
  if (token.current_route?.status === "excluded") classes.push("excluded");
  if (routeChanged(token)) classes.push("route-changed");
  if (state.selected === token.occurrence_id) classes.push("selected");
  return classes.join(" ");
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
  return !state.query || token.surface.toLocaleLowerCase().includes(state.query);
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
    return `<div class="wsd-result assigned">
      <div class="state-box"><small>${escapeHtml(result.selected_tuple?.part_of_speech || "POS unavailable")} · ${escapeHtml(calibration.legacy_band || "unbanded")} legacy confidence band</small><strong>${escapeHtml(result.selected_tuple?.headword || "No headword")} → ${escapeHtml(sense?.translation || result.selected_sense_id)}</strong></div>
      ${sense?.definition ? `<p class="wsd-definition">${escapeHtml(sense.definition)}</p>` : ""}
      <div class="decision-path">${decisions}</div>
      <div class="wsd-facts"><span>confidence ${Number(result.confidence).toFixed(4)}</span><span>BETO ${escapeHtml(vote.status || "not recorded")}${Number.isFinite(vote.gap) ? ` · gap ${Number(vote.gap).toFixed(4)}` : ""}</span></div>
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
        ${escapeHtml(token.surface)}<span class="token-id">${escapeHtml(shortId(token.occurrence_id))}</span>
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
  const normalized = (token.clean_processing?.normalized_form || Object.values(token.states).at(-1)?.normalized_form)?.toLocaleLowerCase();
  const likely = assignments.filter((item) => [item.word, item.lemma].filter(Boolean).some((value) => value.toLocaleLowerCase() === normalized));
  if (!assignments.length) return `<div class="no-evidence">This line is not materialized as an example in the selected Artist release. That absence is visible rather than inferred as a failed WSD decision.</div>`;
  if (!likely.length) return `<div class="no-evidence">This line has ${assignments.length} deck assignment${assignments.length === 1 ? "" : "s"}, but the legacy output does not preserve a safe link from this token occurrence to one of them. Nothing is guessed here.</div>`;
  return likely.slice(0, 6).map((item) => `<div class="assignment">
    <strong>${escapeHtml(item.word)}</strong>
    <p>${escapeHtml(item.sense.translation || "Sense record has no translation")}${item.sense.context ? ` · ${escapeHtml(item.sense.context)}` : ""}</p>
    <small>${escapeHtml(item.assignment_method || "method not recorded")} · sense ${item.sense_index + 1}${item.prompt_id ? ` · ${escapeHtml(item.prompt_id)}` : ""}</small>
  </div>`).join("");
}

function renderTrace(token, line) {
  const [baseline, candidate] = state.data.runs;
  const before = token.states[baseline.run_id] || {};
  const after = token.states[candidate.run_id] || {};
  const source = line.source_ingest;
  const clean = token.clean_processing;
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
      <div class="trace-header-top"><div><p class="eyebrow">Token journey</p><h2 class="trace-surface">${escapeHtml(token.surface)}</h2></div><span class="line-number">line ${line.source_position + 1}</span></div>
      <code class="trace-id">${escapeHtml(token.occurrence_id)}</code><div class="badges">${badges}</div>
    </header>
    <div class="trace-body">
      <section class="trace-section"><h3>Pipeline trace <span>${token.changed ? "first divergence: normalize" : "no divergence"}</span></h3>
        <div class="stage-list">
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
        </div>
      </section>
      <section class="trace-section"><h3>Claim provenance</h3><div class="mono-block">baseline claim: ${escapeHtml(before.claim_id || "not preserved")}<br>candidate claim: ${escapeHtml(after.claim_id || "not preserved")}<br>candidate method: ${escapeHtml(after.method_id || "not preserved")}<br>input: ${escapeHtml(after.input_fingerprint || "not preserved")}${clean ? `<br>clean occurrence: ${escapeHtml(clean.occurrence_id)}<br>clean normalizer: ${escapeHtml(clean.normalizer_method)}<br>clean router: ${escapeHtml(clean.router_method)}` : ""}</div></section>
    </div>`;
}

function selectToken(occurrenceId) {
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
  const [baseline, candidate] = data.runs;
  $("songTitle").textContent = data.song.title;
  $("artistName").textContent = data.artist.name;
  $("languageLabel").textContent = data.language.toUpperCase();
  $("baselineLabel").textContent = baseline.label;
  $("baselineId").textContent = baseline.run_id;
  $("candidateLabel").textContent = candidate.label;
  $("candidateId").textContent = candidate.run_id;
  $("lineCount").textContent = data.comparison.line_count.toLocaleString();
  $("tokenCount").textContent = data.comparison.occurrence_count.toLocaleString();
  $("changeCount").textContent = data.comparison.changed_occurrence_count.toLocaleString();
  $("restoreCount").textContent = data.comparison.restored_occurrence_count.toLocaleString();
  $("alignmentCount").textContent = data.comparison.aligned_line_count.toLocaleString();
  $("wsdCount").textContent = (data.comparison.wsd_result_counts?.assigned || 0).toLocaleString();
  $("cleanCardCount").textContent = (data.comparison.consolidation_card_count || 0).toLocaleString();
  const hasCleanProcessing = data.comparison.process_lineage_event_count > 0;
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
}

function resetSongView() {
  state.selected = null;
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
    const response = await fetch(`data/${entry.bundle}?v=11`, { cache: "no-store" });
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
    const servedUrl = "http://127.0.0.1:4173/lyrics-audit/?v=11";
    $("songTitle").textContent = "Local server required";
    $("artistName").innerHTML = `This explorer loads its audit bundle over HTTP. <a href="${servedUrl}">Open the working explorer</a>.`;
    return;
  }
  try {
    const response = await fetch("data/catalog.json?v=11", { cache: "no-store" });
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
