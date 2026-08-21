import { speak, speechAvailable } from "../../services/speech.js";

function titleCase(value) {
  const text = String(value || "").replaceAll("_", " ");
  return text ? text[0].toUpperCase() + text.slice(1) : "Other";
}

function buildLookupUrl(template, surface) {
  return template.replace("{surface}", encodeURIComponent(surface));
}

export function createStudyController({ release, language, progress, onProgress, onExit }) {
  const cards = release.deck.cards;
  const elements = {
    setup: document.querySelector("#setup-view"),
    study: document.querySelector("#study-view"),
    flashcard: document.querySelector("#flashcard"),
    front: document.querySelector("#card-front"),
    back: document.querySelector("#card-back"),
    frontRank: document.querySelector("#front-rank"),
    frontHeadword: document.querySelector("#front-headword"),
    frontPos: document.querySelector("#front-pos"),
    backHeadword: document.querySelector("#back-headword"),
    backPos: document.querySelector("#back-pos"),
    meaningTabs: document.querySelector("#meaning-tabs"),
    meaningAnswer: document.querySelector("#meaning-answer"),
    example: document.querySelector("#example-card"),
    exampleTarget: document.querySelector("#example-target"),
    exampleEnglish: document.querySelector("#example-english"),
    examplePosition: document.querySelector("#example-position"),
    lookup: document.querySelector("#lookup-link"),
    scrubber: document.querySelector("#scrubber-segments"),
    previous: document.querySelector("#previous-card"),
    next: document.querySelector("#next-card"),
    feedback: document.querySelector("#score-feedback"),
    menu: document.querySelector("#study-menu"),
    completion: document.querySelector("#completion-dialog"),
  };

  let index = 0;
  let meaningIndex = 0;
  let exampleIndex = 0;
  let revealed = false;
  let direction = localStorage.getItem("fluency-next:card-direction:v1") || "target";
  let autoSpeech = localStorage.getItem("fluency-next:auto-speech:v1") !== "off";

  function card() { return cards[index]; }
  function meaning() { return card().meanings[meaningIndex] || card().meanings[0]; }
  function examples() {
    const matching = card().examples.filter((example) => example.sense_id === meaning().sense_id);
    return matching.length ? matching : card().examples;
  }

  function renderScrubber() {
    elements.scrubber.replaceChildren();
    cards.forEach((item, cardIndex) => {
      const segment = document.createElement("button");
      segment.type = "button";
      segment.textContent = String(cardIndex + 1);
      segment.dataset.status = progress.status(item.card_id);
      segment.setAttribute("aria-label", `Go to card ${cardIndex + 1} of ${cards.length} · ${segment.dataset.status}`);
      segment.setAttribute("aria-current", cardIndex === index ? "step" : "false");
      segment.addEventListener("click", () => moveTo(cardIndex));
      elements.scrubber.append(segment);
    });
  }

  function renderMeaningTabs() {
    elements.meaningTabs.replaceChildren();
    card().meanings.forEach((item, itemIndex) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "meaning-tab";
      button.setAttribute("aria-pressed", String(itemIndex === meaningIndex));
      const pos = document.createElement("span");
      pos.className = "tab-pos";
      pos.textContent = item.part_of_speech;
      const translation = document.createElement("span");
      translation.className = "tab-translation";
      translation.textContent = item.translation;
      const itemNumber = document.createElement("span");
      itemNumber.className = "tab-index";
      itemNumber.textContent = card().meanings.length > 1 ? `${itemIndex + 1}/${card().meanings.length}` : "";
      button.append(pos, translation, itemNumber);
      button.addEventListener("click", () => {
        meaningIndex = itemIndex;
        exampleIndex = 0;
        renderBackDetails();
      });
      elements.meaningTabs.append(button);
    });
  }

  function renderBackDetails() {
    const selectedMeaning = meaning();
    const selectedExamples = examples();
    const example = selectedExamples[exampleIndex % selectedExamples.length];
    renderMeaningTabs();
    elements.meaningAnswer.replaceChildren(document.createTextNode(selectedMeaning.translation));
    if (selectedMeaning.context) {
      const context = document.createElement("small");
      context.textContent = selectedMeaning.context;
      elements.meaningAnswer.append(context);
    }
    elements.exampleTarget.textContent = example?.target || "No example attached";
    elements.exampleEnglish.textContent = example?.english || "";
    elements.examplePosition.textContent = selectedExamples.length > 1
      ? `${(exampleIndex % selectedExamples.length) + 1}/${selectedExamples.length}`
      : "1/1";
  }

  function renderCard({ announce = false } = {}) {
    const current = card();
    const firstMeaning = current.meanings[0];
    meaningIndex = Math.min(meaningIndex, current.meanings.length - 1);
    exampleIndex = 0;
    revealed = false;
    elements.front.hidden = false;
    elements.back.hidden = true;
    elements.frontRank.textContent = `Pilot card ${current.rank} of ${cards.length}`;
    elements.frontHeadword.textContent = direction === "target" ? current.display_form : firstMeaning.translation;
    elements.frontHeadword.lang = direction === "target" ? language.key : "en";
    elements.frontPos.textContent = direction === "target" ? titleCase(firstMeaning.part_of_speech) : "English";
    elements.backHeadword.textContent = current.display_form;
    elements.backHeadword.lang = language.key;
    elements.backPos.textContent = titleCase(meaning().part_of_speech);
    renderBackDetails();
    const lookupTemplate = language.reference_links?.word_reference || language.reference_links?.reverso;
    if (lookupTemplate) {
      elements.lookup.href = buildLookupUrl(lookupTemplate, current.display_form);
      elements.lookup.hidden = false;
    } else {
      elements.lookup.hidden = true;
    }
    elements.previous.disabled = index === 0;
    elements.next.disabled = index === cards.length - 1;
    elements.feedback.textContent = "";
    renderScrubber();
    if (announce && autoSpeech) {
      const text = direction === "target" ? current.display_form : firstMeaning.translation;
      speak(text, language.locale, { english: direction !== "target" });
    }
  }

  function reveal() {
    if (revealed) return;
    revealed = true;
    elements.front.hidden = true;
    elements.back.hidden = false;
    const spoken = direction === "target" ? meaning().translation : card().display_form;
    if (autoSpeech) speak(spoken, language.locale, { english: direction === "target" });
  }

  function moveTo(nextIndex, { announce = true } = {}) {
    index = Math.max(0, Math.min(cards.length - 1, nextIndex));
    meaningIndex = 0;
    renderCard({ announce });
  }

  function renderCompletion() {
    const summary = progress.summary(cards.map((item) => item.card_id));
    const container = document.querySelector("#completion-stats");
    container.replaceChildren();
    for (const [label, value] of [["Known", summary.known], ["Review", summary.review], ["Unseen", summary.unseen]]) {
      const block = document.createElement("div");
      const number = document.createElement("strong");
      number.textContent = String(value);
      const name = document.createElement("span");
      name.textContent = label;
      block.append(number, name);
      container.append(block);
    }
  }

  function answer(correct) {
    if (!revealed) {
      elements.feedback.textContent = "Reveal the card before scoring.";
      return;
    }
    progress.answer(card().card_id, correct);
    elements.feedback.textContent = correct ? "Correct" : "Added to review";
    elements.flashcard.classList.remove("score-correct", "score-incorrect");
    void elements.flashcard.offsetWidth;
    elements.flashcard.classList.add(correct ? "score-correct" : "score-incorrect");
    renderScrubber();
    onProgress();
    if (index === cards.length - 1) {
      renderCompletion();
      window.setTimeout(() => elements.completion.showModal(), 230);
    } else {
      window.setTimeout(() => moveTo(index + 1), 230);
    }
  }

  function cycleExample() {
    if (!revealed) return;
    const count = examples().length;
    if (count <= 1) return;
    exampleIndex = (exampleIndex + 1) % count;
    renderBackDetails();
  }

  function show() {
    elements.setup.hidden = true;
    elements.study.hidden = false;
    moveTo(0);
  }

  function exit() {
    elements.study.hidden = true;
    elements.setup.hidden = false;
    if (elements.menu.open) elements.menu.close();
    onExit();
  }

  function updateMenu() {
    document.querySelector("#menu-direction span").textContent = direction === "target"
      ? "English → French"
      : "French → English";
    document.querySelector("#menu-speech span").textContent = autoSpeech
      ? "Mute automatic speech"
      : "Enable automatic speech";
    const summary = progress.summary(cards.map((item) => item.card_id));
    document.querySelector("#menu-progress-copy").textContent =
      `${summary.known} known · ${summary.review} review · ${summary.unseen} unseen`;
  }

  document.querySelector("#headword-button").addEventListener("click", reveal);
  elements.flashcard.addEventListener("click", (event) => {
    if (!revealed || event.target.closest("button, a")) return;
    renderCard();
  });
  document.querySelector("#speak-card").disabled = !speechAvailable();
  document.querySelector("#speak-card").addEventListener("click", () => {
    const text = direction === "target" ? card().display_form : meaning().translation;
    speak(text, language.locale, { english: direction !== "target" });
  });
  elements.example.addEventListener("click", cycleExample);
  elements.previous.addEventListener("click", () => moveTo(index - 1));
  elements.next.addEventListener("click", () => moveTo(index + 1));
  document.querySelector("#answer-correct").addEventListener("click", () => answer(true));
  document.querySelector("#answer-incorrect").addEventListener("click", () => answer(false));
  document.querySelector("#study-settings-button").addEventListener("click", () => {
    updateMenu();
    elements.menu.showModal();
  });
  document.querySelector("#study-main-menu").addEventListener("click", exit);
  document.querySelector("#menu-main").addEventListener("click", exit);
  document.querySelector("#menu-direction").addEventListener("click", () => {
    direction = direction === "target" ? "english" : "target";
    localStorage.setItem("fluency-next:card-direction:v1", direction);
    updateMenu();
    renderCard({ announce: true });
  });
  document.querySelector("#menu-speech").addEventListener("click", () => {
    autoSpeech = !autoSpeech;
    localStorage.setItem("fluency-next:auto-speech:v1", autoSpeech ? "on" : "off");
    updateMenu();
  });
  document.querySelector("#menu-progress").addEventListener("click", () => {
    renderCompletion();
    elements.menu.close();
    elements.completion.showModal();
  });

  document.addEventListener("keydown", (event) => {
    if (elements.study.hidden || document.querySelector("dialog[open]") || event.metaKey || event.ctrlKey) return;
    if (event.key === " ") { event.preventDefault(); revealed ? renderCard() : reveal(); }
    if (event.key === "ArrowLeft") moveTo(index - 1);
    if (event.key === "ArrowRight") moveTo(index + 1);
    if (event.key === "Tab") { event.preventDefault(); cycleExample(); }
    if (event.key === "Enter") answer(true);
    if (event.key.toLowerCase() === "x") answer(false);
    if (event.key === "Escape") exit();
  });

  return Object.freeze({ show, exit, renderCompletion, refreshProgress: renderScrubber });
}
