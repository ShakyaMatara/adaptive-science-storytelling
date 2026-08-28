// /browse — the syllabus browser.
//
// The whole Grade 6-9 science curriculum, as printed in the textbook contents
// pages, laid out as a tree the learner can open: grade → chapter →
// sub-section. Every row carries its printed page reference, and picking any row
// hands its own wording to the start flow as the topic, so a learner never has
// to guess what their textbook calls something.
//
// The tree arrives in one response and is filtered and expanded entirely here;
// searching never goes back to the server.

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getCurriculum } from "../api";
import { Button, Card, EmptyState, SkeletonBlock, Toast, useToast } from "../components/ui";
import "../styles/discovery.css";

export default function BrowsePage() {
  const navigate = useNavigate();
  const { toast, showToast, clearToast } = useToast();

  const [grades, setGrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  // Which rows the learner has opened by hand. While a search is running every
  // surviving row is shown open instead, so matches are visible without clicks.
  const [openGrades, setOpenGrades] = useState(() => new Set());
  const [openChapters, setOpenChapters] = useState(() => new Set());

  useEffect(() => {
    let cancelled = false;
    getCurriculum()
      .then((data) => {
        if (cancelled) return;
        const list = (data && data.grades) || [];
        setGrades(list);
        // Open the first grade so the page shows its shape straight away.
        if (list.length) setOpenGrades(new Set([list[0].grade]));
      })
      .catch((e) => { if (!cancelled) showToast(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const trimmed = query.trim();
  const searching = trimmed.length > 0;
  const visible = useMemo(() => filterGrades(grades, trimmed), [grades, trimmed]);

  const totals = useMemo(() => countTree(visible), [visible]);
  const allTotals = useMemo(() => countTree(grades), [grades]);

  function toggleGrade(grade) {
    setOpenGrades((prev) => toggled(prev, grade));
  }
  function toggleChapter(key) {
    setOpenChapters((prev) => toggled(prev, key));
  }

  // Hand a chapter or sub-section to the start flow with both boxes filled in.
  // The wording sent as the topic is the contents page's own.
  function startFrom(title, grade) {
    navigate("/", { state: { topic: title, grade } });
  }

  return (
    <Card>
      <div className="disc-head">
        <h2>📚 Browse the syllabus</h2>
        <span className="disc-count">
          {allTotals.chapters} chapters · {allTotals.sections} sub-sections
        </span>
      </div>
      <p className="disc-lede">
        Every chapter and sub-section of the Grade 6-9 science textbooks, with the page
        each one is printed on. Pick any row and your story starts there.
      </p>

      <div className="syl-search">
        <span className="syl-search-icon" aria-hidden="true">🔍</span>
        <label className="sr-only" htmlFor="syllabus-search">Search the syllabus</label>
        <input
          id="syllabus-search"
          type="search"
          className="text-input"
          value={query}
          placeholder="Search for a topic, e.g. magnets"
          onChange={(e) => setQuery(e.target.value)}
        />
        {searching && (
          <button className="syl-search-clear" aria-label="Clear search" onClick={() => setQuery("")}>
            ×
          </button>
        )}
      </div>

      {searching && !loading && (
        <p className="disc-lede" role="status" aria-live="polite">
          {totals.chapters === 0 && totals.sections === 0
            ? "Nothing in the syllabus matches that."
            : `${totals.chapters} chapter${totals.chapters === 1 ? "" : "s"} and ` +
              `${totals.sections} sub-section${totals.sections === 1 ? "" : "s"} match.`}
        </p>
      )}

      {loading ? (
        <TreeSkeleton />
      ) : grades.length === 0 ? (
        <EmptyState
          icon="📕"
          title="The syllabus is unavailable"
          message="The textbook contents could not be read just now. You can still start a story on any topic from the home page."
          action={<Button onClick={() => navigate("/")}>Start a story</Button>}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          icon="🔍"
          title="No matching sections"
          message={`Nothing in the Grade 6-9 syllabus matches "${trimmed}". Try a shorter word.`}
          action={<Button variant="quiet" onClick={() => setQuery("")}>Clear the search</Button>}
        />
      ) : (
        <div className="syl-tree">
          {visible.map((grade) => {
            const gradeOpen = searching || openGrades.has(grade.grade);
            const regionId = `syllabus-grade-${grade.grade}`;
            return (
              <section className={`syl-grade ${gradeOpen ? "open" : ""}`} key={grade.grade}>
                <h3 style={{ margin: 0 }}>
                  <button
                    type="button"
                    className="syl-grade-toggle"
                    aria-expanded={gradeOpen}
                    aria-controls={regionId}
                    onClick={() => toggleGrade(grade.grade)}
                  >
                    <span className="syl-grade-num" aria-hidden="true">{grade.grade}</span>
                    <span className="syl-grade-text">
                      <span className="syl-grade-title">Grade {grade.grade}</span>
                      <span className="syl-grade-meta">
                        {" "}· {grade.chapters.length} chapter{grade.chapters.length === 1 ? "" : "s"}
                        {" "}· {countSections(grade)} sub-section{countSections(grade) === 1 ? "" : "s"}
                      </span>
                    </span>
                    <span className={`syl-chevron ${gradeOpen ? "open" : ""}`} aria-hidden="true">▶</span>
                  </button>
                </h3>

                {gradeOpen && (
                  <div className="syl-chapters" id={regionId}>
                    {grade.chapters.map((chapter) => {
                      const key = `${grade.grade}-${chapter.number}`;
                      const chapterOpen = searching || openChapters.has(key);
                      const sectionsId = `syllabus-sections-${key}`;
                      return (
                        <div className="syl-chapter" key={key}>
                          <div className="syl-chapter-row">
                            <button
                              type="button"
                              className="syl-chapter-toggle"
                              aria-expanded={chapterOpen}
                              aria-controls={sectionsId}
                              onClick={() => toggleChapter(key)}
                            >
                              <span className="syl-chapter-num" aria-hidden="true">{chapter.number}</span>
                              <span className="syl-chapter-text">
                                <span className="syl-chapter-title">
                                  <Highlight text={chapter.title} query={trimmed} />
                                </span>
                                <span className="syl-chapter-meta">
                                  {chapter.sections.length
                                    ? `${chapter.sections.length} sub-section${
                                        chapter.sections.length === 1 ? "" : "s"
                                      }`
                                    : "No sub-sections"}{" "}
                                  · {chapter.book}
                                </span>
                              </span>
                              <span className="page-badge">{pageLabel(chapter)}</span>
                              <span className={`syl-chevron ${chapterOpen ? "open" : ""}`} aria-hidden="true">▶</span>
                            </button>
                            <button
                              type="button"
                              className="syl-start"
                              onClick={() => startFrom(chapter.title, grade.grade)}
                              aria-label={`Start a story on the whole chapter "${chapter.title}" for Grade ${grade.grade}`}
                            >
                              Start chapter
                            </button>
                          </div>

                          {chapterOpen && (
                            chapter.sections.length ? (
                              <ul className="syl-sections" id={sectionsId}>
                                {chapter.sections.map((section) => (
                                  <li key={section.number}>
                                    <button
                                      type="button"
                                      className="syl-section"
                                      onClick={() => startFrom(section.title, grade.grade)}
                                      aria-label={`Start a story on "${section.title}" for Grade ${grade.grade}`}
                                    >
                                      <span className="syl-section-num" aria-hidden="true">{section.number}</span>
                                      <span className="syl-section-title">
                                        <Highlight text={section.title} query={trimmed} />
                                      </span>
                                      <span className="page-badge">{pageLabel(section)}</span>
                                      <span className="syl-section-go" aria-hidden="true">Start →</span>
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="syl-no-sections" id={sectionsId}>
                                This chapter is printed without sub-sections — start from the chapter itself.
                              </p>
                            )
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      <Toast message={toast?.message} tone={toast?.tone} onDismiss={clearToast} />
    </Card>
  );
}

// --- Helpers ---------------------------------------------------------------------

// "pp. 6–12" when a real range was derivable, "p. 148" when the row sits on a
// single page or the book ended before an end page could be worked out.
function pageLabel(row) {
  return row.has_range ? `pp. ${row.page_start}–${row.page_end}` : `p. ${row.page_start}`;
}

function countSections(grade) {
  return grade.chapters.reduce((n, c) => n + c.sections.length, 0);
}

function countTree(grades) {
  return grades.reduce(
    (acc, g) => ({
      chapters: acc.chapters + g.chapters.length,
      sections: acc.sections + countSections(g),
    }),
    { chapters: 0, sections: 0 }
  );
}

function toggled(set, value) {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

// Case-insensitive filter over chapter and sub-section titles. A chapter whose
// own title matches keeps all of its sub-sections; otherwise it keeps only the
// sub-sections that matched, and a grade with nothing left drops out entirely.
function filterGrades(grades, query) {
  const q = query.toLowerCase();
  if (!q) return grades;
  const out = [];
  for (const grade of grades) {
    const chapters = [];
    for (const chapter of grade.chapters) {
      const chapterHit = chapter.title.toLowerCase().includes(q);
      const sections = chapterHit
        ? chapter.sections
        : chapter.sections.filter((s) => s.title.toLowerCase().includes(q));
      if (chapterHit || sections.length) chapters.push({ ...chapter, sections });
    }
    if (chapters.length) out.push({ ...grade, chapters });
  }
  return out;
}

// Marks each occurrence of the search term inside a title.
function Highlight({ text, query }) {
  if (!query) return text;
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "ig"));
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <mark className="syl-mark" key={i}>{part}</mark> : part
      )}
    </>
  );
}

// Stands in for the tree while the syllabus loads.
function TreeSkeleton() {
  return (
    <div className="syl-tree" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div className="syl-grade" key={i} style={{ padding: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <SkeletonBlock width="38px" height={38} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
              <SkeletonBlock width="45%" height={14} />
              <SkeletonBlock width="30%" height={10} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
