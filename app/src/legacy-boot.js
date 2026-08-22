import { loadLanguageRegistry } from "./core/language-registry.js";
import { loadRelease } from "./core/release-client.js";
import { createCardDataInspector } from "./features/diagnostics/card-data-inspector.js";
import { createStudyOptions } from "./features/study/study-options.js";
import { buildStudyQueue, findLevel, findSet, nextUnseenSet, releaseCardMap } from "./features/study/study-queues.js";
import { createProgressStore } from "./services/progress-store.js";
import { speak } from "./services/speech.js";
import { createStudySessionStore } from "./services/study-session-store.js";

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
    ["Study structure", release.studyStructureAdapted ? "legacy single-set compatibility adapter" : release.deck.study_structure.structure_version],
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
  byId("step4").style.display = "block";
  const structure = release.deck.study_structure;
  let selectedLevelId = structure.levels[0].level_id;
  let selectedSetId = structure.levels[0].sets[0].set_id;

  function cardIdsForLevel(level) {
    return level.sets.flatMap((studySet) => studySet.card_ids);
  }

  function selectSuggestedSet(level) {
    return level.sets.find((studySet) => progress.summary(studySet.card_ids).unseen > 0)
      || level.sets[level.sets.length - 1];
  }

  function renderLevels() {
    const levelSelector = byId("levelSelector");
    levelSelector.replaceChildren();
    for (const level of structure.levels) {
      const button = element("button", `level-btn${level.level_id === selectedLevelId ? " selected" : ""}`, level.label);
      button.type = "button";
      button.dataset.level = level.level_id;
      button.addEventListener("click", () => {
        selectedLevelId = level.level_id;
        selectedSetId = selectSuggestedSet(level).set_id;
        refresh();
      });
      levelSelector.append(button);
    }
  }

  function refresh() {
    const level = findLevel(release.deck, selectedLevelId) || structure.levels[0];
    if (!findSet(release.deck, level.level_id, selectedSetId)) selectedSetId = selectSuggestedSet(level).set_id;
    const studySet = findSet(release.deck, level.level_id, selectedSetId);
    const levelSummary = progress.summary(cardIdsForLevel(level));
    const setSummary = progress.summary(studySet.card_ids);
    renderLevels();
    byId("levelInfoLine").textContent = `${levelSummary.total} surface cards · ${level.sets.length} stable set${level.sets.length === 1 ? "" : "s"}`;
    byId("levelInfoLine").style.display = "inline";
    const panel = element("div", "study-set-panel");
    const overview = element("div", "study-set-overview");
    const seenSets = level.sets.filter((item) => progress.summary(item.card_ids).unseen < item.card_ids.length).length;
    overview.append(
      element("strong", "", `${seenSets} of ${level.sets.length} sets seen`),
      element("span", "", "New cards stay separate from unfinished review"),
    );
    const dots = element("div", "study-set-dots");
    level.sets.forEach((item, index) => {
      const summary = progress.summary(item.card_ids);
      const dot = element(
        "button",
        `study-set-dot${item.set_id === selectedSetId ? " is-current" : ""}${summary.unseen === 0 ? " is-complete" : summary.unseen < summary.total ? " is-partial" : ""}`,
        index + 1,
      );
      dot.type = "button";
      dot.style.setProperty("--set-known-end", `${(summary.known / summary.total) * 100}%`);
      dot.style.setProperty("--set-review-end", `${((summary.known + summary.review) / summary.total) * 100}%`);
      dot.setAttribute("aria-label", `${item.label}: ${summary.known} known, ${summary.review} review, ${summary.unseen} unseen`);
      dot.addEventListener("click", () => {
        if (selectedSetId === item.set_id) {
          startStudy({ levelId: level.level_id, setId: item.set_id, queueType: summary.unseen > 0 ? "learn" : "all" });
        } else {
          selectedSetId = item.set_id;
          refresh();
        }
      });
      dots.append(dot);
    });
    const current = element("div", "study-set-current-copy");
    const setNumber = level.sets.findIndex((item) => item.set_id === studySet.set_id) + 1;
    current.append(
      element("strong", "", `${studySet.label} of ${level.sets.length}`),
      element("span", "", `${setSummary.known} known · ${setSummary.review} review · ${setSummary.unseen} unseen`),
    );
    const queueType = setSummary.unseen > 0 ? "learn" : "all";
    const start = element(
      "button",
      "range-btn-new study-set-start",
      setSummary.unseen > 0
        ? `Learn ${setSummary.unseen} new card${setSummary.unseen === 1 ? "" : "s"}`
        : `Study Set ${setNumber} Again`,
    );
    start.type = "button";
    start.addEventListener("click", () => startStudy({ levelId: level.level_id, setId: studySet.set_id, queueType }));
    panel.append(overview, dots, current, start);
    if (levelSummary.review > 0) {
      const review = element("button", "study-set-review");
      review.type = "button";
      review.append(
        element("span", "", "Review cards"),
        element("small", "", `${levelSummary.review} unfinished in this level`),
      );
      review.addEventListener("click", () => startStudy({ levelId: level.level_id, setId: studySet.set_id, queueType: "review" }));
      panel.append(review);
    }
    panel.append(element("span", "pilot-setup-badge", `Exact release: ${release.manifest.release_id} · WSD ${release.manifest.wsd.status}`));
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

function createStudy(release, language, progress, sessionStore, onProgress) {
  const allCards = release.deck.cards;
  const cardMap = releaseCardMap(release.deck);
  let cards = [];
  const flashcard = byId("flashcard");
  const setup = byId("setupPanel");
  const app = byId("appContent");
  let index = 0;
  let exampleIndex = 0;
  let revealed = false;
  let direction = localStorage.getItem("fluency-next:card-direction:v1") || "target";
  let autoSpeech = localStorage.getItem("fluency-next:auto-speech:v1") !== "off";
  let session = null;
  let completionNext = null;
  let completionTimer = null;

  const scoreActions = element("div", "pilot-score-actions hidden");
  const wrong = element("button", "incorrect", "✗");
  const right = element("button", "correct", "✓");
  wrong.type = right.type = "button";
  wrong.setAttribute("aria-label", "Needs review");
  right.setAttribute("aria-label", "Correct");
  scoreActions.append(wrong, right);
  document.body.append(scoreActions);

  function card() { return cards[index] || allCards[0]; }
  function allExamples() { return card().examples.length ? card().examples : [{ target: "No example attached", english: "" }]; }

  function sessionTotals() {
    const totals = { correct: 0, incorrect: 0 };
    for (const result of Object.values(session?.sessionResults || {})) {
      totals.correct += Number(result.correct || 0);
      totals.incorrect += Number(result.incorrect || 0);
    }
    return totals;
  }

  function snapshot() {
    if (!session || !cards.length) return null;
    return {
      release_id: release.manifest.release_id,
      level_id: session.levelId,
      set_id: session.setId,
      queue_type: session.queueType,
      card_ids: [...session.cardIds],
      current_position: index,
      current_word: card().display_form,
      card_side: revealed ? "back" : "front",
      example_index: exampleIndex,
      direction,
      automatic_speech: autoSpeech,
      session_results: session.sessionResults,
    };
  }

  function saveSnapshot() {
    const value = snapshot();
    if (value && !app.classList.contains("hidden")) sessionStore.save(value);
  }

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
    exampleButton.addEventListener("click", (event) => {
      event.stopPropagation();
      exampleIndex = (exampleIndex + 1) % examples.length;
      renderBack();
      saveSnapshot();
    });
    wrapper.append(exampleButton);
    byId("backContent").replaceChildren(wrapper);
  }

  function render({ announce = false, save = true } = {}) {
    const current = card();
    const meaning = current.meanings[0];
    revealed = false;
    exampleIndex = 0;
    flashcard.classList.remove("flipped");
    byId("frontWord").textContent = direction === "target" ? current.display_form : meaning.translation;
    byId("frontLemma").textContent = "";
    byId("frontMeanings").replaceChildren();
    byId("frontPOS").replaceChildren(
      element(
        "span",
        `card-pos ${direction === "target" ? posClass(meaning.part_of_speech) : "pos-other"}`,
        direction === "target" ? titleCase(meaning.part_of_speech) : "English",
      ),
    );
    byId("frontRanking").textContent = `Pilot card ${index + 1} of ${cards.length}`;
    renderBack();
    renderScrubbers();
    for (const id of ["prevBtnFront", "prevBtnFrontMobile", "prevBtnBack"]) byId(id).disabled = index === 0;
    for (const id of ["nextBtnFront", "nextBtnFrontMobile", "nextBtnBack"]) byId(id).disabled = index === cards.length - 1;
    if (announce && autoSpeech) {
      speak(
        direction === "target" ? current.display_form : meaning.translation,
        language.locale,
        { english: direction !== "target" },
      );
    }
    if (save) saveSnapshot();
  }

  function reveal({ announce = true, save = true } = {}) {
    if (revealed) return;
    revealed = true;
    flashcard.classList.add("flipped");
    if (announce && autoSpeech) {
      speak(
        direction === "target" ? card().meanings[0].translation : card().display_form,
        language.locale,
        { english: direction === "target" },
      );
    }
    if (save) saveSnapshot();
  }

  function move(next) {
    index = Math.max(0, Math.min(cards.length - 1, next));
    render({ announce: true });
  }

  function recordSessionResult(correct) {
    const cardId = card().card_id;
    const previous = session.sessionResults[cardId] || { correct: 0, incorrect: 0 };
    session.sessionResults[cardId] = {
      correct: previous.correct + (correct ? 1 : 0),
      incorrect: previous.incorrect + (correct ? 0 : 1),
      last_result: correct ? "correct" : "incorrect",
    };
  }

  function cancelCompletionTimer() {
    if (completionTimer) window.clearTimeout(completionTimer);
    completionTimer = null;
  }

  function hideCompletion() {
    cancelCompletionTimer();
    byId("deckCompleteModal").classList.add("hidden");
  }

  function showCompletion() {
    sessionStore.clear();
    scoreActions.classList.add("hidden");
    const totals = sessionTotals();
    const attempts = totals.correct + totals.incorrect;
    const accuracy = attempts ? Math.round((totals.correct / attempts) * 100) : 0;
    const level = findLevel(release.deck, session.levelId);
    const studySet = findSet(release.deck, session.levelId, session.setId);
    const setNumber = Math.max(0, level?.sets.findIndex((item) => item.set_id === session.setId)) + 1;
    byId("deckCompleteTitle").textContent = session.queueType === "review"
      ? "Review Complete!"
      : studySet ? `Set ${setNumber} Complete!` : "Set Complete!";
    byId("completeCorrect").textContent = String(totals.correct);
    byId("completeIncorrect").textContent = String(totals.incorrect);
    byId("completeAccuracy").textContent = `${accuracy}% accuracy`;
    completionNext = session.queueType === "learn"
      ? nextUnseenSet(release.deck, progress, session.levelId, session.setId)
      : null;
    const continueButton = byId("markCompleteBtn");
    if (completionNext) {
      byId("markCompleteLabel").textContent = `Start ${completionNext.label}`;
      byId("markCompleteIcon").textContent = "→";
      byId("completeMessage").textContent = `${byId("markCompleteLabel").textContent} automatically…`;
      continueButton.style.display = "";
    } else {
      byId("completeMessage").textContent = "";
      continueButton.style.display = "none";
    }
    byId("deckCompleteModal").classList.remove("hidden");
    if (completionNext) {
      completionTimer = window.setTimeout(() => {
        completionTimer = null;
        continueButton.click();
      }, 1200);
    }
  }

  function answer(correct) {
    if (!revealed) { reveal(); return; }
    progress.answer(card().card_id, correct);
    recordSessionResult(correct);
    const indicator = byId(correct ? "correctIndicator" : "incorrectIndicator");
    indicator.classList.add("visible");
    renderScrubbers();
    saveSnapshot();
    onProgress();
    window.setTimeout(() => {
      indicator.classList.remove("visible");
      if (index < cards.length - 1) move(index + 1);
      else showCompletion();
    }, 230);
  }

  function openSession({ levelId, setId, queueType, explicitCardIds = null, resumeSnapshot = null }) {
    const queue = explicitCardIds
      ? {
          cardIds: [...explicitCardIds],
          cards: explicitCardIds.map((cardId) => cardMap.get(cardId)),
        }
      : buildStudyQueue(release.deck, progress, { levelId, setId, queueType });
    if (!queue.cardIds.length || queue.cards.some((item) => !item)) return false;
    cards = [...queue.cards];
    session = {
      levelId,
      setId,
      queueType,
      cardIds: [...queue.cardIds],
      sessionResults: { ...(resumeSnapshot?.session_results || {}) },
    };
    index = Math.min(cards.length - 1, Math.max(0, resumeSnapshot?.current_position || 0));
    direction = resumeSnapshot?.direction || direction;
    autoSpeech = typeof resumeSnapshot?.automatic_speech === "boolean"
      ? resumeSnapshot.automatic_speech
      : autoSpeech;
    setup.style.display = "none";
    app.classList.remove("hidden");
    scoreActions.classList.remove("hidden");
    render({ announce: !resumeSnapshot, save: false });
    if (resumeSnapshot) {
      exampleIndex = Math.min(allExamples().length - 1, Math.max(0, resumeSnapshot.example_index || 0));
      renderBack();
      if (resumeSnapshot.card_side === "back") reveal({ announce: false, save: false });
    }
    saveSnapshot();
    return true;
  }

  function show(options) {
    return openSession(options);
  }

  function resume(resumeSnapshot) {
    if (resumeSnapshot.release_id !== release.manifest.release_id) return false;
    if (!findLevel(release.deck, resumeSnapshot.level_id)) return false;
    if (!findSet(release.deck, resumeSnapshot.level_id, resumeSnapshot.set_id)) return false;
    if (!resumeSnapshot.card_ids.every((cardId) => cardMap.has(cardId))) return false;
    return openSession({
      levelId: resumeSnapshot.level_id,
      setId: resumeSnapshot.set_id,
      queueType: resumeSnapshot.queue_type,
      explicitCardIds: resumeSnapshot.card_ids,
      resumeSnapshot,
    });
  }

  function exit({ preserveSnapshot = true } = {}) {
    if (preserveSnapshot) saveSnapshot();
    app.classList.add("hidden");
    scoreActions.classList.add("hidden");
    setup.style.display = "block";
    onProgress();
  }

  function toggleDirection() {
    direction = direction === "target" ? "english" : "target";
    localStorage.setItem("fluency-next:card-direction:v1", direction);
    if (!app.classList.contains("hidden")) render({ announce: true });
    return direction;
  }

  function toggleSpeech() {
    autoSpeech = !autoSpeech;
    localStorage.setItem("fluency-next:auto-speech:v1", autoSpeech ? "on" : "off");
    if (autoSpeech) {
      const current = card();
      speak(
        direction === "target" ? current.display_form : current.meanings[0].translation,
        language.locale,
        { english: direction !== "target" },
      );
    }
    saveSnapshot();
    return autoSpeech;
  }

  function getState() {
    return {
      card: card(),
      cardIndex: index,
      exampleIndex,
      direction,
      autoSpeech,
      summary: progress.summary(cards.map((item) => item.card_id)),
    };
  }

  byId("flipBtn").addEventListener("click", reveal);
  flashcard.querySelector(".card-back").addEventListener("click", (event) => { if (!event.target.closest("button, a")) render(); });
  wrong.addEventListener("click", () => answer(false));
  right.addEventListener("click", () => answer(true));
  for (const id of ["prevBtnFront", "prevBtnFrontMobile", "prevBtnBack"]) byId(id).addEventListener("click", () => move(index - 1));
  for (const id of ["nextBtnFront", "nextBtnFrontMobile", "nextBtnBack"]) byId(id).addEventListener("click", () => move(index + 1));
  for (const id of ["backBtnFloating", "backBtnFrontMobile"]) byId(id).addEventListener("click", exit);
  byId("markCompleteBtn").addEventListener("click", () => {
    if (!completionNext) return;
    const next = completionNext;
    hideCompletion();
    show({ levelId: next.levelId, setId: next.setId, queueType: "learn" });
    onProgress();
  });
  byId("deckCompleteMenuBtn").addEventListener("click", () => {
    hideCompletion();
    exit({ preserveSnapshot: false });
  });
  byId("restartAllBtn").addEventListener("click", () => {
    const redo = {
      levelId: session.levelId,
      setId: session.setId,
      queueType: session.queueType,
      explicitCardIds: [...session.cardIds],
    };
    hideCompletion();
    openSession(redo);
  });
  byId("deckCompleteModal").addEventListener("click", (event) => {
    if (event.target === byId("deckCompleteModal")) hideCompletion();
  });
  document.addEventListener("keydown", (event) => {
    if (app.classList.contains("hidden") || event.metaKey || event.ctrlKey) return;
    if (!byId("deckCompleteModal").classList.contains("hidden")) {
      if (event.key === "Escape") hideCompletion();
      return;
    }
    if (event.key === " ") { event.preventDefault(); revealed ? render() : reveal(); }
    if (event.key === "ArrowLeft") move(index - 1);
    if (event.key === "ArrowRight") move(index + 1);
    if (event.key === "Enter") answer(true);
    if (event.key.toLowerCase() === "x") answer(false);
    if (event.key === "Escape") exit();
  });
  return Object.freeze({ show, resume, exit, toggleDirection, toggleSpeech, getState });
}

function createResumePrompt(release, snapshot, onResume) {
  let shown = false;
  return function showResumePrompt() {
    if (shown || !snapshot) return;
    shown = true;
    const modal = element("section", "modal resume-entry-modal");
    modal.id = "resumeLastSetCard";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute("aria-labelledby", "resumeEntryTitle");
    const content = element("div", "modal-content resume-entry-content");
    content.append(element("span", "resume-set-eyebrow", "Welcome back"));
    const title = element("h3", "", "Continue where you stopped?");
    title.id = "resumeEntryTitle";
    const source = element("strong", "", "French speech");
    const track = snapshot.queue_type === "review" ? "Review" : "Learn new";
    const context = element("p", "", `${snapshot.level_id} · ${snapshot.set_id} · ${track}`);
    const lastCard = element("small", "", `Last card: ${snapshot.current_word || "saved card"} · position ${snapshot.current_position + 1} of ${snapshot.card_ids.length}`);
    const actions = element("div", "resume-entry-actions");
    const dismiss = element("button", "resume-entry-secondary", "Choose a new set");
    dismiss.type = "button";
    const resume = element("button", "resume-entry-primary");
    resume.type = "button";
    const currentRelease = snapshot.release_id === release.manifest.release_id;
    const savedCandidate = release.catalog.candidates.find((item) => item.release_id === snapshot.release_id);
    resume.textContent = currentRelease ? "Continue set" : savedCandidate ? "Open saved release" : "Saved release unavailable";
    resume.disabled = !currentRelease && !savedCandidate;
    actions.append(dismiss, resume);
    content.append(title, source, context, lastCard, actions);
    modal.append(content);
    document.body.append(modal);

    function close() { modal.remove(); }
    dismiss.addEventListener("click", close);
    resume.addEventListener("click", () => {
      if (!currentRelease && savedCandidate) {
        const url = new URL(window.location.href);
        url.searchParams.set("release", snapshot.release_id);
        window.location.assign(url);
        return;
      }
      if (onResume(snapshot)) close();
      else {
        lastCard.textContent = "This saved queue no longer matches its exact release structure.";
        resume.disabled = true;
      }
    });
    modal.addEventListener("click", (event) => { if (event.target === modal) close(); });
  };
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
  const sessionStore = createStudySessionStore({ language: "fr", mode: "speech", namespace: release.manifest.progress_namespace });
  const audit = createReleaseAudit(release);
  let setup;
  const study = createStudy(release, language, progress, sessionStore, () => setup?.refresh());
  setup = renderSetup(languages, release, progress, study.show, audit);
  const cardData = createCardDataInspector(release, study.getState);
  const studyOptions = createStudyOptions({
    getState: study.getState,
    onExit: study.exit,
    onToggleDirection: study.toggleDirection,
    onToggleSpeech: study.toggleSpeech,
    onCardData: cardData.open,
    onReleaseAudit: () => showModal(audit),
  });

  byId("studyMenuBtn").addEventListener("click", studyOptions.open);
  byId("actionsGearBack").addEventListener("click", studyOptions.open);
  byId("actionsGearFront").addEventListener("click", studyOptions.open);
  for (const id of ["reverseLangBtn", "reverseLangBtnPopup"]) {
    byId(id)?.addEventListener("click", study.toggleDirection);
  }
  for (const id of ["speakBtn", "speakBtnPopup"]) {
    byId(id)?.addEventListener("click", study.toggleSpeech);
  }
  byId("helpBtn").addEventListener("click", () => showModal(byId("helpModal")));
  byId("closeHelpModal")?.addEventListener("click", () => hideModal(byId("helpModal")));
  document.documentElement.classList.remove("app-booting");
  byId("appLoadingScreen").classList.add("is-hidden");
  const knownLocalUser = localStorage.getItem("flashcardUser") || sessionStorage.getItem("flashcardGuestSession");
  const showResumePrompt = createResumePrompt(release, sessionStore.load(), study.resume);
  if (knownLocalUser) {
    hideModal(byId("authModal"));
    showResumePrompt();
  } else {
    for (const id of ["guestModeBtn", "submitInitialsBtn"]) {
      byId(id)?.addEventListener("click", () => window.setTimeout(showResumePrompt, 0));
    }
  }
}

start().catch(fatal);
