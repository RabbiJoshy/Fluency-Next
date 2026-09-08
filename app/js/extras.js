// Extras — the words the current settings keep OUT of the deck, kept browsable
// instead of vanishing.
//
// Speech mode has always dropped these silently. Artist mode already had an
// Extra scope (see artistItemMatchesScope in vocab.js), but that one is driven
// by the pipeline's `extra_category` and covers a different set: loanwords,
// proper nouns, noise. This is the speech-mode counterpart and it covers
// exactly two reasons, both of them learner-chosen rather than pipeline-tagged:
//
//   cognate  — excluded by the Cognates toggle
//   lemma    — a surface form folded into another card by Merge Lemmas
//
// Nothing here re-filters. buildFilteredVocab() has already stamped
// `_lemmaModeRepresentative` on every item by the time a deck exists, so this
// module reads the same state the filter used and reports what it discarded.
// That keeps one source of truth for the rules: if the filter changes, this
// follows without edits.
import './state.js?v=20260825ak';

// Every name below is read off globalThis rather than as a bare identifier.
// state.js defines these lazily via defineProperty, and this module can run
// before a deck exists, so a bare read is a ReferenceError rather than an
// undefined — which is exactly how the first version of this file broke.
const g = () => globalThis;

// Mirrors the two branches of getVocabularyExclusionReason() that a learner
// controls. Deliberately NOT imported from vocab.js — that module exports
// nothing, and duplicating two predicates is cheaper than widening its surface.
function cognateExtra(item) {
    // The same decision the deck filter makes: each known language judged at
    // its own cutoff, with the legacy scalar and slider for older releases.
    const decide = g().isCognateKnown;
    const known = decide
        ? Boolean(decide(item))
        : Number(item.cognate_score || 0) >= g().cognateThreshold;
    return g().excludeCognates && g().cognateFieldAvailable && known;
}

function lemmaExtra(item) {
    if (!g().useLemmaMode || !g().lemmaFieldAvailable) return false;
    const runtimeRepresentative = item._lemmaModeRepresentative;
    return runtimeRepresentative === false
        || (runtimeRepresentative === undefined && item.most_frequent_lemma_instance !== true);
}

function lemmaKeyOf(item) {
    return String(item?.lemma || '').normalize('NFC').toLocaleLowerCase('es').trim();
}

function firstTranslation(item) {
    const meaning = (item?.meanings || []).find(m => String(m?.translation || '').trim());
    return meaning ? meaning.translation.trim() : '';
}

// A merged form is only meaningful next to the card that swallowed it, so map
// each lemma to the surviving representative before rendering.
function representativesByLemma(items) {
    const hosts = new Map();
    for (const item of items) {
        if (item._lemmaModeRepresentative !== true) continue;
        const key = lemmaKeyOf(item);
        if (key && !hosts.has(key)) hosts.set(key, item);
    }
    return hosts;
}

function collectExtras() {
    const empty = { cognates: [], lemmas: [] };
    // The full loaded vocabulary, stamped by the last buildFilteredVocab pass.
    // Two routes reach it and they do not overlap: on the setup screen only
    // updateExclusionBars() holds it (it publishes the snapshot), and once a
    // deck is built loadVocabularyData() caches it. `vocabularyData` itself is
    // a local in both, never a global.
    const vocab = g().setupVocabularySnapshot || g().cachedVocabularyData;
    if (!Array.isArray(vocab) || vocab.length === 0) return empty;
    // Artist mode has its own Extra scope with its own categories; showing a
    // second, differently-defined Extras panel there would be two answers to
    // the same question.
    if (g().activeArtist) return empty;

    const hosts = representativesByLemma(vocab);
    const cognates = [];
    const lemmas = [];
    for (const item of vocab) {
        if (!item || !item.word || item.duplicate) continue;
        if (cognateExtra(item)) {
            cognates.push({ item, mergedInto: null });
            continue;
        }
        if (lemmaExtra(item)) {
            const host = hosts.get(lemmaKeyOf(item));
            // A form whose host did not survive the other filters is not a
            // merge — it is simply absent, and claiming otherwise would be a
            // provenance lie.
            if (host && host !== item) lemmas.push({ item, mergedInto: host });
        }
    }
    const byRank = (a, b) => (a.item.rank ?? Infinity) - (b.item.rank ?? Infinity);
    cognates.sort(byRank);
    lemmas.sort(byRank);
    return { cognates, lemmas };
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

// With more than one known language a bare number says nothing about why the
// word is free, so name the language that made it so.
function cognateNote(item) {
    if (!item.cognate_scores) return Number(item.cognate_score || 0).toFixed(2);
    const strongest = g().strongestKnownLanguage?.(item);
    if (!strongest) return '';
    const label = g().knownLanguageLabel ? g().knownLanguageLabel(strongest.code) : strongest.code;
    return `${escapeHtml(label)} ${strongest.score.toFixed(2)}`;
}

function renderRows(entries, kind) {
    if (entries.length === 0) return '';
    return entries.map(({ item, mergedInto }) => {
        const translation = firstTranslation(item);
        // Cognates carry a score the learner can move with the sensitivity
        // setting, so show it rather than repeating the section's blurb on
        // every row. A merged form's useful fact is which card absorbed it.
        const note = kind === 'cognate'
            ? cognateNote(item)
            : `merged into <strong>${escapeHtml(mergedInto.word)}</strong>`;
        return `<li class="extras-row">
            <span class="extras-word">${escapeHtml(item.word)}</span>
            <span class="extras-translation">${escapeHtml(translation)}</span>
            <span class="extras-note${kind === 'cognate' ? ' extras-score' : ''}">${note}</span>
        </li>`;
    }).join('');
}

function renderExtras() {
    const { cognates, lemmas } = collectExtras();
    const body = document.getElementById('extrasBody');
    if (!body) return { cognates, lemmas };

    const sections = [];
    if (cognates.length > 0) {
        sections.push(`<section class="extras-section">
            <h4>Cognates <span class="extras-count">${cognates.length}</span></h4>
            <p class="extras-blurb">Excluded because they resemble their translation closely enough to
            recognise for free. Switch Cognates to Include to study them.</p>
            <ul class="extras-list">${renderRows(cognates, 'cognate')}</ul>
        </section>`);
    }
    if (lemmas.length > 0) {
        sections.push(`<section class="extras-section">
            <h4>Merged forms <span class="extras-count">${lemmas.length}</span></h4>
            <p class="extras-blurb">Still in the deck, on the card for their base form. Switch Merge
            Lemmas off to study each form as its own card.</p>
            <ul class="extras-list">${renderRows(lemmas, 'lemma')}</ul>
        </section>`);
    }
    body.innerHTML = sections.length > 0
        ? sections.join('')
        : `<p class="extras-empty">Nothing is being excluded. Both Merge Lemmas and Cognates are
           set to keep every word in the deck.</p>`;
    return { cognates, lemmas };
}

// The button is only honest when there is something behind it, so its label
// carries the count and it hides itself when the current settings exclude
// nothing.
function refreshExtrasButton() {
    const button = document.getElementById('extrasBtn');
    if (!button) return;
    const { cognates, lemmas } = collectExtras();
    const total = cognates.length + lemmas.length;
    button.style.display = total > 0 ? 'inline-flex' : 'none';
    button.textContent = total === 1 ? '1 word set aside' : `${total} words set aside`;
}

function openExtras() {
    renderExtras();
    document.getElementById('extrasModal')?.classList.remove('hidden');
}

function closeExtras() {
    document.getElementById('extrasModal')?.classList.add('hidden');
}

function initExtras() {
    document.getElementById('extrasBtn')?.addEventListener('click', openExtras);
    document.getElementById('closeExtrasModal')?.addEventListener('click', closeExtras);
    document.getElementById('extrasModal')?.addEventListener('click', event => {
        if (event.target?.id === 'extrasModal') closeExtras();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeExtras();
    });
    refreshExtrasButton();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initExtras);
} else {
    initExtras();
}

// The toggles that decide what lands here live in ui.js and re-render the
// level info lines when they change; there is no shared event for that, so the
// count is refreshed on demand by whoever changes a setting.
globalThis.refreshExtrasButton = refreshExtrasButton;
globalThis.openExtras = openExtras;
