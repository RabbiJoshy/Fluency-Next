// Fast mode — one decision on the setup screen, the parts behind it on a page
// of their own.
//
// Step 2 used to present Merge Lemmas and Cognates as two toggle pairs sitting
// under the level picker. Both are real choices, but neither is one a learner
// can make before they have seen a card, and together they made the landing
// screen read like a settings panel. They now sum to a single question — do you
// want fewer cards for the same coverage? — with the individual controls, their
// counts, and the explanation on the Fast mode page.
//
// This module owns only that summing. The individual toggles keep their own
// handlers in ui.js: turning fast mode on CLICKS them rather than setting the
// state directly, so there is one implementation of what changing each setting
// means and no second copy to drift.
//
// Applies to Speech and Lyrics alike. A language whose release supports only one
// of the two parts still gets fast mode — it just moves the part it has, and the
// page says which part is missing.
import './state.js?v=20260825ak';

function isVisible(element) {
    return Boolean(element) && element.style.display !== 'none';
}

function lemmaAvailable() {
    return isVisible(document.getElementById('lemmaToggleContainer'));
}

function cognateAvailable() {
    return isVisible(document.getElementById('cognateToggleContainer'));
}

// Read the buttons rather than the state variables: what the learner sees is
// the truth, and this cannot drift from it.
function lemmaOn() {
    return document.querySelector('.lemma-toggle-btn.selected')?.dataset.lemma === 'on';
}

function cognatesExcluded() {
    return document.querySelector('.cognate-toggle-btn.selected')?.dataset.cognate === 'exclude';
}

// Fast mode is on when every part the release supports is on. With one part
// available it is that part's state; with neither, there is nothing to report.
function currentState() {
    const parts = [];
    if (lemmaAvailable()) parts.push(lemmaOn());
    if (cognateAvailable()) parts.push(cognatesExcluded());
    if (parts.length === 0) return 'unavailable';
    if (parts.every(Boolean)) return 'on';
    if (parts.every(part => !part)) return 'off';
    // A learner who set the parts individually is in neither state, and saying
    // "on" or "off" would be a lie about their deck.
    return 'custom';
}

// Describes only the parts this release supports. Czech has no lemma mapping,
// so a fixed "forms merged, familiar words set aside" would claim something
// the deck cannot do.
function summaryText() {
    const state = currentState();
    if (state === 'unavailable') return '';
    if (state === 'on') return 'On · less repetition';
    if (state === 'off') return 'Off · full deck';
    return 'Custom';
}

// Turning fast mode on or off drives the real controls, so every side effect
// they own — recounting the deck, invalidating the prepared vocabulary,
// re-rendering the level bands — happens exactly once and exactly as it does
// when the learner changes them by hand.
function applyFastMode(on) {
    if (lemmaAvailable() && lemmaOn() !== on) {
        document.querySelector(`.lemma-toggle-btn[data-lemma="${on ? 'on' : 'off'}"]`)?.click();
    }
    if (cognateAvailable() && cognatesExcluded() !== on) {
        document.querySelector(
            `.cognate-toggle-btn[data-cognate="${on ? 'exclude' : 'include'}"]`
        )?.click();
    }
    // The clicks above each schedule their own refresh; this only restates what
    // the buttons now say.
    setTimeout(refresh, 0);
}

function refresh() {
    const wrapper = document.getElementById('setupOptions');
    if (!wrapper) return;
    const state = currentState();
    wrapper.style.display = state === 'unavailable' ? 'none' : 'block';

    document.querySelectorAll('.fast-mode-btn').forEach(button => {
        const selected = button.dataset.fast === state;
        button.classList.toggle('selected', selected);
        button.setAttribute('aria-pressed', String(selected));
    });
    const summary = document.getElementById('fastModeSummary');
    if (summary) summary.textContent = summaryText();

    const availability = document.getElementById('fastModeAvailability');
    if (availability) {
        const missing = [];
        if (!lemmaAvailable()) missing.push('merging word forms');
        if (!cognateAvailable()) missing.push('skipping familiar words');
        // Absence is stated rather than left as a control that silently is not
        // there, so a learner is not left wondering what they are missing.
        availability.textContent = missing.length
            ? `This language does not yet support ${missing.join(' or ')}.`
            : '';
        availability.style.display = missing.length ? '' : 'none';
    }
    globalThis.refreshExtrasButton?.();
}

function openFastModePage() {
    refresh();
    document.getElementById('fastModeModal')?.classList.remove('hidden');
}

function closeFastModePage() {
    document.getElementById('fastModeModal')?.classList.add('hidden');
}

function init() {
    document.querySelectorAll('.fast-mode-btn').forEach(button => {
        button.addEventListener('click', () => applyFastMode(button.dataset.fast === 'on'));
    });
    document.getElementById('fastModeDetailBtn')?.addEventListener('click', openFastModePage);
    document.getElementById('closeFastModeModal')?.addEventListener('click', closeFastModePage);
    document.getElementById('fastModeModal')?.addEventListener('click', event => {
        if (event.target?.id === 'fastModeModal') closeFastModePage();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeFastModePage();
    });

    // ui.js and main.js show and hide the two containers directly, in about a
    // dozen places, and none of them raises an event. Watching the attribute
    // they actually set is the one hook that cannot fall out of sync.
    const observer = new MutationObserver(refresh);
    for (const id of ['lemmaToggleContainer', 'cognateToggleContainer']) {
        const element = document.getElementById(id);
        if (element) observer.observe(element, { attributes: true, attributeFilter: ['style'] });
    }
    document.querySelectorAll('.lemma-toggle-btn, .cognate-toggle-btn').forEach(button => {
        button.addEventListener('click', () => setTimeout(refresh, 0));
    });

    refresh();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

globalThis.refreshFastMode = refresh;
globalThis.openFastModePage = openFastModePage;
