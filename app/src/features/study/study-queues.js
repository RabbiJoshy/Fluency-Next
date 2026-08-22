export function releaseCardMap(deck) {
  return new Map(deck.cards.map((card) => [card.card_id, card]));
}

export function findLevel(deck, levelId) {
  return deck.study_structure.levels.find((level) => level.level_id === levelId) || null;
}

export function findSet(deck, levelId, setId) {
  return findLevel(deck, levelId)?.sets.find((studySet) => studySet.set_id === setId) || null;
}

export function firstLevelAndSet(deck) {
  const level = deck.study_structure.levels[0];
  return { level, studySet: level.sets[0] };
}

export function buildStudyQueue(deck, progress, { levelId, setId, queueType }) {
  const cardMap = releaseCardMap(deck);
  const level = findLevel(deck, levelId);
  if (!level) throw new Error(`Unknown study level: ${levelId}`);
  let cardIds;
  if (queueType === "review") {
    cardIds = level.sets.flatMap((studySet) => studySet.card_ids)
      .filter((cardId) => progress.status(cardId) === "review");
  } else {
    const studySet = findSet(deck, levelId, setId);
    if (!studySet) throw new Error(`Unknown study set: ${setId}`);
    cardIds = queueType === "learn"
      ? studySet.card_ids.filter((cardId) => progress.status(cardId) === "unseen")
      : [...studySet.card_ids];
  }
  const cards = cardIds.map((cardId) => cardMap.get(cardId));
  if (cards.some((card) => !card)) throw new Error("Study queue references a missing release card");
  return Object.freeze({ cardIds: Object.freeze([...cardIds]), cards: Object.freeze(cards) });
}

export function nextUnseenSet(deck, progress, levelId, currentSetId) {
  const levelIndex = deck.study_structure.levels.findIndex((level) => level.level_id === levelId);
  if (levelIndex < 0) return null;
  const currentLevel = deck.study_structure.levels[levelIndex];
  const setIndex = currentLevel.sets.findIndex((studySet) => studySet.set_id === currentSetId);
  const remainingLevels = [
    { level: currentLevel, sets: currentLevel.sets.slice(setIndex + 1) },
    ...deck.study_structure.levels.slice(levelIndex + 1).map((level) => ({ level, sets: level.sets })),
  ];
  for (const { level, sets } of remainingLevels) {
    const studySet = sets.find((candidate) => candidate.card_ids.some((cardId) => progress.status(cardId) === "unseen"));
    if (studySet) return { levelId: level.level_id, setId: studySet.set_id, label: `${level.label} · ${studySet.label}` };
  }
  return null;
}
