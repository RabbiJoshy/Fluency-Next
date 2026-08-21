async function fetchJson(url, label) {
  const response = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
  return response.json();
}

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

function safeReleaseId(value) {
  return typeof value === "string" && /^[a-z0-9][a-z0-9._-]*$/i.test(value) ? value : null;
}

function validateBundle(language, mode, active, manifest, deck) {
  requireValue(active.manifest_version === "active-release/v1", "Unsupported active release pointer");
  requireValue(active.language === language.key && active.mode === mode, "Active release language or mode disagrees");
  requireValue(manifest.manifest_version === "release-manifest/v1", "Unsupported release manifest");
  requireValue(manifest.release_id === deck.release_id, "Manifest and deck release IDs disagree");
  requireValue(manifest.language === language.key && manifest.mode === mode, "Release language or mode disagrees");
  requireValue(deck.deck_version === "speech-deck/v1", "Unsupported Speech deck");
  requireValue(Array.isArray(deck.cards) && deck.cards.length === manifest.card_count, "Release card count is invalid");
  requireValue(
    typeof manifest.progress_namespace === "string" && manifest.progress_namespace.length > 0,
    "Release progress namespace is missing",
  );
}

export async function loadRelease(language, mode = "speech") {
  const base = `${language.release_base}/${mode}/`;
  const requested = safeReleaseId(new URLSearchParams(window.location.search).get("release"));
  const active = requested
    ? {
        manifest_version: "active-release/v1",
        language: language.key,
        mode,
        release_id: requested,
        manifest_path: `${requested}/manifest.json`,
      }
    : await fetchJson(`${base}active.json`, "Active release pointer");

  requireValue(safeReleaseId(active.release_id), "Active release ID is unsafe");
  requireValue(active.manifest_path === `${active.release_id}/manifest.json`, "Active manifest path is not canonical");
  const manifestUrl = new URL(active.manifest_path, new URL(base, window.location.origin));
  const manifest = await fetchJson(manifestUrl, "Release manifest");
  requireValue(manifest.deck_path === "deck.json", "Release deck path is not canonical");
  const deck = await fetchJson(new URL(manifest.deck_path, manifestUrl), "Speech deck");
  validateBundle(language, mode, active, manifest, deck);
  return Object.freeze({ active, manifest, deck, selectedExplicitly: Boolean(requested) });
}
