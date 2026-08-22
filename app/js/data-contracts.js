// Small runtime guards at the generated-data boundary. Release builders own
// the full JSON schemas; the browser checks only the invariants it needs to
// render safely and reports failures with the exact source path.

function contractError(source, message) {
    const issue = {
        level: 'error',
        source: source || 'unknown source',
        message
    };
    window._dataContractIssues ||= [];
    window._dataContractIssues.push(issue);
    return new Error(`Data contract error in ${issue.source}: ${message}`);
}

export function validateVocabularyIndex(data, { source = 'vocabulary index' } = {}) {
    if (!Array.isArray(data) || data.length === 0) {
        throw contractError(source, 'expected a non-empty array of cards');
    }
    const ids = new Set();
    data.forEach((card, index) => {
        if (!card || typeof card !== 'object' || Array.isArray(card)) {
            throw contractError(source, `card ${index + 1} must be an object`);
        }
        if (typeof card.id !== 'string' || !card.id.trim()) {
            throw contractError(source, `card ${index + 1} has no stable id`);
        }
        if (ids.has(card.id)) {
            throw contractError(source, `duplicate card id ${card.id}`);
        }
        ids.add(card.id);
        if (typeof card.word !== 'string' || !card.word.trim()) {
            throw contractError(source, `card ${card.id} has no display word`);
        }
        if (!Array.isArray(card.meanings)) {
            throw contractError(source, `card ${card.id} has no meanings array`);
        }
    });
    return data;
}

export function validateExamplesSplit(data, { source = 'examples split' } = {}) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
        throw contractError(source, 'expected an object keyed by card id');
    }
    for (const [cardId, payload] of Object.entries(data)) {
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            throw contractError(source, `entry ${cardId} must be an object`);
        }
        for (const bucket of ['m', 'w', 'c', 's', 'r']) {
            if (bucket in payload && !Array.isArray(payload[bucket])) {
                throw contractError(source, `entry ${cardId}.${bucket} must be an array`);
            }
        }
    }
    return data;
}
