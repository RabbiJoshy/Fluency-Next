function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

function safeReleaseId(value) {
  return typeof value === "string" && /^[a-z0-9][a-z0-9._-]*$/i.test(value) ? value : null;
}

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return `sha256:${[...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

async function fetchJson(url, label, expectedContentId = null) {
  const response = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
  const text = await response.text();
  if (expectedContentId) requireValue(await sha256(text) === expectedContentId, `${label} hash does not match its manifest`);
  try { return JSON.parse(text); } catch { throw new Error(`${label} is not valid JSON`); }
}

function validateCatalog(language, mode, catalog) {
  requireValue(catalog.catalog_version === "release-catalog/v1", "Unsupported release catalog");
  requireValue(catalog.language === language.key && catalog.mode === mode, "Release catalog language or mode disagrees");
  requireValue(Array.isArray(catalog.candidates), "Release catalog candidates are invalid");
  const ids = new Set();
  for (const candidate of catalog.candidates) {
    requireValue(safeReleaseId(candidate.release_id) && !ids.has(candidate.release_id), "Release catalog contains an unsafe or duplicate candidate");
    requireValue(candidate.manifest_path === `${candidate.release_id}/manifest.json`, "Candidate manifest path is not canonical");
    ids.add(candidate.release_id);
  }
}

function validateBundle(language, mode, pointer, manifest, deck, composition) {
  requireValue(pointer.manifest_version === "active-release/v1", "Unsupported active release pointer");
  requireValue(pointer.language === language.key && pointer.mode === mode, "Release pointer language or mode disagrees");
  requireValue(manifest.manifest_version === "release-manifest/v1", "Unsupported release manifest");
  requireValue(composition.composition_version === "release-composition/v1", "Unsupported release composition");
  requireValue(manifest.release_id === deck.release_id && manifest.release_id === composition.release_id, "Release IDs disagree");
  requireValue(manifest.language === language.key && manifest.mode === mode, "Release language or mode disagrees");
  requireValue(deck.deck_version === "speech-deck/v1", "Unsupported Speech deck");
  requireValue(Array.isArray(deck.cards) && deck.cards.length === manifest.card_count, "Release card count is invalid");
  requireValue(composition.conflict_policy === "error", "Release does not fail on layer conflicts");
  requireValue(["none", "explicit_missing_only"].includes(composition.fallback_policy), "Release fallback policy is invalid");
}

export async function loadRelease(language, mode = "speech") {
  const base = `${language.release_base}/${mode}/`;
  const catalog = await fetchJson(`${base}catalog.json`, "Release catalog");
  validateCatalog(language, mode, catalog);
  const active = await fetchJson(`${base}active.json`, "Active release pointer");
  requireValue(active.release_id === catalog.active_release_id, "Catalog and active pointer disagree");
  const requested = safeReleaseId(new URLSearchParams(window.location.search).get("release"));
  const selectedId = requested || active.release_id;
  const candidate = catalog.candidates.find((item) => item.release_id === selectedId);
  requireValue(candidate, `Release ${selectedId || "(missing)"} is not an approved candidate`);
  const pointer = requested
    ? { manifest_version: "active-release/v1", language: language.key, mode, release_id: requested, manifest_path: candidate.manifest_path }
    : active;
  requireValue(pointer.manifest_path === `${selectedId}/manifest.json`, "Release manifest path is not canonical");
  const manifestUrl = new URL(pointer.manifest_path, new URL(base, window.location.origin));
  const manifest = await fetchJson(manifestUrl, "Release manifest");
  requireValue(manifest.deck_path === "deck.json" && manifest.composition_path === "composition.json", "Release asset paths are not canonical");
  const [deck, composition] = await Promise.all([
    fetchJson(new URL(manifest.deck_path, manifestUrl), "Speech deck", manifest.deck_content_id),
    fetchJson(new URL(manifest.composition_path, manifestUrl), "Release composition", manifest.composition_content_id),
  ]);
  validateBundle(language, mode, pointer, manifest, deck, composition);
  return Object.freeze({ active: pointer, manifest, deck, composition, catalog, candidate, selectedExplicitly: Boolean(requested) });
}
