// Read-aloud for the current chapter, built on the browser's Web Speech API.
//
// WHY THIS EXISTS: the stories are written in English, which for most learners
// using this is a second (or third) language. Hearing a sentence while seeing it
// is a well-established support for that, and it also opens the material to
// learners with low vision or a reading difficulty. It costs nothing to run —
// the speech happens on the device, not on a server — which matters where
// connectivity is intermittent.
//
// The hook owns the awkward parts of the API so the toolbar can stay simple:
//
//   * Unsupported browsers. `speechSynthesis` is absent on some older Android
//     browsers. The hook reports `supported: false` and does nothing else; the
//     toolbar then renders no controls at all. No error, no warning.
//   * Speech outliving the component. `speechSynthesis` is a property of the
//     window, not of React: without an explicit cancel it happily keeps reading a
//     chapter the learner has already navigated away from. Cancelled on unmount
//     and whenever the paragraphs change.
//   * Voices arriving late. The voice list is often empty on first call and is
//     filled in asynchronously, announced by `voiceschanged`.
//   * Long utterances. Several browsers cut off or silently drop an utterance
//     after roughly fifteen seconds. Rather than the usual pause/resume hack,
//     the text is split into sentence-sized chunks that comfortably finish in
//     time, chained through each chunk's `end` event. Chunks remember which
//     paragraph they came from, so the highlight still moves a paragraph at a
//     time.
//   * `pause()` / `resume()` behaving differently everywhere. The control state
//     is not assumed from the last button pressed; it is polled from
//     `speechSynthesis.speaking` / `.paused` so the buttons describe what the
//     browser is actually doing.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// Roughly the longest chunk that finishes well inside the browsers' cut-off.
const MAX_CHUNK_CHARS = 180;

function speechApi() {
  if (typeof window === "undefined") return null;
  return window.speechSynthesis || null;
}

// Split one paragraph into sentence-sized pieces, keeping sentences whole where
// they fit and hard-splitting only a sentence that is longer than the limit.
function chunkParagraph(text) {
  const sentences = String(text).match(/[^.!?]+[.!?]*\s*/g) || [String(text)];
  const chunks = [];
  let current = "";

  const push = () => {
    const trimmed = current.trim();
    if (trimmed) chunks.push(trimmed);
    current = "";
  };

  for (const sentence of sentences) {
    if (sentence.length > MAX_CHUNK_CHARS) {
      push();
      // A single very long sentence: break it on word boundaries.
      let rest = sentence.trim();
      while (rest.length > MAX_CHUNK_CHARS) {
        const cut = rest.lastIndexOf(" ", MAX_CHUNK_CHARS);
        const at = cut > 40 ? cut : MAX_CHUNK_CHARS;
        chunks.push(rest.slice(0, at).trim());
        rest = rest.slice(at).trim();
      }
      if (rest) chunks.push(rest);
    } else if ((current + sentence).length > MAX_CHUNK_CHARS) {
      push();
      current = sentence;
    } else {
      current += sentence;
    }
  }
  push();
  return chunks;
}

// Prefer a UK English voice, then any English one, then whatever exists.
function pickVoice(voices) {
  if (!voices || voices.length === 0) return null;
  const english = voices.filter((v) => /^en(-|_|$)/i.test(v.lang || ""));
  return (
    english.find((v) => /^en[-_]GB/i.test(v.lang || "")) ||
    english.find((v) => /^en[-_](IN|LK|AU)/i.test(v.lang || "")) ||
    english[0] ||
    voices[0] ||
    null
  );
}

/**
 * @param {string[]} paragraphs  the paragraphs of the chapter being read
 * @param {object}   options
 * @param {(index: number|null) => void} options.onActiveParagraphChange
 *        called with the index of the paragraph being spoken, and with null when
 *        speech stops. Highlighting is the reader's job, not this hook's.
 * @param {number}   options.rate  speaking rate (0.1-10); 0.95 reads a little
 *        slower than default, which suits a second-language listener.
 */
export default function useReadAloud(paragraphs, options = {}) {
  const { onActiveParagraphChange, rate = 0.95 } = options;

  const supported = useMemo(() => !!speechApi(), []);
  const [speaking, setSpeaking] = useState(false);
  const [paused, setPaused] = useState(false);
  const [activeParagraph, setActiveParagraph] = useState(null);
  const [error, setError] = useState("");
  const [voice, setVoice] = useState(null);

  // A run id lets us ignore `end`/`error` events from a run we have cancelled —
  // those events still arrive, and without the guard they would start the next
  // chunk of a chapter the learner has already left.
  const runRef = useRef(0);
  const chunkIndexRef = useRef(0);
  const voiceRef = useRef(null);
  const notifyRef = useRef(onActiveParagraphChange);
  // Chain bookkeeping, used by the watchdog in the polling effect below.
  const finishedRef = useRef(true);   // has the chain reached the last chunk?
  const startedRef = useRef(false);   // did the current chunk actually begin speaking?
  const idleTicksRef = useRef(0);     // consecutive polls with a silent engine

  useEffect(() => { notifyRef.current = onActiveParagraphChange; }, [onActiveParagraphChange]);
  useEffect(() => { voiceRef.current = voice; }, [voice]);

  // Flatten the chapter into chunks, each tagged with its paragraph index.
  const chunks = useMemo(() => {
    const list = [];
    (paragraphs || []).forEach((paragraph, paragraphIndex) => {
      chunkParagraph(paragraph).forEach((text) => list.push({ text, paragraphIndex }));
    });
    return list;
  }, [paragraphs]);

  // Voices load asynchronously; ask once, then listen for the list arriving.
  useEffect(() => {
    const api = speechApi();
    if (!api) return undefined;
    const load = () => {
      const picked = pickVoice(api.getVoices());
      if (picked) setVoice(picked);
    };
    load();
    api.addEventListener?.("voiceschanged", load);
    return () => api.removeEventListener?.("voiceschanged", load);
  }, []);

  // Tell the reader which paragraph to highlight.
  useEffect(() => {
    notifyRef.current?.(activeParagraph);
  }, [activeParagraph]);

  const stop = useCallback(() => {
    const api = speechApi();
    runRef.current += 1;      // invalidate any queued end/error handlers
    chunkIndexRef.current = 0;
    finishedRef.current = true;
    idleTicksRef.current = 0;
    if (api) api.cancel();
    setSpeaking(false);
    setPaused(false);
    setActiveParagraph(null);
  }, []);

  // Speak from `startAt` onwards, chaining chunk by chunk.
  const speakFrom = useCallback((startAt) => {
    const api = speechApi();
    if (!api || chunks.length === 0) return;

    const runId = runRef.current + 1;
    runRef.current = runId;
    finishedRef.current = false;
    idleTicksRef.current = 0;
    setError("");

    const speakChunk = (index) => {
      if (runRef.current !== runId) return;     // superseded by a newer run
      if (index >= chunks.length) {             // finished the chapter
        chunkIndexRef.current = 0;
        finishedRef.current = true;
        setSpeaking(false);
        setPaused(false);
        setActiveParagraph(null);
        return;
      }
      chunkIndexRef.current = index;
      startedRef.current = false;
      const chunk = chunks[index];
      setActiveParagraph(chunk.paragraphIndex);

      const utterance = new window.SpeechSynthesisUtterance(chunk.text);
      utterance.rate = rate;
      utterance.lang = voiceRef.current?.lang || "en-GB";
      if (voiceRef.current) utterance.voice = voiceRef.current;
      utterance.onstart = () => { startedRef.current = true; };
      utterance.onend = () => speakChunk(index + 1);
      utterance.onerror = (event) => {
        if (runRef.current !== runId) return;
        // "interrupted" and "canceled" are what a deliberate stop looks like; the
        // watchdog below picks the chain back up if either arrives spuriously.
        if (event.error === "interrupted" || event.error === "canceled") return;
        setError("Read-aloud stopped unexpectedly. Your browser may not have a voice installed.");
        finishedRef.current = true;
        setSpeaking(false);
        setPaused(false);
        setActiveParagraph(null);
      };
      api.speak(utterance);
    };

    setSpeaking(true);
    setPaused(false);

    // Only cancel if something is actually queued, and give the cancel a moment
    // to settle before speaking: calling speak() in the same tick as cancel()
    // makes some browsers deliver "interrupted" to the new utterance instead of
    // starting it. Measured on this machine: an immediate speak() after cancel()
    // errors, a deferred one does not.
    if (api.speaking || api.pending) {
      api.cancel();
      setTimeout(() => speakChunk(startAt), 120);
    } else {
      speakChunk(startAt);
    }
  }, [chunks, rate]);

  const play = useCallback(() => {
    const api = speechApi();
    if (!api) return;
    if (api.paused && api.speaking) {  // resume where the learner paused
      api.resume();
      setPaused(false);
      return;
    }
    speakFrom(0);
  }, [speakFrom]);

  const pause = useCallback(() => {
    const api = speechApi();
    if (!api || !api.speaking) return;
    api.pause();
    // Some browsers ignore pause() entirely; the poll below corrects the state
    // within a quarter-second if that happens, so the button never lies.
    setPaused(true);
  }, []);

  const resume = useCallback(() => {
    const api = speechApi();
    if (!api) return;
    if (api.speaking) {
      api.resume();
      setPaused(false);
    } else {
      // Pause was ignored and the queue has drained: carry on from the chunk we
      // had reached rather than starting the chapter again.
      speakFrom(chunkIndexRef.current);
    }
  }, [speakFrom]);

  const toggle = useCallback(() => {
    if (!speaking) play();
    else if (paused) resume();
    else pause();
  }, [speaking, paused, play, pause, resume]);

  // Poll the real engine state while active, so the controls reflect what the
  // browser is doing rather than what we last asked it to do — and so a chapter
  // that the engine drops mid-way is picked back up instead of stopping dead.
  useEffect(() => {
    if (!supported || !speaking) return undefined;
    const id = setInterval(() => {
      const api = speechApi();
      if (!api) return;

      const reallyPaused = api.paused && (api.speaking || api.pending);
      setPaused(reallyPaused);
      if (reallyPaused || api.speaking || api.pending) {
        idleTicksRef.current = 0;
        return;
      }

      // The engine is silent. A single silent sample means nothing: there is a
      // gap between one chunk ending and the next being picked up, and it was
      // measured on this machine at up to half a second. A poll landing inside
      // that gap must not be allowed to end the chapter — which is exactly the
      // fault this counter was added to fix. Three consecutive silent samples
      // (three quarters of a second) never occur between chunks, so they mean
      // the queue really is empty.
      idleTicksRef.current += 1;
      if (idleTicksRef.current < 3) return;
      idleTicksRef.current = 0;

      if (finishedRef.current) {   // the chapter genuinely finished
        setSpeaking(false);
        setPaused(false);
        setActiveParagraph(null);
        return;
      }
      // Chunks left but nothing queued: the browser dropped the utterance, which
      // several of them do on a long read. Carry on rather than falling silent —
      // from the next chunk if this one was spoken, or from this one if it never
      // began.
      speakFrom(startedRef.current ? chunkIndexRef.current + 1 : chunkIndexRef.current);
    }, 250);
    return () => clearInterval(id);
  }, [supported, speaking, speakFrom]);

  // New chapter (or unmount): stop talking about the old one.
  useEffect(() => stop, [chunks, stop]);

  return {
    supported,
    speaking,
    paused,
    activeParagraph,
    error,
    clearError: useCallback(() => setError(""), []),
    voiceName: voice?.name || null,
    play,
    pause,
    resume,
    toggle,
    stop,
  };
}
