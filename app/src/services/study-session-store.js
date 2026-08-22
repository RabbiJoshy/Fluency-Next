const SESSION_VERSION = "study-session/v1";

function validSnapshot(value) {
  return value
    && value.session_version === SESSION_VERSION
    && typeof value.release_id === "string"
    && typeof value.level_id === "string"
    && typeof value.set_id === "string"
    && ["learn", "review", "all"].includes(value.queue_type)
    && Array.isArray(value.card_ids)
    && value.card_ids.length > 0
    && value.card_ids.every((cardId) => typeof cardId === "string")
    && Number.isInteger(value.current_position)
    && value.current_position >= 0
    && ["front", "back"].includes(value.card_side)
    && ["target", "english"].includes(value.direction)
    && typeof value.automatic_speech === "boolean"
    && value.session_results
    && typeof value.session_results === "object";
}

export function createStudySessionStore({ language, mode, namespace }) {
  const key = `fluency-next:${SESSION_VERSION}:${namespace}:${language}:${mode}`;
  return Object.freeze({
    key,
    load() {
      try {
        const value = JSON.parse(localStorage.getItem(key) || "null");
        return validSnapshot(value) ? value : null;
      } catch {
        return null;
      }
    },
    save(snapshot) {
      const value = { ...snapshot, session_version: SESSION_VERSION, saved_at: new Date().toISOString() };
      if (!validSnapshot(value)) throw new Error("Refusing to save an invalid study session snapshot");
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* memory-only fallback */ }
      return value;
    },
    clear() {
      try { localStorage.removeItem(key); } catch { /* memory-only fallback */ }
    },
  });
}
