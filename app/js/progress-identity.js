// Pure progress-identity helpers. Kept separate from the browser state module
// so the historical-ID bridge can be regression-tested without a DOM.

export function normalizeProgressSurface(value) {
    return String(value || '')
        .normalize('NFC')
        .trim()
        .toLocaleLowerCase()
        .replace(/\s+/g, ' ');
}

export function crossModeProgressId(fullId) {
    if (!fullId || fullId.length < 4) return null;
    if (fullId[2] === '0') return fullId.slice(0, 2) + '1' + fullId.slice(3);
    if (fullId[2] === '1') return fullId.slice(0, 2) + '0' + fullId.slice(3);
    return null;
}

function surfaceForId(surfaceById, fullId) {
    if (!surfaceById || !fullId) return '';
    if (typeof surfaceById.get === 'function') return surfaceById.get(fullId) || '';
    return surfaceById[fullId] || '';
}

export function matchingProgressRecords(
    progress,
    { fullId, surface = '', language = '', surfaceById = null } = {}
) {
    if (!progress || !fullId) return [];
    const result = [];
    const matchedIds = new Set();
    const add = id => {
        if (!id || matchedIds.has(id) || !progress[id]) return;
        matchedIds.add(id);
        result.push({ id, progress: progress[id] });
    };

    add(fullId);
    add(crossModeProgressId(fullId));

    // Current Speech releases use canonical surface-card prefixes while the
    // retained Lyrics catalogue and historical rows use older eight-hex IDs.
    // The stored word is the evidence-backed bridge: identity is the observed
    // language surface, never mode, artist, lemma, POS or sense.
    const normalizedSurface = normalizeProgressSurface(
        surface || surfaceForId(surfaceById, fullId)
    );
    if (!normalizedSurface) return result;

    for (const [id, row] of Object.entries(progress)) {
        if (matchedIds.has(id) || !row) continue;
        if (language && row.language !== language) continue;
        if (normalizeProgressSurface(row.word) !== normalizedSurface) continue;
        add(id);
    }
    return result;
}

function timestamp(value) {
    if (!value) return 0;
    const parsed = new Date(value).getTime();
    return Number.isFinite(parsed) ? parsed : 0;
}

function newestValue(records, field) {
    let latest = null;
    let latestTime = 0;
    for (const { progress } of records) {
        const candidateTime = timestamp(progress?.[field]);
        if (candidateTime >= latestTime && candidateTime > 0) {
            latest = progress[field];
            latestTime = candidateTime;
        }
    }
    return latest;
}

export function mergeProgressRecords(records) {
    if (!Array.isArray(records) || records.length === 0) return null;
    let newest = records[0].progress || {};
    let newestTime = -1;
    let correct = 0;
    let wrong = 0;
    for (const { progress = {} } of records) {
        correct += Math.max(0, Number(progress.correct) || 0);
        wrong += Math.max(0, Number(progress.wrong) || 0);
        const rowTime = Math.max(
            timestamp(progress.lastSeen),
            timestamp(progress.lastCorrect),
            timestamp(progress.lastWrong)
        );
        if (rowTime >= newestTime) {
            newest = progress;
            newestTime = rowTime;
        }
    }
    return {
        word: newest.word || records.find(record => record.progress?.word)?.progress.word || '',
        language: newest.language || records.find(record => record.progress?.language)?.progress.language || '',
        correct,
        wrong,
        lastCorrect: newestValue(records, 'lastCorrect'),
        lastWrong: newestValue(records, 'lastWrong'),
        lastSeen: newestValue(records, 'lastSeen'),
        // Review cadence follows the newest answer source. Summed lifetime
        // counts remain history and must not accidentally inflate SRS stage.
        srsStage: newest.srsStage
    };
}
