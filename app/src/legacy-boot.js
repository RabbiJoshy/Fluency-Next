import { loadLanguageRegistry } from "./core/language-registry.js";
import { loadRelease } from "./core/release-client.js";
import { createProgressStore } from "./services/progress-store.js";
import { speak } from "./services/speech.js";

const byId = (id) => document.getElementById(id);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function titleCase(value) {
  const text = String(value || "other").replaceAll("_", " ");
  return text[0].toUpperCase() + text.slice(1);
}

function posClass(value) {
  const aliases = { adjective: "adj", adverb: "adv", conjunction: "conj", determiner: "det", interjection: "int", noun: "noun", preposition: "prep", pronoun: "pron", verb: "verb" };
  return `pos-${aliases[String(value).toLowerCase()] || "other"}`;
}

function showModal(modal) { modal?.classList.remove("hidden"); }
function hideModal(modal) { modal?.classList.add("hidden"); }

function createReleaseAudit(release) {
  const modal = element("div", "modal hidden release-audit-modal");
  modal.id = "releaseAuditModal";
  const card = element("div", "modal-content release-audit-card");
  const close = element("button", "modal-close", "✕");
  close.type = "button";
  close.setAttribute("aria-label", "Close release audit");
  close.addEventListener("click", () => hideModal(modal));
  card.append(close, element("h3", "", "Release & layer audit"));
  card.append(element("p", "release-audit-note", "Choose an exact approved candidate. Selection reloads the app with that release only; no older deck is scanned or blended in."));

  const selector = element("select");
  selector.id = "releaseSelector";
  for (const candidate of release.catalog.candidates) {
    const option = element("option", "", `${candidate.label}${candidate.active ? " · active" : ""}`);
    option.value = candidate.release_id;
    option.selected = candidate.release_id === release.manifest.release_id;
    selector.append(option);
  }
  selector.addEventListener("change", () => {
    const url = new URL(window.location.href);
    if (selector.value === release.catalog.active_release_id) url.searchParams.delete("release");
    else url.searchParams.set("release", selector.value);
    window.location.assign(url);
  });
  card.append(selector);

  const rows = [
    ["Release", release.manifest.release_id],
    ["Selection", release.selectedExplicitly ? "explicit candidate" : "active pointer"],
    ["Deck hash", release.manifest.deck_content_id],
    ["Composition hash", release.manifest.composition_content_id],
    ["Conflict policy", release.composition.conflict_policy],
    ["Fallback policy", release.composition.fallback_policy],
    ["WSD", `${release.manifest.wsd.status} · enabled=${release.manifest.wsd.enabled}`],
  ];
  const grid = element("dl", "release-audit-grid");
  for (const [name, value] of rows) grid.append(element("dt", "", name), element("dd", "", value));
  card.append(grid, element("h4", "", "Selected layers"));
  const layers = element("div", "release-layer-list");
  for (const [name, selection] of Object.entries(release.composition.layers)) {
    const item = element("div", "release-layer");
    item.append(
      element("strong", "", name.replaceAll("_", " ")),
      element("span", "", `${selection.source_type}:${selection.source_id}`),
      element("span", "", selection.artifact_id),
    );
    layers.append(item);
  }
  for (const omitted of release.composition.omitted_layers) {
    const item = element("div", "release-layer");
    item.append(element("strong", "", `${omitted.layer.replaceAll("_", " ")} · omitted`), element("span", "", omitted.reason));
    layers.append(item);
  }
  card.append(layers);
  modal.append(card);
  modal.addEventListener("click", (event) => { if (event.target === modal) hideModal(modal); });
  document.body.append(modal);
  return modal;
}

function renderSetup(languages, release, progress, startStudy, auditModal) {
  const registry = [...languages.values()];
  const tabs = byId("languageTabs");
  tabs.replaceChildren();
  for (const language of registry) {
    const button = element("button", `lang-tab${language.key === "fr" ? " active" : ""}`);
    button.type = "button";
    button.disabled = language.key !== "fr";
    button.append(element("span", "", language.flag), element("span", "", language.name));
    if (language.key !== "fr") button.title = `${language.name}: ${language.status.replaceAll("_", " ")}`;
    tabs.append(button);
  }
  byId("step1Title").textContent = "Language";
  byId("step2").style.display = "block";
  const levelSelector = byId("levelSelector");
  levelSelector.replaceChildren();
  const level = element("button", "level-btn selected", "Pilot");
  level.type = "button";
  levelSelector.append(level);
  byId("levelInfoLine").textContent = `${release.manifest.card_count} surface cards · curated fixture`;
  byId("levelInfoLine").style.display = "inline";
  byId("step4").style.display = "block";

  function refresh() {
    const summary = progress.summary(release.deck.cards.map((card) => card.card_id));
    const panel = element("div", "study-set-panel");
    const overview = element("div", "study-set-overview");
    overview.append(element("strong", "", "Pilot · Set 1 of 1"), element("span", "", `${summary.known} known · ${summary.review} review · ${summary.unseen} unseen`));
    const dots = element("div", "study-set-dots");
    const dot = element("button", `study-set-dot is-current${summary.unseen < summary.total ? " is-partial" : ""}`, "1");
    dot.type = "button";
    dot.style.setProperty("--set-known-end", `${(summary.known / summary.total) * 100}%`);
    dot.style.setProperty("--set-review-end", `${((summary.known + summary.review) / summary.total) * 100}%`);
    dots.append(dot);
    const start = element("button", "range-btn-new study-set-start", summary.unseen === summary.total ? `Learn ${summary.total} new cards` : "Continue French Speech");
    start.type = "button";
    start.addEventListener("click", startStudy);
    panel.append(overview, dots, start, element("span", "pilot-setup-badge", `Exact release: ${release.manifest.release_id} · WSD ${release.manifest.wsd.status}`));
    byId("rangeSelector").replaceChildren(panel);
  }
  refresh();

  const status = element("button", "release-pill", release.selectedExplicitly ? "Candidate release" : "Active release");
  status.type = "button";
  status.title = release.manifest.release_id;
  status.addEventListener("click", () => showModal(auditModal));
  byId("syncStatusIndicator").replaceWith(status);
  byId("topBarGearBtn").addEventListener("click", () => showModal(auditModal));
  byId("findWordBtn").style.display = "none";
  byId("standardSourceCard").style.display = "flex";
  byId("standardSourceLanguageIcon").textContent = "🇫🇷";
  byId("standardSourceLanguageName").textContent = "French";
  byId("standardSourcePickerBtn").textContent = "Browse Lyrics · coming later";
  byId("standardSourcePickerBtn").disabled = true;
  byId("standardSourceLanguageBtn").disabled = true;
  return { refresh };
}

function createStudy(release, language, progress, onProgress) {
  const cards = release.deck.cards;
  const flashcard = byId("flashcard");
  const setup = byId("setupPanel");
  const app = byId("appContent");
  let index = 0;
  let exampleIndex = 0;
  let revealed = false;
  let autoSpeech = localStorage.getItem("fluency-next:auto-speech:v1") !== "off";

  const scoreActions = element("div", "pilot-score-actions hidden");
  const wrong = element("button", "incorrect", "✗");
  const right = element("button", "correct", "✓");
  wrong.type = right.type = "button";
  wrong.setAttribute("aria-label", "Needs review");
  right.setAttribute("aria-label", "Correct");
  scoreActions.append(wrong, right);
  document.body.append(scoreActions);

  function card() { return cards[index]; }
  function allExamples() { return card().examples.length ? card().examples : [{ target: "No example attached", english: "" }]; }

  function renderScrubbers() {
    const desktop = byId("deckProgressSegments");
    const mobile = byId("cardBackPips");
    desktop.replaceChildren();
    mobile.replaceChildren();
    cards.forEach((item, itemIndex) => {
      const status = progress.status(item.card_id);
      const segment = element("button", `deck-progress-segment${itemIndex === index ? " is-current" : ""}${status !== "unseen" ? " is-visited" : ""}${status === "known" ? " is-result-correct" : status === "review" ? " is-result-incorrect" : ""}`, itemIndex + 1);
      segment.type = "button";
      segment.dataset.distance = String(Math.min(4, Math.abs(itemIndex - index)));
      segment.addEventListener("click", () => move(itemIndex));
      desktop.append(segment);
      const pip = element("button", `cbp-pip${itemIndex === index ? " is-current" : ""}${status !== "unseen" ? " is-visited" : ""}`, itemIndex + 1);
      pip.type = "button";
      pip.addEventListener("click", () => move(itemIndex));
      mobile.append(pip);
    });
  }

  function renderBack() {
    const current = card();
    const wrapper = element("div", "pilot-back-content");
    wrapper.append(element("h2", "", current.display_form));
    for (const meaning of current.meanings) {
      const row = element("div", "pilot-meaning");
      row.append(element("strong", "", meaning.translation));
      if (meaning.context) row.append(element("small", "", meaning.context));
      wrapper.append(row);
    }
    const examples = allExamples();
    const example = examples[exampleIndex % examples.length];
    const exampleButton = element("button", "pilot-example");
    exampleButton.type = "button";
    exampleButton.append(element("span", "", example.target), element("span", "", example.english));
    if (examples.length > 1) exampleButton.append(element("small", "", `${exampleIndex + 1}/${examples.length} · tap for next`));
    exampleButton.addEventListener("click", (event) => { event.stopPropagation(); exampleIndex = (exampleIndex + 1) % examples.length; renderBack(); });
    wrapper.append(exampleButton);
    byId("backContent").replaceChildren(wrapper);
  }

  function render({ announce = false } = {}) {
    const current = card();
    const meaning = current.meanings[0];
    revealed = false;
    exampleIndex = 0;
    flashcard.classList.remove("flipped");
    byId("frontWord").textContent = current.display_form;
    byId("frontLemma").textContent = "";
    byId("frontMeanings").replaceChildren();
    byId("frontPOS").replaceChildren(element("span", `card-pos ${posClass(meaning.part_of_speech)}`, titleCase(meaning.part_of_speech)));
    byId("frontRanking").textContent = `Pilot card ${index + 1} of ${cards.length}`;
    renderBack();
    renderScrubbers();
    for (const id of ["prevBtnFront", "prevBtnFrontMobile", "prevBtnBack"]) byId(id).disabled = index === 0;
    for (const id of ["nextBtnFront", "nextBtnFrontMobile", "nextBtnBack"]) byId(id).disabled = index === cards.length - 1;
    if (announce && autoSpeech) speak(current.display_form, language.locale);
  }

  function reveal() {
    if (revealed) return;
    revealed = true;
    flashcard.classList.add("flipped");
    if (autoSpeech) speak(card().meanings[0].translation, language.locale, { english: true });
  }

  function move(next) {
    index = Math.max(0, Math.min(cards.length - 1, next));
    render({ announce: true });
  }

  function answer(correct) {
    if (!revealed) { reveal(); return; }
    progress.answer(card().card_id, correct);
    const indicator = byId(correct ? "correctIndicator" : "incorrectIndicator");
    indicator.classList.add("visible");
    renderScrubbers();
    onProgress();
    window.setTimeout(() => {
      indicator.classList.remove("visible");
      if (index < cards.length - 1) move(index + 1);
      else exit();
    }, 230);
  }

  function show() {
    setup.style.display = "none";
    app.classList.remove("hidden");
    scoreActions.classList.remove("hidden");
    index = 0;
    render({ announce: true });
  }

  function exit() {
    app.classList.add("hidden");
    scoreActions.classList.add("hidden");
    setup.style.display = "block";
    onProgress();
  }

  byId("flipBtn").addEventListener("click", reveal);
  flashcard.querySelector(".card-back").addEventListener("click", (event) => { if (!event.target.closest("button, a")) render(); });
  wrong.addEventListener("click", () => answer(false));
  right.addEventListener("click", () => answer(true));
  for (const id of ["prevBtnFront", "prevBtnFrontMobile", "prevBtnBack"]) byId(id).addEventListener("click", () => move(index - 1));
  for (const id of ["nextBtnFront", "nextBtnFrontMobile", "nextBtnBack"]) byId(id).addEventListener("click", () => move(index + 1));
  for (const id of ["backBtnFloating", "backBtnFrontMobile"]) byId(id).addEventListener("click", exit);
  document.addEventListener("keydown", (event) => {
    if (app.classList.contains("hidden") || event.metaKey || event.ctrlKey) return;
    if (event.key === " ") { event.preventDefault(); revealed ? render() : reveal(); }
    if (event.key === "ArrowLeft") move(index - 1);
    if (event.key === "ArrowRight") move(index + 1);
    if (event.key === "Enter") answer(true);
    if (event.key.toLowerCase() === "x") answer(false);
    if (event.key === "Escape") exit();
  });
  return { show, exit };
}

function fatal(error) {
  const panel = element("section", "pilot-fatal");
  panel.append(element("h1", "", "Fluency could not load this release."), element("p", "", error instanceof Error ? error.message : String(error)), element("code", "", "make pilot\nmake dev"));
  document.body.append(panel);
  byId("appLoadingScreen")?.classList.add("is-hidden");
}

async function start() {
  const languages = await loadLanguageRegistry();
  const language = languages.get("fr");
  if (!language) throw new Error("French is missing from the language registry");
  const release = await loadRelease(language, "speech");
  const progress = createProgressStore({ language: "fr", mode: "speech", namespace: release.manifest.progress_namespace });
  const audit = createReleaseAudit(release);
  let setup;
  const study = createStudy(release, language, progress, () => setup?.refresh());
  setup = renderSetup(languages, release, progress, study.show, audit);

  byId("studyMenuBtn").addEventListener("click", () => showModal(audit));
  byId("actionsGearBack").addEventListener("click", () => showModal(audit));
  byId("actionsGearFront").addEventListener("click", () => showModal(audit));
  byId("helpBtn").addEventListener("click", () => showModal(byId("helpModal")));
  byId("closeHelpModal")?.addEventListener("click", () => hideModal(byId("helpModal")));
  document.documentElement.classList.remove("app-booting");
  byId("appLoadingScreen").classList.add("is-hidden");
  const knownLocalUser = localStorage.getItem("flashcardUser") || sessionStorage.getItem("flashcardGuestSession");
  if (knownLocalUser) hideModal(byId("authModal"));
}

start().catch(fatal);
