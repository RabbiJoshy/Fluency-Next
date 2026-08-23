const state = { data: null, filter: "all", query: "", selected: null, showIds: false };

const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const shortId = (value) => value ? `${value.slice(0, 8)}…` : "not preserved";

function tokenClasses(token) {
  const classes = ["token"];
  if (token.changed) classes.push("changed");
  if (token.restored) classes.push("restored");
  if (token.current_route?.status === "excluded") classes.push("excluded");
  if (state.selected === token.occurrence_id) classes.push("selected");
  return classes.join(" ");
}

function tokenMatches(token) {
  if (state.filter === "changed" && !token.changed) return false;
  if (state.filter === "restored" && !token.restored) return false;
  if (state.filter === "excluded" && token.current_route?.status !== "excluded") return false;
  if (state.filter === "unresolved" && token.current_route?.status !== "unresolved") return false;
  return !state.query || token.surface.toLocaleLowerCase().includes(state.query);
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
          <div class="stage current"><div class="stage-title"><strong>Route</strong><span class="evidence-kind">${clean ? "pinned migration snapshot" : "current snapshot"}</span></div><div class="state-box"><small>${escapeHtml(token.current_route.status)}</small><strong>${escapeHtml(token.current_route.label)}</strong></div></div>
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
}

async function start() {
  if (window.location.protocol === "file:") {
    const servedUrl = "http://127.0.0.1:4173/lyrics-audit/?v=5";
    $("songTitle").textContent = "Local server required";
    $("artistName").innerHTML = `This explorer loads its audit bundle over HTTP. <a href="${servedUrl}">Open the working explorer</a>.`;
    return;
  }
  try {
    const response = await fetch("data/estamos-arriba.json?v=4", { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    state.data = await response.json();
    renderHeader();
    renderSong();
    const firstChanged = state.data.song.lines.flatMap((line) => line.occurrences).find((token) => token.changed);
    if (firstChanged) selectToken(firstChanged.occurrence_id);
    bindControls();
  } catch (error) {
    $("songTitle").textContent = "Could not load audit bundle";
    $("artistName").textContent = error.message;
  }
}

start();
