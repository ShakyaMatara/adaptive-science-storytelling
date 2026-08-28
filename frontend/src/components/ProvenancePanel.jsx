// The provenance panel: the textbook passages a chapter was actually built from.
//
// This is the surface that makes curricular fidelity visible. A learner (or a
// teacher looking over their shoulder) taps a paragraph of the story and sees
// the pages of the real Grade 6-9 science textbook that grounded it, with the
// printed page citation they can turn to in the physical book.
//
// The extract is deliberately set apart from the app's own voice: a serif face
// on paper-coloured ground, labelled as the textbook's own words, so it can
// never be read as generated content.
//
// Props
//   chapterId  (number, required)  the chapter to explain
//   grade      (number, optional)  shown in the heading before the fetch lands
//   open       (bool)              whether the panel is showing
//   onClose    (function)          called on Escape, backdrop click, or the close button
//   label      (string, optional)  overrides the heading, e.g. when opened from a topic
//
// Fetching only happens while `open` is true, and each chapter's result is kept
// for the lifetime of the component so reopening the panel is instant.

import { useCallback, useEffect, useRef, useState } from "react";

import { getProvenance } from "../api";
import { SkeletonLines, Toast, useToast } from "./ui";
import "../styles/insight.css";

export default function ProvenancePanel({
  chapterId,
  grade = null,
  open = false,
  onClose = () => {},
  label = null,
}) {
  const { toast, showToast, clearToast } = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const cache = useRef({});          // chapterId -> response, for this mount only
  const closeRef = useRef(null);     // the close button, focused when the panel opens
  const returnFocusRef = useRef(null); // whatever had focus before it opened

  // --- Load (only while open, and only once per chapter) ---------------------
  useEffect(() => {
    if (!open || !chapterId) return undefined;

    let cancelled = false;
    const cached = cache.current[chapterId];
    if (cached) {
      setData(cached);
      setError("");
      return undefined;
    }

    setData(null);
    setError("");
    getProvenance(chapterId)
      .then((res) => {
        if (cancelled) return;
        cache.current[chapterId] = res;
        setData(res);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
        showToast(e.message);
      });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, chapterId]);

  // --- Escape to close -------------------------------------------------------
  const handleKeyDown = useCallback((e) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, handleKeyDown]);

  // --- Focus: into the panel on open, back where it came from on close -------
  useEffect(() => {
    if (open) {
      returnFocusRef.current = document.activeElement;
      // Wait for the panel to be in the document before moving focus into it.
      const id = window.setTimeout(() => closeRef.current && closeRef.current.focus(), 0);
      return () => window.clearTimeout(id);
    }
    const previous = returnFocusRef.current;
    if (previous && typeof previous.focus === "function") previous.focus();
    returnFocusRef.current = null;
    return undefined;
  }, [open]);

  if (!open) return null;

  // Only show a response that belongs to the chapter currently asked for, so
  // reopening the panel on a different chapter cannot flash the previous one.
  const ready = data && data.chapter_id === chapterId ? data : null;
  const shownGrade = (ready && ready.grade) || grade;
  const heading = label || (ready ? ready.chapter_title : "Textbook source");

  return (
    <>
      <div className="prov-backdrop" onClick={onClose} aria-hidden="true" />
      <aside
        className="prov-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prov-panel-title"
      >
        <header className="prov-head">
          <div className="prov-head-text">
            <h2 className="prov-title" id="prov-panel-title">📖 Where this came from</h2>
            <p className="prov-subtitle">
              {heading}
              {shownGrade ? ` · Grade ${shownGrade} textbook` : ""}
            </p>
          </div>
          <button
            className="prov-close"
            ref={closeRef}
            onClick={onClose}
            aria-label="Close the textbook source panel"
          >
            ×
          </button>
        </header>

        <div className="prov-body">
          <p className="prov-explain">
            This story was written from your own science textbook. Everything in a
            cream box below is the textbook's own wording, copied exactly — not
            part of the story. Use the page number to find it in your printed book.
          </p>

          {error && <p className="prov-error">⚠️ {error}</p>}

          {!ready && !error && <SkeletonLines lines={5} />}

          {ready && <PanelBody data={ready} />}
        </div>
      </aside>
      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </>
  );
}

// The textbook index labels a page that carries no chapter heading of its own —
// a contents page, for instance — as "(document)". That is an artefact of how
// the book was read, not something to show a learner, so it is dropped here.
const LABEL_PLACEHOLDER = "(document)";

function whereInBook(passage) {
  return [passage.chapter, passage.section]
    .filter((label) => label && label !== LABEL_PLACEHOLDER)
    .join(" › ");
}

// Everything below the explanation, once the response has landed.
function PanelBody({ data }) {
  const passages = data.passages || [];
  const recovery = data.recovery || { semantic: 0, exact: 0 };

  return (
    <>
      {data.message && <p className="prov-note">ℹ️ {data.message}</p>}

      {passages.length === 0 && !data.message && (
        <p className="prov-note">
          ℹ️ No textbook passages are recorded for this chapter.
        </p>
      )}

      {passages.map((p, i) => {
        const where = whereInBook(p);
        return (
        <section className="prov-passage" key={`${p.source_file}-${p.page}-${i}`}>
          <span className="prov-passage-label">
            Textbook source — printed exactly as it appears
          </span>
          <blockquote className="prov-text">{p.text}</blockquote>
          <span className="prov-cite">
            From the Grade {data.grade} textbook, {p.page_citation || `page ${p.page}`}
            {where && <span className="prov-where">{" — "}{where}</span>}
          </span>
          <span className="prov-recovery">
            {p.recovered_by === "exact lookup"
              ? "Found by looking up this exact page in the textbook index."
              : "Matched back to this chapter by searching the textbook index."}
            {p.page != null ? ` (file ${p.source_file}, PDF page ${p.page})` : ""}
          </span>
        </section>
        );
      })}

      {data.grounded && (
        <p className="prov-footer">
          {passages.length} of {data.stored_reference_count} recorded textbook
          {data.stored_reference_count === 1 ? " reference" : " references"} recovered
          {passages.length > 0 && ` — ${recovery.semantic} by search, ${recovery.exact} by exact page lookup`}.
          The passages are read from the textbook index each time and are never
          rewritten.
        </p>
      )}
    </>
  );
}
