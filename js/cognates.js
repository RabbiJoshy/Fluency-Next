// Which languages the learner already reads, and how transparent each deck
// word is to them.
//
// The deck used to carry one `cognate_score` per word, which could only ever
// mean "close to English". A learner who also reads Polish gets a large part of
// a Czech deck for free, and none of that was expressible. So the release now
// ships a score per known language and the learner says which ones apply.
//
//   cognate_scores: { en: 0.76, pl: 0.85 }
//
// There is no combining. Each known language is its own exclusion, deciding at
// its own cutoff whether it already gives the learner this word; a word leaves
// the deck if any of them says so. The scores are therefore never compared
// with one another, which is what lets Spanish keep its own hand-built number
// on its own scale without the two ever having to mean the same thing.
//
// Selecting nothing leaves every word in the deck, which is the honest default
// for someone who has not said what they read.
//
// The old scalar still works. Where a release predates this, `cognate_score`
// is read as the English entry, so Spanish is untouched.
import './state.js?v=20260825ak';

const SELECTED_KEY = 'fluency_known_languages_v1';

// Named here rather than fetched: the picker must render before the scores
// arrive, and a language code with no name is not something to show a learner.
const KNOWN_LANGUAGE_NAMES = {
    en: 'English',
    pl: 'Polish',
    es: 'Spanish',
    fr: 'French',
    pt: 'Portuguese',
    de: 'German',
    it: 'Italian',
    ru: 'Russian',
    sk: 'Slovak',
    uk: 'Ukrainian',
    nl: 'Dutch',
    sv: 'Swedish',
};

// surface (lowercased) -> { known language: score }
let cognateScores = null;
let cognateLanguages = [];
// The auto cutoff per known language, shipped with the scores because it is a
// property of the pair that produced them, not a user setting. An advanced
// override can come later; until then the words a slightly wrong number moves
// are not lost, only relocated to Extras.
let cognateThresholds = {};
let selectedKnownLanguages = null;

function readSelected() {
    if (selectedKnownLanguages) return selectedKnownLanguages;
    try {
        const saved = JSON.parse(localStorage.getItem(SELECTED_KEY) || 'null');
        if (Array.isArray(saved)) {
            selectedKnownLanguages = saved.filter(code => typeof code === 'string');
            return selectedKnownLanguages;
        }
    } catch (_) {
        // Blocked site data. Fall through to the default rather than failing:
        // the setting is a convenience, not something to lose the deck over.
    }
    // English is the language the glosses are already written in, so a learner
    // who has said nothing is at least reading English.
    selectedKnownLanguages = ['en'];
    return selectedKnownLanguages;
}

function writeSelected(codes) {
    selectedKnownLanguages = codes.slice();
    try {
        localStorage.setItem(SELECTED_KEY, JSON.stringify(selectedKnownLanguages));
    } catch (_) {}
}

function languageLabel(code) {
    return KNOWN_LANGUAGE_NAMES[code] || String(code || '').toUpperCase();
}

// The scores a release actually shipped. A language with no scores is never
// offered, so the picker cannot promise a filter that would do nothing.
function availableKnownLanguages() {
    return cognateLanguages.slice();
}

function activeKnownLanguages() {
    const available = new Set(cognateLanguages);
    return readSelected().filter(code => available.has(code));
}

// Does any language the learner reads already give them this word? Each is
// asked separately, at its own cutoff.
function isCognateKnown(item) {
    if (!item) return false;
    const perLanguage = item.cognate_scores;
    if (!perLanguage) {
        // Pre-contract release: one score, on its own scale, against the
        // slider that scale was calibrated for. Spanish lives here.
        return Number(item.cognate_score || 0) >= Number(globalThis.cognateThreshold || 0);
    }
    for (const code of activeKnownLanguages()) {
        const score = Number(perLanguage[code] || 0);
        const cutoff = Number(cognateThresholds[code] ?? globalThis.cognateThreshold ?? 1);
        if (score >= cutoff) return true;
    }
    return false;
}

// For display only — which language makes this word free, and how strongly.
// Never used to decide anything, because comparing two scales would be
// meaningless.
function strongestKnownLanguage(item) {
    const perLanguage = item && item.cognate_scores;
    if (!perLanguage) return null;
    let bestCode = null;
    let best = -1;
    for (const code of activeKnownLanguages()) {
        const score = Number(perLanguage[code] || 0);
        if (score >= Number(cognateThresholds[code] ?? 1) && score > best) {
            best = score;
            bestCode = code;
        }
    }
    return bestCode === null ? null : { code: bestCode, score: best };
}

// Attach shipped scores to the loaded vocabulary. Called once per deck load,
// before any filtering, so buildFilteredVocab sees a complete item.
function applyCognateScores(vocabularyData) {
    if (!Array.isArray(vocabularyData) || !cognateScores) return;
    for (const item of vocabularyData) {
        const scores = cognateScores[String(item.word || '').toLowerCase()];
        if (scores) item.cognate_scores = scores;
    }
}

async function loadCognateScores(langConfig) {
    cognateScores = null;
    cognateLanguages = [];
    cognateThresholds = {};
    const path = langConfig && langConfig.cognatesPath;
    if (!path) return;
    try {
        const response = await fetch(path, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const scores = payload && payload.scores;
        if (!scores || typeof scores !== 'object') throw new Error('no scores in cognate file');
        cognateScores = scores;
        cognateLanguages = Array.isArray(payload.known_languages)
            ? payload.known_languages.slice()
            : Object.keys(Object.values(scores)[0] || {});
        cognateThresholds = (payload.thresholds && typeof payload.thresholds === 'object')
            ? payload.thresholds
            : {};
    } catch (error) {
        // Absence is declared, not inferred: with no scores the picker stays
        // hidden and the deck keeps every word, rather than silently filtering
        // against whatever happened to be left in memory.
        console.warn('Cognate scores unavailable:', error);
        cognateScores = null;
        cognateLanguages = [];
        cognateThresholds = {};
    }
    renderKnownLanguagePicker();
}

// ---------------------------------------------------------------- the picker

function renderKnownLanguagePicker() {
    const container = document.getElementById('knownLanguagesContainer');
    const selector = document.getElementById('knownLanguagesSelector');
    if (!container || !selector) return;
    const available = availableKnownLanguages();
    // One language is not a choice — with English alone this is the old
    // behaviour and the picker would only be noise.
    if (available.length < 2) {
        container.style.display = 'none';
        return;
    }
    container.style.display = 'block';
    const active = new Set(activeKnownLanguages());
    selector.innerHTML = available.map(code => `
        <button type="button" class="known-language-btn${active.has(code) ? ' selected' : ''}"
                data-known-language="${code}" aria-pressed="${active.has(code)}">
            ${languageLabel(code)}
        </button>`).join('');
    selector.querySelectorAll('.known-language-btn').forEach(button => {
        button.addEventListener('click', () => toggleKnownLanguage(button.dataset.knownLanguage));
    });
}

function toggleKnownLanguage(code) {
    if (!code) return;
    const current = new Set(activeKnownLanguages());
    if (current.has(code)) {
        current.delete(code);
    } else {
        current.add(code);
    }
    writeSelected(availableKnownLanguages().filter(item => current.has(item)));
    renderKnownLanguagePicker();
    // The deck composition just changed, so every count on the setup screen is
    // now stale. These are the same refreshes a cognate-toggle click performs.
    globalThis.updateExclusionBars?.();
    globalThis.updateLevelSelector?.();
    globalThis.refreshFastMode?.();
}

globalThis.isCognateKnown = isCognateKnown;
globalThis.strongestKnownLanguage = strongestKnownLanguage;
globalThis.applyCognateScores = applyCognateScores;
globalThis.loadCognateScores = loadCognateScores;
globalThis.availableKnownLanguages = availableKnownLanguages;
globalThis.activeKnownLanguages = activeKnownLanguages;
globalThis.renderKnownLanguagePicker = renderKnownLanguagePicker;
globalThis.knownLanguageLabel = languageLabel;
