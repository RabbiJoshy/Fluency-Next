// What a level is worth.
//
// Speech levels are a pure ordering: the inventory keeps each surface's rank
// and discards the count it was ranked by, so "Ranks 801–1,000" could say
// nothing about whether that band is worth studying. The release now ships each
// deck surface's share of the frequency corpus, and this turns a band of ranks
// into a figure a learner can act on.
//
// Two readings of the same data, because they answer different questions:
//
//   share  what fraction of speech this level accounts for
//   gain   what fraction of what you have NOT yet covered it accounts for
//
// Share is the honest headline and it decays hard — a fifteenth Czech level is
// 0.6%, because that is the shape of a power law and the first two hundred
// words really are half of everything said. Gain keeps a legible number all the
// way down (3.0% for the same band) by shrinking the denominator as the learner
// advances. Share is the default; gain is a setting.
import './state.js?v=20260825ak';

const MODE_KEY = 'fluency_coverage_mode_v1';

// surface (lowercased) -> fraction of the corpus
let shares = null;
let coverageMode = null;

function readMode() {
    if (coverageMode) return coverageMode;
    try {
        const saved = localStorage.getItem(MODE_KEY);
        if (saved === 'gain' || saved === 'share') {
            coverageMode = saved;
            return coverageMode;
        }
    } catch (_) {}
    coverageMode = 'share';
    return coverageMode;
}

function setCoverageMode(mode) {
    coverageMode = mode === 'gain' ? 'gain' : 'share';
    try {
        localStorage.setItem(MODE_KEY, coverageMode);
    } catch (_) {}
    return coverageMode;
}

function coverageAvailable() {
    return shares !== null;
}

async function loadCoverage(langConfig) {
    shares = null;
    const path = langConfig && langConfig.coveragePath;
    if (!path) return;
    try {
        const response = await fetch(path, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (!payload || typeof payload.shares !== 'object') throw new Error('no shares');
        shares = payload.shares;
    } catch (error) {
        // Absence is declared: with no shares the readout omits the figure
        // rather than showing a plausible-looking guess.
        console.warn('Coverage shares unavailable:', error);
        shares = null;
    }
    renderCoverageModeSwitch();
}

function shareOf(word) {
    if (!shares) return 0;
    return Number(shares[String(word || '').toLowerCase()] || 0);
}

// Samples are {word, stableRank}; bands are half-open [startRank, endRank) to
// match the range loader's contract everywhere else in setup.
function sumBand(samples, startRank, endRank) {
    let total = 0;
    for (const sample of samples || []) {
        const rank = Number(sample?.stableRank ?? sample?.rank);
        if (Number.isFinite(rank) && rank >= startRank && rank < endRank) {
            total += shareOf(sample.word);
        }
    }
    return total;
}

// The figure for one level, in whichever reading the learner has chosen.
// Returns null when there is nothing to say, so callers hide the element
// instead of printing a zero that would read as "this level is worthless".
function levelCoverage(samples, startRank, endRank) {
    if (!shares) return null;
    const band = sumBand(samples, startRank, endRank);
    if (band <= 0) return null;
    if (readMode() === 'share') return band;
    const before = sumBand(samples, 0, startRank);
    const remaining = 1 - before;
    return remaining > 0 ? band / remaining : null;
}

function coverageLabel() {
    // "of speech" rather than "of film and TV dialogue": the corpus is subtitle
    // text, but the longer phrase buys precision a learner cannot use.
    return readMode() === 'gain' ? 'of what you have left' : 'of speech';
}

// ------------------------------------------------------------- the switch

function renderCoverageModeSwitch() {
    const container = document.getElementById('coverageModeContainer');
    const selector = document.getElementById('coverageModeSelector');
    if (!container || !selector) return;
    // Nothing to choose between when the language ships no shares.
    container.style.display = coverageAvailable() ? 'block' : 'none';
    if (!coverageAvailable()) return;
    const mode = readMode();
    selector.querySelectorAll('.coverage-mode-btn').forEach(button => {
        const selected = button.dataset.coverage === mode;
        button.classList.toggle('selected', selected);
        button.setAttribute('aria-pressed', String(selected));
    });
    const example = document.getElementById('coverageModeExample');
    if (example) {
        example.textContent = mode === 'gain'
            ? 'A late level reads a few percent rather than under one.'
            : 'The first level is about half of everything said.';
    }
}

function initCoverageSwitch() {
    document.querySelectorAll('.coverage-mode-btn').forEach(button => {
        button.addEventListener('click', () => {
            setCoverageMode(button.dataset.coverage);
            renderCoverageModeSwitch();
            // The readout is rebuilt from the level list, so re-render it.
            globalThis.renderLevelSelector?.(globalThis.selectedLanguage);
        });
    });
    renderCoverageModeSwitch();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCoverageSwitch);
} else {
    initCoverageSwitch();
}

globalThis.renderCoverageModeSwitch = renderCoverageModeSwitch;
globalThis.loadCoverage = loadCoverage;
globalThis.coverageAvailable = coverageAvailable;
globalThis.levelCoverage = levelCoverage;
globalThis.coverageLabel = coverageLabel;
globalThis.coverageMode = readMode;
globalThis.setCoverageMode = setCoverageMode;
