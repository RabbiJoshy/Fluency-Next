import './state.js?v=20260825ak';

// One scorer for every language. English used to have its own selector that
// scored premium/enhanced/siri/apple but had no rule for Google or Microsoft
// voices at all, while the other languages explicitly preferred Google. On
// Chrome that left every en-US voice tied on the same score and the winner
// decided by list order — which is how a 90s-robot Eloquence voice could come
// out on top. Divergent paths were the bug; there is now one.

// Never acceptable. Apple's novelty set plus the Eloquence family (macOS 26),
// which is the DECtalk-style robot voice. Matched against name AND voiceURI,
// because the URI is sometimes the only place the family shows up.
const REJECTED_VOICES = new RegExp([
    // novelty
    'albert', 'bad news', 'bahh', 'bells', 'boing', 'bubbles', 'cellos',
    'good news', 'jester', 'organ', 'superstar', 'trinoids', 'whisper',
    'wobble', 'zarvox', 'fred', 'junior', 'ralph', 'kathy', 'princess',
    // eloquence — the robot ones
    'eloquence', 'eddy', 'flo', 'grandma', 'grandpa', 'reed', 'rocko',
    'sandy', 'shelley',
    // low-quality open-source fallbacks on Linux/Android
    'espeak', 'pico'
].join('|'), 'i');

// Per-language preferred voices, best first. Names only — quality tiers below
// outrank these, so a "Premium" voice still wins over a plain named one.
const PREFERRED_VOICE_NAMES = {
    'en-gb': ['serena', 'daniel', 'kate', 'oliver', 'stephanie', 'ava', 'samantha'],
    'en': ['samantha', 'ava', 'allison', 'susan', 'zoe', 'evan', 'nathan', 'tom', 'alex'],
    'es': ['mónica', 'monica', 'paulina', 'marisol', 'jorge', 'juan', 'diego'],
    'fr': ['audrey', 'aurelie', 'thomas', 'amelie'],
    'nl': ['xander', 'ellen', 'claire'],
    'it': ['alice', 'luca', 'federica'],
    'pt': ['luciana', 'joana', 'catarina'],
    'pl': ['zosia', 'krzysztof', 'ewa'],
    'sv': ['alva', 'klara', 'oskar']
};

function voiceIdentity(voice) {
    return `${voice.name || ''} ${voice.voiceURI || ''}`.toLowerCase();
}

/**
 * Score a voice for a target locale. Higher is better; null means unusable.
 * The quality tiers matter far more than the name list: a "Google UK English"
 * or an "Enhanced" system voice beats a preferred-by-name compact one.
 */
function scoreVoice(voice, preferredLang) {
    const identity = voiceIdentity(voice);
    if (REJECTED_VOICES.test(identity)) return null;

    const locale = String(voice.lang || '').toLowerCase().replace('_', '-');
    const preferredLocale = String(preferredLang || '').toLowerCase().replace('_', '-');
    const langPrefix = preferredLocale.split('-')[0];
    if (!locale.startsWith(langPrefix)) return null;

    let score = 0;
    if (locale === preferredLocale) score += 30;

    // Quality tiers, in the order they actually sound.
    if (identity.includes('premium')) score += 140;
    else if (identity.includes('enhanced')) score += 125;
    else if (identity.includes('neural')) score += 120;
    else if (identity.includes('natural')) score += 118;
    else if (identity.includes('siri')) score += 110;
    // Chrome's bundled voices are consistently good and were the missing rule.
    else if (identity.includes('google')) score += 100;
    else if (identity.includes('microsoft')) score += 70;

    const names = PREFERRED_VOICE_NAMES[preferredLocale]
        || PREFERRED_VOICE_NAMES[langPrefix] || [];
    const nameIndex = names.findIndex(name => identity.includes(name));
    if (nameIndex >= 0) score += 40 - nameIndex;

    // Compact/low-quality variants are a last resort: iOS exposes only these
    // until a fuller system voice has been downloaded.
    if (identity.includes('compact')) score -= 90;
    if (voice.localService === false) score += 5;   // network voices are usually newer
    if (voice.default) score += 3;

    return score;
}

// A manual override beats every heuristic. Scoring cannot know which enhanced
// voices a given machine has actually downloaded, so window.setVoice() lets the
// choice be made on the device that can hear it, per language, and persists.
const VOICE_PREF_KEY = 'fluencyVoicePref';

function readVoicePrefs() {
    try { return JSON.parse(localStorage.getItem(VOICE_PREF_KEY) || '{}'); }
    catch (_) { return {}; }
}

function setVoice(nameFragment, langPrefix = 'en') {
    const prefs = readVoicePrefs();
    if (nameFragment) prefs[langPrefix] = String(nameFragment);
    else delete prefs[langPrefix];
    localStorage.setItem(VOICE_PREF_KEY, JSON.stringify(prefs));
    const chosen = selectVoice(window.speechSynthesis?.getVoices() || [],
                              langPrefix === 'en' ? 'en-US' : langPrefix);
    console.log(nameFragment
        ? `Voice for "${langPrefix}" pinned to something matching "${nameFragment}" — now: ${chosen?.name}`
        : `Voice override for "${langPrefix}" cleared — now: ${chosen?.name}`);
    return chosen?.name || null;
}

function selectVoice(voices, preferredLang) {
    const langPrefix = String(preferredLang || '').toLowerCase().split('-')[0];
    const pinned = readVoicePrefs()[langPrefix];
    if (pinned) {
        const needle = pinned.toLowerCase();
        const match = voices.find(voice =>
            voiceIdentity(voice).includes(needle)
            && String(voice.lang || '').toLowerCase().startsWith(langPrefix));
        if (match) return match;
    }
    return voices
        .map((voice, index) => ({ voice, index, score: scoreVoice(voice, preferredLang) }))
        .filter(entry => entry.score !== null)
        .sort((a, b) => b.score - a.score || a.index - b.index)[0]?.voice || null;
}

/**
 * Console helper: window.listVoices() prints every voice the device offers
 * with the score this module gives it, so a bad pick can be diagnosed from the
 * machine that has the bad voice rather than guessed at.
 */
function listVoices(preferredLang = 'en-US') {
    const voices = window.speechSynthesis?.getVoices() || [];
    const scored = voices.map(voice => ({
        name: voice.name,
        lang: voice.lang,
        local: voice.localService,
        score: scoreVoice(voice, preferredLang),
        uri: voice.voiceURI
    })).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    console.table(scored);
    console.log(`${voices.length} voices; winner for ${preferredLang}:`,
                selectVoice(voices, preferredLang)?.name || '(none)');
    return scored;
}

// Speak a word in the target language. The optional completion callback lets
// lyric autoplay wait for the English sense label before starting its first
// example; ordinary callers remain fire-and-forget.
function speakWord(text, useEnglish = false, onComplete = null) {
    if (!speechEnabled || !text || !window.speechSynthesis) {
        if (typeof onComplete === 'function') onComplete();
        return;
    }

    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    let completed = false;
    const complete = () => {
        if (completed) return;
        completed = true;
        if (typeof onComplete === 'function') onComplete();
    };
    utterance.onend = complete;
    utterance.onerror = complete;
    const deviceEnglishLang = (navigator.languages || [navigator.language])
        .find(lang => /^en(?:-|$)/i.test(lang));
    const langCode = useEnglish
        ? (deviceEnglishLang || 'en-US')
        // config is authoritative: a language declares its own speechLang, so
        // adding one does not mean editing a second table in state.js.
        : (config?.languages?.[selectedLanguage]?.speechLang
           || speechLangCodes[selectedLanguage]
           || 'es-ES');
    utterance.lang = langCode;
    utterance.rate = 0.9;

    const voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
        const preferredVoice = selectVoice(voices, langCode);
        if (preferredVoice) {
            utterance.voice = preferredVoice;
            utterance.lang = preferredVoice.lang;
        }
    }

    window.speechSynthesis.speak(utterance);
}

// Preload voices (they may not be available immediately)
if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.getVoices();
    };
}

window.speakWord = speakWord;
window.listVoices = listVoices;
window.setVoice = setVoice;
