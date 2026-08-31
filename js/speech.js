import './state.js?v=20260825ak';

// Apple exposes several English variants with the same friendly name, while
// voiceURI is often the only place that distinguishes a downloaded premium or
// enhanced voice from its noticeably flatter compact counterpart. Rank both
// fields together for English; other languages retain their established
// selection order below.
function selectAppleEnglishVoice(voices, preferredLang = 'en-US') {
    const preferredLocale = preferredLang.toLowerCase();
    const preferredNames = preferredLocale === 'en-gb'
        ? ['serena', 'daniel', 'oliver', 'ava', 'zoe', 'samantha', 'alex']
        : ['ava', 'zoe', 'samantha', 'nathan', 'tom', 'alex', 'allison', 'daniel'];

    return voices
        .map((voice, index) => {
            const identity = `${voice.name || ''} ${voice.voiceURI || ''}`.toLowerCase();
            const locale = String(voice.lang || '').toLowerCase();
            let score = 0;

            if (locale === preferredLocale) score += 24;
            if (identity.includes('premium')) score += 140;
            if (identity.includes('enhanced')) score += 125;
            if (identity.includes('siri')) score += 115;
            if (identity.includes('natural')) score += 105;
            if (identity.includes('apple')) score += 12;

            const nameIndex = preferredNames.findIndex(name => identity.includes(name));
            if (nameIndex >= 0) score += 50 - nameIndex;

            // Keep compact voices as a last resort: iOS may expose only these
            // until a higher-quality system voice has been downloaded.
            if (identity.includes('compact')) score -= 90;

            return { voice, score, index };
        })
        .sort((a, b) => b.score - a.score || a.index - b.index)[0]?.voice || null;
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
        const langPrefix = langCode.split('-')[0];
        // Exclude novelty and character voices that sound bad
        const badVoices = /Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Fred|Good News|Jester|Junior|Organ|Ralph|Superstar|Trinoids|Whisper|Wobble|Zarvox|Eddy|Flo|Grandma|Grandpa|Rocko|Reed|Sandy|Shelley/;
        const matchingVoices = voices.filter(v => v.lang.startsWith(langPrefix) && !badVoices.test(v.name));

        // Tier 1: Premium voices (Natural/Siri/Enhanced)
        // Tier 2: Google voices (Chrome)
        // Tier 3: Best named voices in preference order
        const findByName = (name) => matchingVoices.find(v => v.name.includes(name));
        const preferredVoice = useEnglish
            ? selectAppleEnglishVoice(matchingVoices, langCode)
            : findByName('Natural') || findByName('Premium') || findByName('Siri')
                || findByName('Enhanced')
                || findByName('Google')
                || findByName('Samantha') || findByName('Ava') || findByName('Paulina')
                || findByName('Mónica') || findByName('Kathy') || findByName('Moira')
                || findByName('Karen') || findByName('Tessa')
                || findByName('Daniel') || findByName('Rishi')
                || matchingVoices[0];

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
