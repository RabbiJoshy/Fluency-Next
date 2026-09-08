// Fast mode for the setup page.
//
// Step 2 used to present Merge Lemmas and Cognates as two always-open toggle
// pairs with their own info lines. Each is a real choice, but neither is one a
// first-time learner can make before seeing a card, and together they make the
// landing page read like a settings screen. So they collapse behind one
// disclosure that states what they are currently set to.
//
// Nothing about the toggles themselves changes: ui.js still owns their state,
// their visibility per language capability, and their info lines. This module
// only decides whether the row they sit in is expanded, and keeps a one-line
// summary honest. If both toggles are unavailable for a language, the
// disclosure hides itself rather than opening onto an empty box.
import './state.js?v=20260825ak';

const EXPANDED_KEY = 'fluency_setup_options_expanded_v1';

function readExpanded() {
    try {
        return localStorage.getItem(EXPANDED_KEY) === '1';
    } catch (_) {
        return false;
    }
}

function writeExpanded(expanded) {
    try {
        localStorage.setItem(EXPANDED_KEY, expanded ? '1' : '0');
    } catch (_) {
        // Private browsing and blocked site data both land here. The
        // disclosure still works for this visit; it just will not be
        // remembered, which is the right way to fail for a convenience.
    }
}

function isVisible(element) {
    return Boolean(element) && element.style.display !== 'none';
}

// Reads the toggles rather than the state variables so the summary cannot
// drift from what the buttons show.
function summaryText() {
    const parts = [];
    const lemmaVisible = isVisible(document.getElementById('lemmaToggleContainer'));
    const cognateVisible = isVisible(document.getElementById('cognateToggleContainer'));
    if (lemmaVisible) {
        const on = document.querySelector('.lemma-toggle-btn.selected')?.dataset.lemma === 'on';
        parts.push(`Merge lemmas ${on ? 'on' : 'off'}`);
    }
    if (cognateVisible) {
        const exclude = document.querySelector('.cognate-toggle-btn.selected')?.dataset.cognate === 'exclude';
        parts.push(`cognates ${exclude ? 'excluded' : 'included'}`);
    }
    return parts.join(' · ');
}

function setExpanded(expanded, { remember = true } = {}) {
    const toggle = document.getElementById('setupOptionsToggle');
    const body = document.getElementById('setupOptionsBody');
    if (!toggle || !body) return;
    body.hidden = !expanded;
    toggle.setAttribute('aria-expanded', String(expanded));
    if (remember) writeExpanded(expanded);
}

function refresh() {
    const wrapper = document.getElementById('setupOptions');
    const summary = document.getElementById('setupOptionsSummary');
    if (!wrapper) return;
    const anyAvailable = isVisible(document.getElementById('lemmaToggleContainer'))
        || isVisible(document.getElementById('cognateToggleContainer'));
    wrapper.style.display = anyAvailable ? 'block' : 'none';
    if (summary) summary.textContent = summaryText();
    globalThis.refreshExtrasButton?.();
}

function init() {
    const toggle = document.getElementById('setupOptionsToggle');
    if (!toggle) return;

    setExpanded(readExpanded(), { remember: false });
    toggle.addEventListener('click', () => {
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        setExpanded(!expanded);
    });

    // ui.js and main.js show and hide the two containers directly, in about a
    // dozen places, and none of them raises an event. Watching the attribute
    // they actually set is the one hook that cannot fall out of sync with
    // them, and it costs nothing to leave running.
    const observer = new MutationObserver(refresh);
    for (const id of ['lemmaToggleContainer', 'cognateToggleContainer']) {
        const element = document.getElementById(id);
        if (element) observer.observe(element, { attributes: true, attributeFilter: ['style'] });
    }

    // Selecting a toggle rewrites the `selected` class on its siblings; the
    // summary and the extras count both follow from that.
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

globalThis.refreshSetupOptions = refresh;
