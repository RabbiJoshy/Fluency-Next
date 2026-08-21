async function fetchJson(url, label) {
  const response = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
  return response.json();
}

export async function loadLanguageRegistry() {
  const registry = await fetchJson("/config/languages.json", "Language registry");
  if (registry.registry_version !== "language-registry/v1" || !Array.isArray(registry.languages)) {
    throw new Error("Language registry is invalid");
  }
  const languages = new Map();
  for (const language of registry.languages) {
    if (!language.key || languages.has(language.key)) throw new Error("Language registry contains an invalid key");
    languages.set(language.key, Object.freeze({ ...language }));
  }
  return languages;
}
