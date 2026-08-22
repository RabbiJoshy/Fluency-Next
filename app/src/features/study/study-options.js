function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

export function createStudyOptions({ getState, onExit, onToggleDirection, onToggleSpeech, onCardData, onReleaseAudit }) {
  const modal = element("div", "modal hidden study-options-modal");
  modal.id = "studyOptionsModal";
  const card = element("div", "modal-content study-options-card");
  const close = element("button", "modal-close", "✕");
  close.type = "button";
  close.setAttribute("aria-label", "Close study options");
  close.addEventListener("click", () => modal.classList.add("hidden"));
  card.append(close, element("span", "study-options-eyebrow", "Active set"), element("h3", "", "Study options"));
  const actions = element("div", "study-options-actions");
  card.append(actions);
  modal.append(card);
  document.body.append(modal);

  function action(label, detail, handler, className = "") {
    const button = element("button", className);
    button.type = "button";
    button.append(element("strong", "", label), element("span", "", detail));
    button.addEventListener("click", handler);
    actions.append(button);
    return button;
  }

  function render() {
    const state = getState();
    actions.replaceChildren();
    action("Main menu", "Return to French Speech setup", () => { modal.classList.add("hidden"); onExit(); });
    action(
      "Card direction",
      state.direction === "target" ? "French → English" : "English → French",
      () => { onToggleDirection(); render(); },
    );
    action(
      "Automatic speech",
      state.autoSpeech ? "On · tap to mute" : "Off · tap to enable",
      () => { onToggleSpeech(); render(); },
    );
    action(
      "Set progress",
      `${state.summary.known} known · ${state.summary.review} review · ${state.summary.unseen} unseen`,
      () => {},
      "is-static",
    );
    action("Card Data", `Inspect every example assignment for ${state.card.display_form}`, () => { modal.classList.add("hidden"); onCardData(); }, "is-primary");
    action("Release & layer audit", "Inspect exact runs, artifacts and fallback policy", () => { modal.classList.add("hidden"); onReleaseAudit(); });
  }

  function open() {
    render();
    modal.classList.remove("hidden");
  }

  modal.addEventListener("click", (event) => { if (event.target === modal) modal.classList.add("hidden"); });
  return Object.freeze({ modal, open, render });
}
