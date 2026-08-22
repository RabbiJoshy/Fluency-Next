function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function flattenMetadata(value, prefix = "", rows = []) {
  if (Array.isArray(value)) {
    if (!value.length) rows.push([prefix, "[]"]);
    value.forEach((item, index) => flattenMetadata(item, `${prefix}[${index}]`, rows));
    return rows;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) rows.push([prefix, "{}"]);
    for (const [key, child] of entries) flattenMetadata(child, prefix ? `${prefix}.${key}` : key, rows);
    return rows;
  }
  rows.push([prefix, value == null ? "not recorded" : String(value)]);
  return rows;
}

function metadataTable(rows) {
  const table = element("dl", "card-data-metadata");
  for (const [key, value] of rows) {
    table.append(element("dt", "", key), element("dd", "", value));
  }
  return table;
}

function layerSummary(composition, layerName) {
  const selected = composition.layers[layerName];
  if (selected) {
    return {
      state: "selected",
      source: `${selected.source_type}:${selected.source_id}`,
      artifact: selected.artifact_id,
      fallback: selected.fallback
        ? `${selected.fallback.policy}:${selected.fallback.source_id}`
        : "none",
    };
  }
  const omitted = composition.omitted_layers.find((item) => item.layer === layerName);
  return { state: "omitted", reason: omitted?.reason || "not declared" };
}

export function createCardDataInspector(release, getActiveCardState) {
  const modal = element("div", "modal hidden card-data-modal");
  modal.id = "cardDataModal";
  const shell = element("div", "modal-content card-data-card");
  const close = element("button", "modal-close", "✕");
  close.type = "button";
  close.setAttribute("aria-label", "Close Card Data");
  close.addEventListener("click", () => modal.classList.add("hidden"));
  const eyebrow = element("span", "card-data-eyebrow", "Active card evidence");
  const title = element("h3", "", "Card Data");
  const subtitle = element("p", "card-data-subtitle");
  const scrubber = element("div", "card-data-scrubber");
  const content = element("div", "card-data-content");
  shell.append(close, eyebrow, title, subtitle, scrubber, content);
  modal.append(shell);
  document.body.append(modal);

  let card;
  let exampleIndex = 0;

  function examples() {
    return Array.isArray(card?.examples) ? card.examples : [];
  }

  function assignedSense(example) {
    return card.meanings.find((meaning) => meaning.sense_id === example?.sense_id) || null;
  }

  function renderScrubber() {
    scrubber.replaceChildren();
    const items = examples();
    const previous = element("button", "card-data-arrow", "‹");
    previous.type = "button";
    previous.setAttribute("aria-label", "Previous example metadata");
    previous.disabled = exampleIndex === 0;
    previous.addEventListener("click", () => { exampleIndex -= 1; render(); });
    const positions = element("div", "card-data-positions");
    items.forEach((example, index) => {
      const button = element("button", index === exampleIndex ? "is-current" : "", index + 1);
      button.type = "button";
      button.setAttribute("aria-label", `Inspect example ${index + 1} of ${items.length}`);
      button.setAttribute("aria-current", index === exampleIndex ? "step" : "false");
      button.addEventListener("click", () => { exampleIndex = index; render(); });
      positions.append(button);
    });
    const next = element("button", "card-data-arrow", "›");
    next.type = "button";
    next.setAttribute("aria-label", "Next example metadata");
    next.disabled = exampleIndex >= items.length - 1;
    next.addEventListener("click", () => { exampleIndex += 1; render(); });
    scrubber.append(previous, positions, next);
  }

  function renderSenseMenu(activeSense) {
    const details = element("details", "card-data-sense-menu");
    const summary = element("summary", "", `Full sense menu · ${card.meanings.length}`);
    details.append(summary);
    const list = element("div", "card-data-sense-list");
    card.meanings.forEach((meaning, index) => {
      const row = element("div", meaning.sense_id === activeSense?.sense_id ? "is-assigned" : "");
      row.append(
        element("strong", "", `${index + 1}. ${meaning.translation}`),
        element("span", "", `${meaning.part_of_speech} · ${meaning.sense_id}`),
      );
      if (meaning.context) row.append(element("small", "", meaning.context));
      list.append(row);
    });
    details.append(list);
    return details;
  }

  function render() {
    const items = examples();
    exampleIndex = Math.max(0, Math.min(Math.max(0, items.length - 1), exampleIndex));
    const example = items[exampleIndex] || null;
    const sense = assignedSense(example);
    subtitle.textContent = `${card.display_form} · ${card.card_id} · Example ${items.length ? exampleIndex + 1 : 0} of ${items.length}`;
    renderScrubber();
    content.replaceChildren();

    const sentence = element("section", "card-data-section card-data-example");
    sentence.append(element("span", "card-data-section-label", "Example"));
    sentence.append(
      element("p", "card-data-target", example?.target || "No example attached"),
      element("p", "card-data-english", example?.english || "No English sentence recorded"),
    );
    content.append(sentence);

    const assignment = element("section", "card-data-section");
    assignment.append(element("span", "card-data-section-label", "Assigned sense"));
    if (sense) {
      assignment.append(
        element("h4", "", sense.translation),
        element("p", "card-data-sense-id", `${sense.part_of_speech} · ${sense.sense_id}`),
      );
      if (sense.context) assignment.append(element("p", "card-data-context", sense.context));
    } else {
      assignment.append(element("p", "card-data-unassigned", example ? "Unassigned: the example sense_id does not resolve in this card." : "No example to assign."));
    }
    content.append(assignment);

    const wsdLayer = layerSummary(release.composition, "wsd_assignments");
    const manualOverrideLayer = layerSummary(release.composition, "manual_overrides");
    const evidenceRows = [
      ...flattenMetadata(example || {}, "example"),
      ...flattenMetadata(sense || {}, "assigned_sense"),
      ["assignment.method", example?.assignment_method || sense?.assignment_method || "not recorded"],
      ["assignment.confidence", example?.assignment_confidence ?? example?.confidence ?? "not recorded"],
      ["assignment.run_id", example?.assignment_run_id || example?.run_id || "not recorded"],
      ["assignment.fallback", release.composition.fallback_policy === "none" ? "none" : "see selected layer fallback metadata"],
      ["assignment.manual_override", manualOverrideLayer.state === "omitted" ? manualOverrideLayer.reason : manualOverrideLayer.source],
      ...flattenMetadata(layerSummary(release.composition, "sentences"), "sentence_layer"),
      ...flattenMetadata(wsdLayer, "wsd_layer"),
      ...flattenMetadata(layerSummary(release.composition, "example_selection"), "example_selection_layer"),
      ["release.id", release.manifest.release_id],
      ["release.deck_content_id", release.manifest.deck_content_id],
      ["release.composition_content_id", release.manifest.composition_content_id],
      ["release.fallback_policy", release.composition.fallback_policy],
    ];
    const evidence = element("section", "card-data-section");
    evidence.append(element("span", "card-data-section-label", "Complete recorded metadata"), metadataTable(evidenceRows));
    content.append(evidence, renderSenseMenu(sense));
  }

  function open() {
    const state = getActiveCardState();
    card = state.card;
    exampleIndex = Math.max(0, state.exampleIndex || 0);
    render();
    modal.classList.remove("hidden");
  }

  modal.addEventListener("click", (event) => { if (event.target === modal) modal.classList.add("hidden"); });
  return Object.freeze({ modal, open });
}
