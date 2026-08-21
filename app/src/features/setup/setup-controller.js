function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = String(value);
}

export function createSetupController({ languages, release, progress, onStart }) {
  const dialog = document.querySelector("#language-dialog");
  const orbit = document.querySelector("#language-orbit");
  const picker = document.querySelector("#language-picker-button");
  const start = document.querySelector("#start-study");
  const cardIds = release.deck.cards.map((card) => card.card_id);

  function renderLanguageChoices() {
    orbit.querySelectorAll(".language-choice").forEach((element) => element.remove());
    const choices = [...languages.values()];
    choices.forEach((language, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "language-choice";
      button.style.setProperty("--angle", `${(360 / choices.length) * index}deg`);
      button.disabled = language.status !== "pilot";
      button.setAttribute("aria-label", button.disabled
        ? `${language.name} — ${language.status.replaceAll("_", " ")}`
        : language.name);

      const flag = document.createElement("span");
      flag.className = "flag";
      flag.textContent = language.flag;
      const name = document.createElement("strong");
      name.textContent = language.name;
      const status = document.createElement("small");
      status.textContent = language.status === "pilot" ? "ready" : language.status.replaceAll("_", " ");
      button.append(flag, name, status);
      if (!button.disabled) button.addEventListener("click", () => dialog.close());
      orbit.append(button);
    });
  }

  function renderProgress() {
    const summary = progress.summary(cardIds);
    const seen = summary.known + summary.review;
    setText("#set-progress-title", `${seen > 0 ? 1 : 0} of 1 sets seen`);
    setText("#set-summary-copy", `${summary.known} known · ${summary.review} review · ${summary.unseen} unseen`);
    if (summary.unseen === summary.total) {
      start.textContent = `Learn ${summary.total} new cards`;
    } else if (summary.review > 0) {
      start.textContent = `Continue · ${summary.review} to review`;
    } else {
      start.textContent = "Continue Pilot";
    }
    document.querySelector("#pilot-set").dataset.known = String(summary.known);
    return summary;
  }

  picker.addEventListener("click", () => dialog.showModal());
  start.addEventListener("click", onStart);
  setText("#pilot-card-count", release.manifest.card_count);
  renderLanguageChoices();
  renderProgress();

  return Object.freeze({ renderProgress });
}
