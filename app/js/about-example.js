// About → "See Example": an annotated walkthrough of real flashcards.
//
// The About copy already carries two small auto-playing demo cards
// (`demo://normal` / `demo://artist`, built in auth.js). Those show the card
// moving; they deliberately say nothing about what any part of it means.
// This module is the other half: a stepped tour where the card sits still,
// every element on it is numbered, and the numbers are explained beside it.
//
// Two constraints shape the implementation:
//
//   1. "Exact replica". The card is built from the same class names and the
//      same inline styles that updateCard() in flashcards.js emits, so it
//      inherits the real card's CSS rather than a lookalike stylesheet. Only
//      SIZE is overridden (see .about-example-card-inner in style.css), the
//      same trick the inline demo cards use.
//   2. "Spotify needs to work". The Spotify button is not a picture of a
//      button — it calls the real window.spotifyPlayTrack() with a real track
//      id and a real lyric timestamp, and the Spotify module handles the
//      login hand-off itself when the visitor isn't connected yet. Track ids
//      and timestamps below are lifted from Artists/spotify_tracks.json and
//      the Bad Bunny deck, so they play the actual line on the actual song.
//
// Everything else about the card is inert on purpose: no progress is written,
// no deck state is touched, nothing here needs the app to have loaded a
// vocabulary. The walkthrough works for a logged-out visitor landing on
// `?about=1`, which is the main audience for it.

// ---------------------------------------------------------------------------
// Demo cards — real entries, real lyrics, real track ids.
// ---------------------------------------------------------------------------
//
// `cielo` is a genuine Bad Bunny deck entry — rank, line count, meanings,
// percentages, lyrics and timestamps all read out of the built deck rather
// than written for the walkthrough. `tem` is curated from the live Portuguese
// speech release because its Wiktionary senses demonstrate the compact
// metadata and cross-card-reference treatment that the old `aunque` mock did
// not contain.

const ABOUT_EXAMPLE_CARDS = {
    // Chosen for the quality of its sense assignment, not at random. `fuego`
    // was here first and read badly: its "light (for smoking)" row was
    // illustrated by "Fuego, desde que te vi me puse roja" and its "passion"
    // row by "me voy a fuego" — an idiom meaning "I go all out". Both are
    // real output of the current classifier, and a visitor who reads the
    // English can see they don't demonstrate the meaning claimed. A showcase
    // has to be a case the system gets right; `cielo` splits cleanly into two
    // concrete meanings a non-Spanish-speaker can check from the translation
    // alone. Revisit when sense assignment improves.
    cielo: {
        mode: 'lyrics',
        word: 'cielo',
        pos: 'NOUN',
        rank: 344,
        corpusCount: 33,
        meanings: [
            {
                pos: 'NOUN',
                translation: 'heaven',
                context: 'religious',
                pct: 70,
                examples: [
                    {
                        target: 'El cielo en el infierno, nadie va a entender',
                        english: 'Heaven in hell, no one will understand',
                        song: 'Volando (Remix)',
                        trackId: '0G2zPzWqVjR68iNPmx2TBe',
                        positionMs: 220310,
                        vocalists: 'Bad Bunny',
                    },
                    {
                        target: 'Lo subo al cielo, yo soy su Messiah',
                        english: 'I take him to heaven, I am his Messiah',
                        song: 'LA NOCHE DE ANOCHE',
                        trackId: '2XIc1pqjXV3Cr2BQUGNBck',
                        positionMs: 137190,
                        vocalists: 'ROSALÍA',
                    },
                    {
                        target: 'Ya estoy acostumbra’o a estar siempre en el cielo',
                        english: 'I’m already used to always being in heaven',
                        song: 'Estamos Bien',
                        trackId: '2OWVCFTolecLiGZPquvWvT',
                        positionMs: 68170,
                        vocalists: null,
                    },
                ],
            },
            {
                pos: 'NOUN',
                translation: 'sky',
                context: 'firmament',
                pct: 30,
                examples: [
                    {
                        target: 'Y ver pa’l cielo a ver si te veo caer',
                        english: 'And I look to the sky to see if I see you fall',
                        song: 'BAILE INoLVIDABLE',
                        trackId: '2lTm559tuIvatlT1u0JYG2',
                        positionMs: 118690,
                        vocalists: null,
                    },
                ],
            },
        ],
    },

    tem: {
        mode: 'speech',
        word: 'tem',
        pos: 'VERB',
        rank: 47,
        corpusCount: 1326,
        defaultMeaningIndex: 2,
        meanings: [
            {
                pos: 'VERB',
                translation: 'to have (to possess or hold something)',
                context: 'to be in possession of something',
                pct: 50,
                metadata: [
                    { short: 'tr.', full: 'transitive', family: 'construction' },
                ],
                examples: [
                    {
                        target: 'E isso tem muito mais do que isso!',
                        english: 'And this has much more than that!',
                        sourceLabel: 'Speech example',
                    },
                ],
            },
            {
                pos: 'VERB',
                translation: 'to have to; must',
                context: null,
                pct: 30,
                metadata: [
                    { short: 'aux.', full: 'auxiliary', family: 'construction' },
                    { short: '+ de/que + infinitive', full: 'with de or que + infinitive', family: 'construction' },
                ],
                examples: [
                    {
                        target: 'Mas não tem de o ser.',
                        english: "But it doesn't have to be.",
                        sourceLabel: 'Speech example',
                    },
                ],
            },
            {
                pos: 'VERB',
                translation: 'there be (to exist physically or abstractly)',
                context: null,
                pct: 15,
                metadata: [
                    { short: 'impers.', full: 'impersonal', family: 'construction' },
                    { short: 'tr.', full: 'transitive', family: 'construction' },
                    { short: 'Brazil', full: 'Brazil', family: 'register' },
                    { short: 'informal', full: 'informal', family: 'register' },
                ],
                examples: [
                    {
                        target: 'Aqui tem tudo o que precisamos.',
                        english: 'Everything we need is here.',
                        sourceLabel: 'Wiktionary example',
                    },
                ],
            },
            {
                pos: 'VERB',
                translation: 'See ter de, ter que.',
                references: ['ter de', 'ter que'],
                context: null,
                pct: 5,
                metadata: [
                    { short: 'aux.', full: 'auxiliary', family: 'construction' },
                    { short: '+ de/que + infinitive', full: 'with de or que + infinitive', family: 'construction' },
                ],
                examples: [
                    {
                        target: 'Não, ele tem de fazer isto.',
                        english: "No, he's got to do this.",
                        sourceLabel: 'Speech example',
                    },
                ],
            },
        ],
    },
};

const CARD_WALKTHROUGH_SEEN_KEY = 'fluencyCardWalkthroughSeenV1';
const LEGACY_CARD_WALKTHROUGH_PROMPT_KEY = 'fluencyCardWalkthroughPromptV1';

function hasSeenCardWalkthrough() {
    try {
        return localStorage.getItem(CARD_WALKTHROUGH_SEEN_KEY) === '1'
            || localStorage.getItem(LEGACY_CARD_WALKTHROUGH_PROMPT_KEY) === '1';
    } catch (_) {
        return false;
    }
}

function rememberCardWalkthrough() {
    try {
        localStorage.setItem(CARD_WALKTHROUGH_SEEN_KEY, '1');
        // The older first-flip prompt reads this key. Marking both makes every
        // route into the same tour converge on one durable onboarding state.
        localStorage.setItem(LEGACY_CARD_WALKTHROUGH_PROMPT_KEY, '1');
    } catch (_) {}
}

// ---------------------------------------------------------------------------
// Decks and their annotations
// ---------------------------------------------------------------------------
//
// Two things are being selected independently, and conflating them was the
// first version's mistake:
//
//   * The DECK (Lyrics / Speech) — chosen by the tab. This is the only thing
//     the tab does.
//   * The FACE (back / front) — chosen by flipping the card, like anywhere
//     else in the app.
//
// Annotations belong to a FACE, not to a tab step. Flip the card and the whole
// numbered set is replaced by the one describing the side now showing;
// otherwise the labels stay behind pointing at elements that turned away.
//
// The back opens by default. It carries the senses, the shares and the
// evidence — everything the app is actually for. The front is a prompt.
//
// `anchor` is a CSS selector resolved inside the rendered card; `side` puts
// the note in the left or right column and pins its badge to the matching edge
// of the element, so a badge never has to cross the card to reach its note.

const ABOUT_EXAMPLE_DECKS = [
    {
        id: 'lyrics',
        card: 'cielo',
        tab: 'Lyrics',
        faces: {
            back: {
                title: 'What the app actually teaches you',
                blurb: 'This is the answer side of a flashcard. Instead of giving one '
                     + 'translation and hiding the rest, it shows every meaning the word has, '
                     + 'how often each one is really used, and a line from a song using it.',
                notes: [
                    {
                        side: 'left',
                        anchor: '.back-headword',
                        title: 'The word',
                        text: 'Repeated at the top so you keep your place reading down.',
                    },
                    {
                        side: 'right',
                        anchor: '.pos-section-head',
                        title: 'Meaning section',
                        text: 'The part of speech labels the whole group once. Its colour carries '
                            + 'through the rows, without repeating a tag beside every meaning.',
                    },
                    {
                        side: 'left',
                        anchor: '.meanings-scroll .meaning-row:nth-child(1)',
                        title: 'Its most common meaning',
                        text: '“heaven” is how this word is used about 70% of the time across '
                            + 'his songs. The highlighted row is the one you’re looking at.',
                    },
                    {
                        side: 'left',
                        anchor: '.meanings-scroll .meaning-row:nth-child(2)',
                        title: 'Its other meanings',
                        text: 'Tap one to switch. The lyric underneath changes to a line where '
                            + 'that meaning is the one being used.',
                        interactive: true,
                    },
                    {
                        side: 'right',
                        anchor: '.about-example-pct',
                        title: 'How often each is used',
                        text: 'Every line in his songs containing this word was read and sorted '
                            + 'by meaning, so these are his real proportions — not a dictionary’s '
                            + 'ordering.',
                    },
                    {
                        side: 'right',
                        anchor: '.example-word-highlight',
                        title: 'The word in a real line',
                        text: 'Marked inside the lyric, in whatever form it takes there.',
                    },
                    {
                        side: 'left',
                        anchor: '.translation',
                        title: 'The line in English',
                        text: 'So the whole lyric makes sense without looking anything up.',
                    },
                    {
                        side: 'left',
                        anchor: '.example-song-credit',
                        title: 'Which song it’s from',
                        text: 'Plus any guest artist singing that line.',
                    },
                    {
                        side: 'right',
                        anchor: '.spotify-btn',
                        title: 'Play it — really',
                        text: 'A working button. It plays the song in your own Spotify, starting '
                            + 'at the second that line is sung. Spotify Premium required.',
                        interactive: true,
                    },
                    {
                        side: 'right',
                        anchor: '.example-counter-group',
                        title: 'More than one example',
                        text: 'Where a meaning turns up in several songs, tap the lyric to move '
                            + 'through them.',
                        interactive: true,
                    },
                ],
            },
            front: {
                title: 'The question side',
                blurb: 'You see the word on its own and try to recall it. The two figures '
                     + 'underneath say how common it is, which is how the app decides the order '
                     + 'you meet words in.',
                notes: [
                    {
                        side: 'left',
                        anchor: '.card-word',
                        title: 'The word',
                        text: 'Try to recall what it means before turning the card over. The '
                            + 'effort of remembering is what makes it stick.',
                    },
                    {
                        side: 'left',
                        anchor: '.card-rank-label',
                        title: 'How common it is',
                        text: 'The 344th most-used word across his songs. Words are taught in '
                            + 'that order — the ones you’ll hear most, first.',
                    },
                    {
                        side: 'right',
                        anchor: '.card-pos-list',
                        title: 'Part of speech',
                        text: 'A compact hint on the question side. On the answer side it becomes '
                            + 'the heading for the meanings it belongs to.',
                    },
                    {
                        side: 'right',
                        anchor: '.card-freq-label',
                        title: 'How much evidence there is',
                        text: 'The number of lines in his songs that use this word.',
                    },
                ],
            },
        },
    },

    {
        id: 'speech',
        card: 'tem',
        tab: 'Speech',
        faces: {
            back: {
                title: 'A dictionary-rich card without the dictionary clutter',
                blurb: 'This Portuguese speech card has several Wiktionary senses. The overview '
                     + 'stays brief; the selected sense reveals its full wording and compact '
                     + 'grammar, register and region details beside the matching sentence.',
                notes: [
                    {
                        side: 'left',
                        anchor: '.back-headword',
                        title: 'The surface form',
                        text: '<em>tem</em> is shown as it actually appears in speech. The card can '
                            + 'still connect its senses to the dictionary headword <em>ter</em>.',
                    },
                    {
                        side: 'left',
                        anchor: '.pos-section-head',
                        title: 'A clean sense overview',
                        text: 'Parenthetical notes stay out of this header. It fits every complete '
                            + 'sense label it can, then uses one unambiguous <em>+N</em> count.',
                        interactive: true,
                    },
                    {
                        side: 'left',
                        anchor: '.meaning-row.is-current-sense',
                        title: 'One fully open subsense',
                        text: 'The selected row grows to show the full definition. Other rows are '
                            + 'compact choices, and another part of speech stays closed.',
                        interactive: true,
                    },
                    {
                        side: 'left',
                        anchor: '.sense-cross-reference',
                        title: 'References become navigation',
                        text: 'A Wiktionary “See” target is a real card link in the app, instead '
                            + 'of dead editorial text.',
                    },
                    {
                        side: 'right',
                        anchor: '.sense-metadata-list',
                        title: 'Metadata, in a stable order',
                        text: 'Grammar and construction come first, then companion words, register, '
                            + 'region and domain. Tap <em>+N</em> only when there is more.',
                        interactive: true,
                    },
                    {
                        side: 'right',
                        anchor: '.about-example-pct',
                        title: 'Usage share stays separate',
                        text: 'Dictionary examples and metadata do not change these percentages; '
                            + 'they describe the speech evidence assigned to each sense.',
                    },
                    {
                        side: 'right',
                        anchor: '.example-word-highlight',
                        title: 'The matching sentence',
                        text: 'Changing the active sense changes this sentence, making the link '
                            + 'between the meaning and its evidence explicit.',
                    },
                    {
                        side: 'right',
                        anchor: '.example-song-credit',
                        title: 'Examples may come from two places',
                        text: 'Speech evidence and dictionary examples can both help, while only '
                            + 'the speech evidence contributes to usage share.',
                    },
                ],
            },
            front: {
                title: 'The question side, away from music',
                blurb: 'Identical to a song card, with one number swapped.',
                notes: [
                    {
                        side: 'left',
                        anchor: '.card-word',
                        title: 'The word',
                        text: 'The same prompt, whichever set of cards you’re in.',
                    },
                    {
                        side: 'left',
                        anchor: '.card-rank-label',
                        title: 'How common it is',
                        text: 'The 47th most-used form in Portuguese film and TV dialogue.',
                    },
                    {
                        side: 'right',
                        anchor: '.card-pos-list',
                        title: 'Part of speech',
                        text: 'A compact hint here; on the back, the verb heading organises all '
                            + 'of the visible subsenses.',
                    },
                    {
                        side: 'right',
                        anchor: '.card-freq-label',
                        title: 'The figure that changes',
                        text: 'How often it appears per million words of dialogue. On a song card '
                            + 'this slot counts lyric lines instead.',
                    },
                ],
            },
        },
    },
];

// ---------------------------------------------------------------------------
// Card rendering — mirrors updateCard() in flashcards.js.
// ---------------------------------------------------------------------------

const POS_CLASS = {
    VERB: 'pos-verb', NOUN: 'pos-noun', ADJ: 'pos-adj', ADV: 'pos-adv',
    PREP: 'pos-prep', ADP: 'pos-prep', CONJ: 'pos-conj', CCONJ: 'pos-conj',
    SCONJ: 'pos-conj', PRON: 'pos-pron', DET: 'pos-det', INT: 'pos-int',
    INTJ: 'pos-int', NUM: 'pos-num', MWE: 'pos-mwe',
};

const POS_NAME = {
    VERB: 'verb', NOUN: 'noun', ADJ: 'adjective', ADV: 'adverb',
    PREP: 'preposition', ADP: 'preposition', CONJ: 'conjunction',
    CCONJ: 'conjunction', SCONJ: 'conjunction', PRON: 'pronoun',
    DET: 'determiner', INT: 'interjection', INTJ: 'interjection',
    NUM: 'number', MWE: 'expression',
};

const posClass = (pos) => POS_CLASS[String(pos || '').toUpperCase()] || '';
const posName = (pos) => POS_NAME[String(pos || '').toUpperCase()] || String(pos || '').toLowerCase();

function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Same word-boundary highlight the real card applies to its example sentence:
// unicode property escapes so Spanish letters are handled, case-insensitive so
// a sentence-initial "Fuego" still matches. The sentence is escaped first, so
// data can never inject markup.
function highlightWord(sentence, word) {
    const escaped = esc(sentence);
    if (!word) return escaped;
    const wordEsc = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    try {
        const re = new RegExp(`(?<![\\p{L}\\p{N}])(${wordEsc})(?![\\p{L}\\p{N}])`, 'giu');
        return escaped.replace(re, '<span class="example-word-highlight">$1</span>');
    } catch (_) {
        return escaped;  // engines without \p{...} support
    }
}

// Verbatim copy of the real card's Spotify mark so the button is visually and
// behaviourally identical — see the `spotifySvg` const in flashcards.js.
const SPOTIFY_SVG = '<svg width="44" height="44" viewBox="0 0 24 24" fill="#1DB954">'
    + '<path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34'
    + 'c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539'
    + '-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3'
    + 'c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6'
    + '-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36'
    + 'C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381'
    + ' 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/>'
    + '</svg>';

function renderFront(card) {
    const rankLabel = `<span class="card-rank-label">Vocabulary rank: `
        + `<strong class="card-stat-value">${card.rank.toLocaleString()}</strong></span>`;
    const count = `<strong class="card-stat-value">${card.corpusCount.toLocaleString()}</strong>`;
    const freqLabel = card.mode === 'lyrics'
        ? `<span class="card-freq-label">Lyric lines: ${count}</span>`
        : `<span class="card-freq-label">Frequency: ${count}/million</span>`;

    return `
        <div class="card-face card-front">
            <div class="card-word">${esc(card.word)}</div>
            <div class="card-pos-list" style="display: flex;">
                <span class="front-pos-unit"><span class="card-pos ${posClass(card.pos)}">${posName(card.pos)}</span></span>
            </div>
            <div class="card-ranking" style="display: flex;">${rankLabel}${freqLabel}</div>
            <div class="about-example-flip-hint" aria-hidden="true">Tap to flip</div>
            <div class="card-tint" aria-hidden="true"></div>
        </div>`;
}

// Sense rows. The real card emits several row layouts depending on how the
// meanings group; the singleton `.meaning-row-regular` branch below is the one
// these demo cards hit, reproduced with its inline styles intact so it picks
// up the live rules rather than a copy of them.
function walkthroughSenseSummary(value) {
    let text = String(value || '').trim();
    let previous = '';
    while (text !== previous) {
        previous = text;
        text = text.replace(/\s*\([^()]*\)/gu, ' ');
    }
    return text.replace(/\s{2,}/gu, ' ').replace(/\s+([,;:.])/gu, '$1').trim();
}

function walkthroughSenseText(meaning, selected) {
    if (Array.isArray(meaning.references) && meaning.references.length) {
        const links = meaning.references.map(target => (
            `<button type="button" class="sense-cross-reference" title="Open ${esc(target)} card" `
            + `aria-label="Open ${esc(target)} card">${esc(target)}</button>`
        )).join('<span class="sense-cross-reference-separator">,</span> ');
        return `<span class="sense-cross-reference-prefix">See</span> ${links}`;
    }
    const value = selected ? meaning.translation : walkthroughSenseSummary(meaning.translation);
    return esc(value || meaning.translation);
}

function walkthroughMetadata(meaning, selected) {
    if (!selected || !Array.isArray(meaning.metadata) || !meaning.metadata.length) return '';
    const renderItems = items => items.map(item => (
        `<span class="sense-metadata-detail" data-family="${esc(item.family)}" `
        + `title="${esc(`${item.family}: ${item.full}`)}">${esc(item.short)}</span>`
    )).join('');
    const primary = meaning.metadata.filter(item => item.family !== 'grammar' && item.family !== 'functional');
    const grammar = meaning.metadata.filter(item => item.family === 'grammar');
    const supporting = meaning.metadata.filter(item => item.family === 'functional');
    const primaryHTML = primary.length
        ? `<span class="sense-metadata-tier sense-metadata-tier--primary">${renderItems(primary)}</span>` : '';
    const grammarHTML = grammar.length
        ? `<span class="sense-metadata-tier sense-metadata-tier--grammar"><span class="sense-metadata-tier-label">grammar</span>${renderItems(grammar)}</span>` : '';
    const supportingHTML = supporting.length
        ? `<span class="sense-metadata-tier sense-metadata-tier--details" hidden>${renderItems(supporting)}</span>` : '';
    const more = supporting.length
        ? `<button type="button" class="sense-metadata-more" aria-expanded="false" data-count="${supporting.length}">Details +${supporting.length}</button>` : '';
    return `<span class="sense-metadata-list" aria-label="Sense details">${primaryHTML}${grammarHTML}${supportingHTML}${more}</span>`;
}

function renderMeaningRows(card, selectedIdx) {
    const rows = card.meanings.map((m, idx) => {
        const isSelected = idx === selectedIdx;
        const bg = 'rgba(var(--sense-match-rgb), 0.10)';
        const textColor = 'var(--text-primary)';
        const ctx = m.context
            ? ` <span class="meaning-context">· ${esc(m.context)}</span>`
            : '';
        const pct = m.pct < 100
            ? `<span class="about-example-pct sense-percentage sense-percentage-tail" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); white-space: nowrap; pointer-events: none;">${m.pct}%</span>`
            : '';
        const check = isSelected
            ? '<svg class="meaning-row-check" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="rgb(var(--sense-match-rgb))" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>'
            : '';
        return `
            <div class="meaning-row meaning-row-regular${isSelected ? ' selected is-current-sense' : ''}" data-meaning-index="${idx}" style="position: relative; display: grid; grid-template-columns: 1fr; align-items: center; padding: 1px 2px; margin-bottom: 4px; background: ${bg}; border-radius: 8px; cursor: pointer; min-height: 39px;">
                ${check}
                <div class="meaning-row-body" style="display: flex; flex-direction: column; align-items: stretch; justify-content: center; min-width: 0; padding: 0 ${m.pct < 100 ? '42px' : '8px'} 0 8px;">
                    <span class="meaning-row-translation row-adaptive-text" style="font-weight: ${isSelected ? 700 : 500}; color: ${textColor}; text-align: center; width: 100%;">${walkthroughSenseText(m, isSelected)}${ctx}</span>
                    ${walkthroughMetadata(m, isSelected)}
                </div>
                ${pct}
            </div>`;
    }).join('');
    const summaryLimit = Math.min(2, card.meanings.length);
    const summaries = card.meanings.slice(0, summaryLimit).map(meaning => (
        `<span class="pos-summary-sense">${esc(walkthroughSenseSummary(meaning.translation))}</span>`
    )).join('');
    const hiddenCount = card.meanings.length - summaryLimit;
    const more = hiddenCount > 0
        ? `<span class="pos-pill-more" aria-label="${hiddenCount} more senses">+${hiddenCount}</span>`
        : '';
    return `
        <section class="meaning-pos-section pos-collapsible is-open" data-pos="${esc(card.pos)}">
            <button type="button" class="pos-section-head" aria-label="${esc(`${posName(card.pos)}: ${card.meanings.map(m => walkthroughSenseSummary(m.translation)).join('; ')}`)}">
                <span class="pos-section-label">${esc(posName(card.pos))}</span>
                <span class="pos-section-summary">${summaries}${more}</span>
                <span class="pos-section-chevron">▾</span>
            </button>
            <div class="meaning-pos-rows">${rows}</div>
        </section>`;
}

// Credit strip beneath the lyric: song + vocalists on the left, autoplay /
// Spotify / example counter on the right. Speech cards have no track, so the
// strip degrades to a right-aligned source label, exactly as on a live card.
function renderCredit(card, meaning, example, exampleIdx) {
    const counter = meaning.examples.length > 1
        ? `<span class="example-counter-group"><span class="compact-example-counter" aria-label="example ${exampleIdx + 1} of ${meaning.examples.length}"><span class="compact-example-counter-label" aria-hidden="true">ex</span>${exampleIdx + 1}⁄${meaning.examples.length}</span></span>`
        : '';

    if (example.trackId) {
        // The live handler on the real card. It resolves the Spotify token,
        // starts the PKCE login when there isn't one, and picks the Web
        // Playback SDK or Connect depending on the device — all of which we
        // want here unchanged, which is why this defers to the global rather
        // than reimplementing any of it.
        const btn = `<button type="button" class="spotify-btn link-btn"
                data-track-id="${esc(example.trackId)}" data-position-ms="${example.positionMs}"
                title="Play in Spotify" style="cursor:pointer; margin:0; position:relative; z-index:999;"
                data-about-example-spotify="1">${SPOTIFY_SVG}</button>`;
        const vocalists = example.vocalists
            ? `<span class="example-vocalist-credit"> · ${esc(example.vocalists)}</span>`
            : '';
        return `
            <div style="display: flex; justify-content: space-between; align-items: center; color: #b9c2cd; font-size: 13px; margin-top: 8px; font-style: italic;">
                <span class="example-song-credit">— ${esc(example.song)}${vocalists}</span>
                <span style="display: flex; align-items: center; gap: 6px;">${btn}${counter}</span>
            </div>`;
    }

    const label = example.sourceLabel
        ? `<span class="example-song-credit" style="margin-right:auto;">${esc(example.sourceLabel)}</span>`
        : '';
    if (!label && !counter) return '';
    return `
        <div style="display: flex; justify-content: flex-end; align-items: center; color: #b9c2cd; font-size: 13px; margin-top: 8px;">
            ${label}<span style="display: flex; align-items: center; gap: 6px;">${counter}</span>
        </div>`;
}

function renderBack(card, selectedIdx, exampleIdx) {
    const meaning = card.meanings[selectedIdx];
    const example = meaning.examples[exampleIdx % meaning.examples.length];
    const cursor = meaning.examples.length > 1 ? 'cursor: pointer;' : '';

    return `
        <div class="card-face card-back">
            <div class="card-details">
                <div class="back-header">
                    <div class="flip-back-area">
                        <div class="back-headword-row">
                            <span class="back-headword" style="font-size: 42px; font-weight: bold; line-height: 1.1;">${esc(card.word)}</span>
                        </div>
                    </div>
                </div>
                <div class="meanings-scroll">${renderMeaningRows(card, selectedIdx)}</div>
                <div class="sentence example-is-matched" style="text-align: center; ${cursor}" data-about-example-cycle="${meaning.examples.length > 1 ? '1' : '0'}">
                    <div class="breakdown-trigger" style="margin-bottom: 8px;">${highlightWord(example.target, card.word)}</div>
                    <div class="translation">${esc(example.english)}</div>
                    ${renderCredit(card, meaning, example, exampleIdx % meaning.examples.length)}
                </div>
            </div>
            <div class="card-tint" aria-hidden="true"></div>
        </div>`;
}


// ---------------------------------------------------------------------------
// Walkthrough controller
// ---------------------------------------------------------------------------

const state = {
    chapterIndex: 0,
    // The back opens first, deliberately: it holds the senses, the shares and
    // the evidence. The front is a prompt with a rank on it.
    flipped: true,
    meaningIndex: 0,
    exampleIndex: 0,
    activeNote: -1,
};

// The source order is intentional: first teach the everyday Speech card,
// then reveal that the same study model works with Lyrics and live playback.
// ABOUT_EXAMPLE_DECKS retains its data order; this owns the tutorial story.
const TUTORIAL_DECK_SEQUENCE = [1, 0];

const MOBILE_WALKTHROUGH_QUERY = '(max-width: 700px)';

function isMobileWalkthrough() {
    return window.matchMedia?.(MOBILE_WALKTHROUGH_QUERY).matches === true;
}

function currentDeck() {
    return ABOUT_EXAMPLE_DECKS[TUTORIAL_DECK_SEQUENCE[state.chapterIndex]];
}

function currentCard() {
    return ABOUT_EXAMPLE_CARDS[currentDeck().card];
}

// The annotation set is a property of the face on show, not of the tab. This
// is the whole reason flipping re-renders the notes.
function currentFace() {
    return currentDeck().faces[state.flipped ? 'back' : 'front'];
}

// Left column first, then right, so the numbers run in reading order and each
// badge sits on the same side as the note explaining it.
function orderedNotes() {
    const notes = currentFace().notes;
    return [
        ...notes.filter(n => n.side !== 'right'),
        ...notes.filter(n => n.side === 'right'),
    ];
}

// Full rebuild — used when the deck changes.
function renderCard() {
    const stage = document.getElementById('aboutExampleStage');
    if (!stage) return;
    const card = currentCard();

    stage.innerHTML = `
        <div class="about-example-card-inner">
            <div class="card${state.flipped ? ' flipped' : ''}" data-rank="${card.rank}">
                ${renderFront(card)}
                ${renderBack(card, state.meaningIndex, state.exampleIndex)}
            </div>
        </div>`;

    wireCardShell(stage);
    wireBack(stage);
    renderFaceCopy();
    renderNotes();
    placeMarkers();
    syncContinueButton();
}

// Sense and example changes replace only the back face, leaving the .card
// element (and therefore its flip transform) untouched — the same division of
// labour as the live app, where updateCard() rewrites #backContent rather than
// the card around it.
function refreshBack() {
    const stage = document.getElementById('aboutExampleStage');
    const back = stage?.querySelector('.card-back');
    if (!stage || !back) return;
    back.outerHTML = renderBack(currentCard(), state.meaningIndex, state.exampleIndex);
    wireBack(stage);
    placeMarkers();
}

// Flipping is a face change, so the annotations change with it: new copy, new
// numbered set, badges re-placed on the side now showing.
function flipCardFace(mobileNote = 0) {
    const stage = document.getElementById('aboutExampleStage');
    const cardEl = stage?.querySelector('.card');
    if (!cardEl) return;

    state.flipped = !state.flipped;
    state.activeNote = -1;
    cardEl.classList.toggle('flipped', state.flipped);

    // Clear the outgoing badges immediately — leaving them on screen through
    // the 0.6s flip is exactly the "labels in the wrong place" problem.
    const layer = document.getElementById('aboutExampleMarkers');
    if (layer) layer.innerHTML = '';

    renderFaceCopy();
    renderNotes();
    syncFlipButton();
    syncContinueButton();
    // Re-place once the transform has settled, so boxes are measured flat.
    setTimeout(() => {
        placeMarkers();
        if (isMobileWalkthrough()) {
            const finalIndex = Math.max(0, orderedNotes().length - 1);
            setActiveNote(Math.min(mobileNote, finalIndex));
        }
    }, 640);
}

function wireCardShell(stage) {
    const cardEl = stage.querySelector('.card');
    if (!cardEl) return;

    // Flip on card tap, minus the controls that carry their own meaning.
    // Toggling the class (rather than re-rendering) is what lets the real
    // 0.6s flip transition actually play.
    cardEl.addEventListener('click', (e) => {
        if (e.target.closest('.spotify-btn')) return;
        if (e.target.closest('.sense-metadata-more')) return;
        if (e.target.closest('.sense-cross-reference')) return;
        if (e.target.closest('.meaning-row')) return;
        if (e.target.closest('.sentence[data-about-example-cycle="1"]')) return;
        flipCardFace();
    });
}

// Handlers for everything inside the back face. Called again after every
// back-face rebuild, since those nodes are replaced wholesale.
function wireBack(stage) {
    stage.querySelector('.pos-section-head')?.addEventListener('click', (e) => {
        // The walkthrough shows one already-open group. Keep taps on its
        // heading from being mistaken for a request to flip the whole card.
        e.stopPropagation();
    });

    // Sense selection — switching sense resets to that sense's first example,
    // the same as selectMeaning() does on a live card.
    stage.querySelectorAll('.meaning-row').forEach((row) => {
        row.addEventListener('click', (e) => {
            if (e.target.closest('.sense-metadata-more, .sense-cross-reference')) return;
            e.stopPropagation();
            const idx = Number(row.dataset.meaningIndex);
            if (Number.isNaN(idx)) return;
            state.meaningIndex = idx;
            state.exampleIndex = 0;
            refreshBack();
        });
    });

    stage.querySelector('.sense-metadata-more')?.addEventListener('click', (e) => {
        e.stopPropagation();
        const control = e.currentTarget;
        const list = control.closest('.sense-metadata-list');
        const expanded = control.getAttribute('aria-expanded') === 'true';
        const details = list?.querySelector('.sense-metadata-tier--details');
        if (details) details.hidden = expanded;
        control.setAttribute('aria-expanded', String(!expanded));
        control.textContent = expanded ? `Details +${control.dataset.count}` : 'Hide details';
        control.setAttribute('aria-label', expanded
            ? `Show ${control.dataset.count} supporting details`
            : 'Hide supporting details');
        placeMarkers();
    });

    // The real card opens the referenced vocabulary card. The walkthrough is
    // data-independent, so its copy of the control is intentionally inert.
    stage.querySelectorAll('.sense-cross-reference').forEach(reference => {
        reference.addEventListener('click', e => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    // Tap the lyric to cycle this sense's other examples.
    const sentence = stage.querySelector('.sentence[data-about-example-cycle="1"]');
    if (sentence) {
        sentence.addEventListener('click', (e) => {
            if (e.target.closest('.spotify-btn')) return;
            e.stopPropagation();
            state.exampleIndex += 1;
            refreshBack();
        });
    }

    // The live Spotify hand-off. spotifyPlayTrack() is published on window by
    // spotify.js; it resolves the token, runs the PKCE login when there isn't
    // one, and picks the Web Playback SDK or Connect by device — all of which
    // we want unchanged, which is why this defers rather than reimplementing.
    // If the module somehow isn't loaded, fall back to the web player.
    const spotifyBtn = stage.querySelector('[data-about-example-spotify]');
    if (spotifyBtn) {
        spotifyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            const trackId = spotifyBtn.dataset.trackId;
            const positionMs = Number(spotifyBtn.dataset.positionMs) || 0;
            if (typeof window.spotifyPlayTrack === 'function') {
                spotifyBtn.classList.add('autoplay-loading');
                Promise.resolve(window.spotifyPlayTrack(trackId, positionMs))
                    .catch(() => {})
                    .finally(() => spotifyBtn.classList.remove('autoplay-loading'));
            } else {
                window.open(`https://open.spotify.com/track/${trackId}`, '_blank', 'noopener');
            }
        });
    }
}

function syncFlipButton() {
    const btn = document.getElementById('aboutExampleFlip');
    if (!btn) return;
    btn.textContent = state.flipped ? '⟲  Show the front' : '⟲  Show the back';
}

function syncContinueButton() {
    const btn = document.getElementById('aboutExampleContinue');
    if (!btn) return;
    const ready = !isMobileWalkthrough() && !state.flipped;
    btn.hidden = !ready;
    if (!ready) return;
    btn.textContent = state.chapterIndex < TUTORIAL_DECK_SEQUENCE.length - 1
        ? 'Continue to Lyrics →'
        : 'Finish tutorial';
}

// ---------------------------------------------------------------------------
// Annotations
// ---------------------------------------------------------------------------

// Badges are positioned from each target's measured box rather than hard-coded
// offsets, so they stay correct when a sense row wraps, the lyric runs to two
// lines, or the viewport narrows. A left-column note pins its badge to the
// element's left edge and a right-column note to its right edge, so no badge
// has to cross the card to reach the note it belongs to.
function placeMarkers() {
    const stage = document.getElementById('aboutExampleStage');
    const layer = document.getElementById('aboutExampleMarkers');
    if (!stage || !layer) return;
    layer.innerHTML = '';

    const stageRect = stage.getBoundingClientRect();
    const cardRect = stage.querySelector('.card')?.getBoundingClientRect() || stageRect;
    const occupied = { left: [], right: [] };

    orderedNotes().forEach((note, i) => {
        const target = stage.querySelector(note.anchor);
        if (!target) return;
        target.classList.add('about-example-anchored');
        target.dataset.aboutExampleNote = String(i);

        // Both faces are always in the DOM (backface-visibility does the
        // hiding) and both report real boxes. Only badge what is face-up.
        const onBack = !!target.closest('.card-back');
        if (onBack !== state.flipped) return;

        const rect = target.getBoundingClientRect();
        if (!rect.width && !rect.height) return;

        const onRight = note.side === 'right';
        const marker = document.createElement('button');
        marker.type = 'button';
        marker.className = `about-example-marker ${onRight ? 'is-right' : 'is-left'}`;
        marker.dataset.note = String(i);
        marker.textContent = String(i + 1);
        marker.setAttribute('aria-label', `Annotation ${i + 1}: ${note.title}`);
        // Badges live just outside the card rather than covering the word,
        // percentage, Spotify button or compact counter they explain. Several
        // targets can share one row, so nudge collisions into a short stack.
        marker.style.left = onRight
            ? `${cardRect.right - stageRect.left + 4}px`
            : `${cardRect.left - stageRect.left - 26}px`;
        const side = onRight ? 'right' : 'left';
        let top = rect.top - stageRect.top + rect.height / 2 - 11;
        const upperBound = cardRect.top - stageRect.top;
        const lowerBound = cardRect.bottom - stageRect.top - 22;
        top = Math.max(upperBound, Math.min(top, lowerBound));
        while (occupied[side].some(value => Math.abs(value - top) < 24)) top -= 24;
        top = Math.max(upperBound, top);
        occupied[side].push(top);
        marker.style.top = `${top}px`;
        marker.addEventListener('mouseenter', () => setActiveNote(i));
        marker.addEventListener('mouseleave', () => setActiveNote(-1));
        marker.addEventListener('focus', () => setActiveNote(i));
        marker.addEventListener('blur', () => setActiveNote(-1));
        layer.appendChild(marker);
    });

    if (state.activeNote >= 0) setActiveNote(state.activeNote);
}

// Hovering either a badge or its note lights up both, plus the element itself.
function setActiveNote(index) {
    state.activeNote = index;
    const root = document.getElementById('aboutExampleModal');
    if (!root) return;
    root.querySelectorAll('.about-example-marker').forEach((m) => {
        m.classList.toggle('is-active', Number(m.dataset.note) === index);
    });
    root.querySelectorAll('.about-example-note').forEach((n) => {
        n.classList.toggle('is-active', Number(n.dataset.note) === index);
    });
    root.querySelectorAll('.about-example-anchored').forEach((el) => {
        el.classList.toggle('is-annotation-active', Number(el.dataset.aboutExampleNote) === index);
    });
    renderMobileCoach();
}

function renderMobileCoach() {
    const coach = document.getElementById('aboutExampleMobileCoach');
    if (!coach) return;
    const mobile = isMobileWalkthrough();
    const notes = orderedNotes();
    const index = Math.max(0, Math.min(state.activeNote, notes.length - 1));
    const note = notes[index];
    coach.hidden = !mobile || !note;
    if (coach.hidden) return;

    document.getElementById('aboutExampleMobileProgress').textContent =
        `${currentDeck().tab} · ${state.chapterIndex + 1} of ${TUTORIAL_DECK_SEQUENCE.length}`
        + ` · ${state.flipped ? 'Back' : 'Front'} · ${index + 1} of ${notes.length}`;
    document.getElementById('aboutExampleMobileTitle').innerHTML =
        `${esc(note.title)}${note.interactive ? '<span class="about-example-try">tap it</span>' : ''}`;
    document.getElementById('aboutExampleMobileText').innerHTML = note.text;
    const back = document.getElementById('aboutExampleMobileBack');
    const next = document.getElementById('aboutExampleMobileNext');
    back.disabled = state.chapterIndex === 0 && state.flipped && index === 0;
    next.textContent = index < notes.length - 1
        ? 'Next'
        : (state.flipped
            ? 'Show front'
            : (state.chapterIndex < TUTORIAL_DECK_SEQUENCE.length - 1 ? 'Continue to Lyrics' : 'Finish'));
}

function moveMobileTour(direction) {
    if (!isMobileWalkthrough()) return;
    const notes = orderedNotes();
    const index = Math.max(0, Math.min(state.activeNote, notes.length - 1));
    const candidate = index + direction;
    if (candidate >= 0 && candidate < notes.length) {
        setActiveNote(candidate);
        return;
    }
    if (direction > 0 && state.flipped) {
        flipCardFace(0);
    } else if (direction > 0) {
        advanceChapterOrFinish();
    } else if (!state.flipped) {
        flipCardFace(Number.MAX_SAFE_INTEGER);
    } else if (state.chapterIndex > 0) {
        showTutorialChapter(state.chapterIndex - 1, false, Number.MAX_SAFE_INTEGER);
    }
}

function renderFaceCopy() {
    const face = currentFace();
    const host = document.getElementById('aboutExampleIntro');
    if (!host) return;
    // The title is a lead-in to the summary, not a heading over it — one
    // line instead of two, because the card and its annotations have to share
    // the screen. No "Lyrics · Bad Bunny · back of card" line either: the tab
    // already says which deck, and the card in front of you already says
    // which side you are looking at.
    host.innerHTML = `
        <p class="about-example-blurb">
            <strong class="about-example-lede">${face.title}</strong>
            ${face.blurb}
        </p>`;
}

function noteHTML(note, index) {
    return `
        <li class="about-example-note" data-note="${index}">
            <span class="about-example-note-num">${index + 1}</span>
            <div>
                <strong>${note.title}${note.interactive ? '<span class="about-example-try">try it</span>' : ''}</strong>
                <span>${note.text}</span>
            </div>
        </li>`;
}

function renderNotes() {
    const left = document.getElementById('aboutExampleNotesLeft');
    const right = document.getElementById('aboutExampleNotesRight');
    if (!left || !right) return;

    const notes = orderedNotes();
    const leftHTML = [];
    const rightHTML = [];
    notes.forEach((note, i) => {
        (note.side === 'right' ? rightHTML : leftHTML).push(noteHTML(note, i));
    });

    left.innerHTML = `<ol class="about-example-note-list">${leftHTML.join('')}</ol>`;
    right.innerHTML = `<ol class="about-example-note-list">${rightHTML.join('')}</ol>`;

    document.getElementById('aboutExampleModal')
        ?.querySelectorAll('.about-example-note')
        .forEach((el) => {
            const i = Number(el.dataset.note);
            el.addEventListener('mouseenter', () => setActiveNote(i));
            el.addEventListener('mouseleave', () => setActiveNote(-1));
        });
}

// ---------------------------------------------------------------------------
// Linear tutorial chapters
// ---------------------------------------------------------------------------

function renderSequenceProgress() {
    const host = document.getElementById('aboutExampleSequence');
    if (!host) return;
    host.innerHTML = `<strong>${esc(currentDeck().tab)}</strong><span>${state.chapterIndex + 1} of ${TUTORIAL_DECK_SEQUENCE.length}</span>`;
}

function showTutorialChapter(index, flipped = true, mobileNote = 0) {
    if (index < 0 || index >= TUTORIAL_DECK_SEQUENCE.length) return;
    state.chapterIndex = index;
    state.flipped = flipped;
    state.meaningIndex = currentCard().defaultMeaningIndex || 0;
    state.exampleIndex = 0;
    state.activeNote = isMobileWalkthrough() ? mobileNote : -1;

    renderSequenceProgress();
    renderCard();
    syncFlipButton();
    renderMobileCoach();

    const body = document.getElementById('aboutExampleBody');
    if (body) body.scrollTop = 0;
}

function advanceChapterOrFinish() {
    if (state.chapterIndex < TUTORIAL_DECK_SEQUENCE.length - 1) {
        showTutorialChapter(state.chapterIndex + 1);
    } else {
        closeAboutExample();
    }
}

// ---------------------------------------------------------------------------
// Open / close
// ---------------------------------------------------------------------------

let _resizeHandler = null;

function openAboutExample() {
    const modal = document.getElementById('aboutExampleModal');
    if (!modal) return;
    rememberCardWalkthrough();
    modal.classList.remove('hidden');
    showTutorialChapter(0);

    if (!_resizeHandler) {
        _resizeHandler = () => {
            if (isMobileWalkthrough() && state.activeNote < 0) state.activeNote = 0;
            placeMarkers();
            syncContinueButton();
            renderMobileCoach();
        };
        window.addEventListener('resize', _resizeHandler);
    }
}

function openFirstRunAboutExample() {
    if (hasSeenCardWalkthrough()) return false;
    // Never stack the automatic tour over authentication, About, settings, or
    // another onboarding sheet. Permanent replay links remain available.
    if (document.querySelector('.modal:not(.hidden), .knowledge-overview-modal:not([hidden])')) {
        return false;
    }
    openAboutExample();
    return true;
}

// The modal is layered over its opener. Closing therefore reveals About when
// launched there, or the main app when launched by onboarding/help.
function closeAboutExample() {
    const modal = document.getElementById('aboutExampleModal');
    if (!modal) return;
    modal.classList.add('hidden');
    // Leave any Spotify playback the visitor started running — they pressed
    // play deliberately, and closing a walkthrough shouldn't stop their music.
    if (_resizeHandler) {
        window.removeEventListener('resize', _resizeHandler);
        _resizeHandler = null;
    }
}

function setupAboutExample() {
    const modal = document.getElementById('aboutExampleModal');
    if (!modal || modal.dataset.ready === '1') return;
    modal.dataset.ready = '1';

    document.getElementById('closeAboutExampleModal')?.addEventListener('click', closeAboutExample);
    document.getElementById('aboutExampleFlip')?.addEventListener('click', () => flipCardFace(0));
    document.getElementById('aboutExampleContinue')?.addEventListener('click', advanceChapterOrFinish);
    document.getElementById('aboutExampleMobileBack')?.addEventListener('click', () => moveMobileTour(-1));
    document.getElementById('aboutExampleMobileNext')?.addEventListener('click', () => moveMobileTour(1));

    // Escape closes; left/right move through the story; space flips, as in study.
    document.addEventListener('keydown', (e) => {
        if (modal.classList.contains('hidden')) return;
        if (e.key === 'Escape') closeAboutExample();
        else if (e.key === 'ArrowRight') showTutorialChapter(state.chapterIndex + 1);
        else if (e.key === 'ArrowLeft') showTutorialChapter(state.chapterIndex - 1);
        else if (e.key === ' ' && !e.target.closest('button')) {
            e.preventDefault();
            flipCardFace();
        }
    });
}

document.addEventListener('DOMContentLoaded', setupAboutExample);
if (document.readyState !== 'loading') setupAboutExample();

window.openAboutExample = openAboutExample;
window.openFirstRunAboutExample = openFirstRunAboutExample;
window.closeAboutExample = closeAboutExample;
