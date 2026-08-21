export function speechAvailable() {
  return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

export function speak(text, locale, { english = false } = {}) {
  if (!speechAvailable() || !text) return false;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = english ? "en-GB" : locale;
  utterance.rate = 0.9;
  const languagePrefix = utterance.lang.split("-")[0];
  const badVoices = /Albert|Bad News|Bahh|Bells|Boing|Bubbles|Cellos|Fred|Jester|Organ|Ralph|Trinoids|Whisper|Zarvox/;
  const voices = window.speechSynthesis.getVoices().filter((voice) =>
    voice.lang.startsWith(languagePrefix) && !badVoices.test(voice.name));
  const preferred = voices.find((voice) => /Natural|Premium|Siri|Enhanced|Google/.test(voice.name)) || voices[0];
  if (preferred) utterance.voice = preferred;
  window.speechSynthesis.speak(utterance);
  return true;
}
