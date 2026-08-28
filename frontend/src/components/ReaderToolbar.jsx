// The control strip that sits under a chapter title: listen to the chapter, and
// save or print the story.
//
// It is deliberately one small component with no knowledge of where it is
// mounted, because it is mounted in two places — the live reader and the
// read-only replay — through the `toolbar` slot each of them already has.
//
// Both controls degrade rather than fail. If the browser has no speech engine,
// the listening controls are simply not rendered. The export needs the whole
// story rather than the chapter in view, so it fetches it on demand the first
// time it is used, unless the surrounding page already has it and passes it in.

import { useCallback, useEffect, useRef, useState } from "react";

import { getSession } from "../api";
import useReadAloud from "../hooks/useReadAloud";
import { exportStory } from "../utils/exportStory";
import "../styles/study.css";
import { Button, Toast, useToast } from "./ui";

export default function ReaderToolbar({
  sessionId,
  paragraphs = [],
  onActiveParagraphChange = null,
  story = null,          // already-loaded GET /api/sessions/<id> body, if the page has one
  learnerName = null,    // overrides the name in that response, if the page knows better
  className = "",
}) {
  const { toast, showToast, clearToast } = useToast();
  const [exporting, setExporting] = useState(false);
  const cachedStory = useRef(story);

  const speech = useReadAloud(paragraphs, { onActiveParagraphChange });

  // Speech errors are rare but should not be silent — the one case that matters
  // is a browser that reports a speech engine and then has no voice installed.
  const { error: speechError, clearError: clearSpeechError } = speech;
  useEffect(() => {
    if (!speechError) return;
    showToast(speechError, "info");
    clearSpeechError();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [speechError]);

  const handleExport = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      const full = story || cachedStory.current || (await getSession(sessionId));
      cachedStory.current = full;
      exportStory(full, learnerName ? { learnerName } : {});
    } catch (e) {
      showToast(e.message || "The story could not be prepared for printing.");
    } finally {
      setExporting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exporting, story, sessionId, learnerName]);

  const canRead = speech.supported && paragraphs.length > 0;

  return (
    <div className={`reader-toolbar ${className}`.trim()}>
      <div className="reader-toolbar-controls">
        {canRead && (
          <div className="reader-toolbar-group" role="group" aria-label="Read this chapter aloud">
            <Button
              variant="quiet"
              className="toolbar-btn"
              onClick={speech.toggle}
              aria-pressed={speech.speaking && !speech.paused}
            >
              {!speech.speaking ? "▶ Listen" : speech.paused ? "▶ Resume" : "⏸ Pause"}
            </Button>
            <Button
              variant="quiet"
              className="toolbar-btn"
              onClick={speech.stop}
              disabled={!speech.speaking}
            >
              ⏹ Stop
            </Button>
          </div>
        )}

        <div className="reader-toolbar-group">
          <Button
            variant="quiet"
            className="toolbar-btn"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? "Preparing…" : "🖨 Save or print"}
          </Button>
        </div>
      </div>

      <p className="reader-toolbar-note">
        {canRead
          ? "Listen while you read, or save the whole story to read offline — a printed copy needs no connection at all."
          : "Save the whole story to read offline — a printed copy needs no connection at all."}
      </p>

      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </div>
  );
}
