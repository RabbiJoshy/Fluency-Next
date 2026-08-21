const STORAGE_VERSION = "progress/v1";

function blankRecord() {
  return { correct: 0, wrong: 0, lastCorrect: 0, lastWrong: 0, lastSeen: 0, srsStage: 0 };
}

function validRecord(value) {
  return value && Object.keys(blankRecord()).every((key) => Number.isFinite(value[key]));
}

export function progressStatus(record) {
  if (!record || !record.lastSeen) return "unseen";
  return record.lastCorrect > record.lastWrong ? "known" : "review";
}

export function createProgressStore({ language, mode, namespace }) {
  const key = `fluency-next:${STORAGE_VERSION}:${namespace}:${language}:${mode}`;
  let records = {};
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      records = Object.fromEntries(Object.entries(parsed).filter(([, value]) => validRecord(value)));
    }
  } catch {
    records = {};
  }

  function persist() {
    try { localStorage.setItem(key, JSON.stringify(records)); } catch { /* memory-only fallback */ }
  }

  return Object.freeze({
    key,
    get(cardId) {
      return { ...blankRecord(), ...(records[cardId] || {}) };
    },
    status(cardId) {
      return progressStatus(records[cardId]);
    },
    answer(cardId, correct) {
      const previous = this.get(cardId);
      const timestamp = Math.max(Date.now(), previous.lastCorrect + 1, previous.lastWrong + 1);
      const next = { ...previous, lastSeen: timestamp };
      if (correct) {
        next.correct += 1;
        next.lastCorrect = timestamp;
        next.srsStage = Math.min(previous.srsStage + 1, 7);
      } else {
        next.wrong += 1;
        next.lastWrong = timestamp;
        next.srsStage = 0;
      }
      records[cardId] = next;
      persist();
      return { ...next };
    },
    summary(cardIds) {
      const result = { known: 0, review: 0, unseen: 0, total: cardIds.length };
      for (const cardId of cardIds) result[progressStatus(records[cardId])] += 1;
      return result;
    },
    reset() {
      records = {};
      try { localStorage.removeItem(key); } catch { /* memory-only fallback */ }
    },
  });
}
