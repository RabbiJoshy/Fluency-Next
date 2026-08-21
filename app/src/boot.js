import { createAppStore } from "./core/app-store.js";
import { loadLanguageRegistry } from "./core/language-registry.js";
import { loadRelease } from "./core/release-client.js";
import { createSetupController } from "./features/setup/setup-controller.js";
import { createStudyController } from "./features/study/study-controller.js";
import { createProgressStore } from "./services/progress-store.js";

const WELCOME_KEY = "fluency-next:local-welcome:v1";

function setInformation(title, body) {
  const dialog = document.querySelector("#information-dialog");
  document.querySelector("#information-title").textContent = title;
  dialog.querySelector("p").textContent = body;
  dialog.showModal();
}

function addDiagnostic(list, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = String(value);
  list.append(term, description);
}

function renderDiagnostics(release) {
  const list = document.querySelector("#diagnostics-list");
  list.replaceChildren();
  const rows = [
    ["Release", release.manifest.release_id],
    ["Selection", release.selectedExplicitly ? "explicit URL candidate" : "active.json pointer"],
    ["Language", `${release.manifest.language} · ${release.manifest.locale}`],
    ["Mode", release.manifest.mode],
    ["Status", release.manifest.publication_status],
    ["Cards", release.manifest.card_count],
    ["Deck hash", release.manifest.deck_content_id],
    ["WSD", `${release.manifest.wsd.status} · enabled=${release.manifest.wsd.enabled}`],
    ["Progress", release.manifest.progress_namespace],
    ["Created", release.manifest.created_at],
  ];
  for (const [label, value] of rows) addDiagnostic(list, label, value);
}

function wireDialogs() {
  for (const closer of document.querySelectorAll("[data-close-dialog]")) {
    closer.addEventListener("click", () => document.querySelector(`#${closer.dataset.closeDialog}`)?.close());
  }
  for (const dialog of document.querySelectorAll("dialog")) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog && !dialog.classList.contains("radial-dialog")) dialog.close();
    });
  }
}

function showFatal(error) {
  document.querySelector("#boot-screen").hidden = true;
  document.querySelector("#welcome-screen").hidden = true;
  document.querySelector("#app-container").hidden = true;
  document.querySelector("#fatal-error").hidden = false;
  document.querySelector("#fatal-error-message").textContent = error instanceof Error ? error.message : String(error);
  document.documentElement.classList.remove("app-booting");
}

async function start() {
  wireDialogs();
  const languages = await loadLanguageRegistry();
  const language = languages.get("fr");
  if (!language) throw new Error("French is missing from the language registry");
  const release = await loadRelease(language, "speech");
  const store = createAppStore({ screen: "setup", language: "fr", mode: "speech", releaseId: release.manifest.release_id });
  const progress = createProgressStore({
    language: language.key,
    mode: "speech",
    namespace: release.manifest.progress_namespace,
  });

  let setupController;
  const studyController = createStudyController({
    release,
    language,
    progress,
    onProgress: () => setupController.renderProgress(),
    onExit: () => {
      store.update({ screen: "setup" });
      setupController.renderProgress();
    },
  });
  setupController = createSetupController({
    languages,
    release,
    progress,
    onStart: () => {
      store.update({ screen: "study" });
      studyController.show();
    },
  });

  renderDiagnostics(release);
  document.body.dataset.theme = language.theme;
  document.querySelector("#app-container").hidden = false;
  document.querySelector("#diagnostics-button").addEventListener("click", () =>
    document.querySelector("#diagnostics-dialog").showModal());
  document.querySelector("#release-status-button").addEventListener("click", () =>
    document.querySelector("#diagnostics-dialog").showModal());
  document.querySelector("#menu-diagnostics").addEventListener("click", () => {
    document.querySelector("#study-menu").close();
    document.querySelector("#diagnostics-dialog").showModal();
  });
  document.querySelector("#completion-main-menu").addEventListener("click", () => {
    document.querySelector("#completion-dialog").close();
    studyController.exit();
  });
  const resetProgress = document.querySelector("#reset-progress");
  resetProgress.addEventListener("click", () => {
    if (resetProgress.dataset.armed !== "true") {
      resetProgress.dataset.armed = "true";
      resetProgress.textContent = "Press again to confirm reset";
      return;
    }
    progress.reset();
    setupController.renderProgress();
    studyController.refreshProgress();
    resetProgress.dataset.armed = "false";
    resetProgress.textContent = "Pilot progress reset";
  });

  document.querySelector("#help-button").addEventListener("click", () => setInformation(
    "How to start",
    "Choose French, open the Pilot level, and learn its one 25-card set. Reveal each card before scoring it. This is the real rebuilt Speech flow using curated fixture data while the research layers are developed.",
  ));
  document.querySelector("#setup-settings-button").addEventListener("click", () => setInformation(
    "Local study settings",
    "Card direction and automatic speech are available from the gear beside the study scrubber. Lemma merging has been deliberately removed; surface forms own card identity.",
  ));
  document.querySelector("#level-info-button").addEventListener("click", () => setInformation(
    "Pilot level",
    "This temporary level proves the complete release-to-app path. It does not claim frequency rank, corpus coverage, or WSD output. Production levels will use approved inventory metadata without changing this interface.",
  ));
  document.querySelector("#artist-preview-button").addEventListener("click", () => setInformation(
    "Lyrics architecture reserved",
    "Artist mode will use this same shell, language registry, stable card identity, and study engine. Its song, artist, audio, and Spotify code will load only when Lyrics is selected.",
  ));
  document.querySelector("#welcome-about").addEventListener("click", () => setInformation(
    "About this rebuild",
    "Fluency is being migrated into a smaller multilingual application with immutable, selectable research releases. French Speech is the first working vertical slice.",
  ));

  const welcome = document.querySelector("#welcome-screen");
  const seenWelcome = sessionStorage.getItem(WELCOME_KEY) === "seen";
  welcome.hidden = seenWelcome;
  document.querySelector("#continue-local").addEventListener("click", () => {
    sessionStorage.setItem(WELCOME_KEY, "seen");
    welcome.hidden = true;
  });

  document.documentElement.classList.remove("app-booting");
  document.documentElement.classList.add("app-ready");
  window.setTimeout(() => { document.querySelector("#boot-screen").hidden = true; }, 220);
}

start().catch(showFatal);
