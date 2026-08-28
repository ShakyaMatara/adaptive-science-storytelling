// Save or print a finished story — a self-contained, offline copy.
//
// WHY THIS EXISTS: the deployment context is Sri Lankan school and home
// connectivity, which is intermittent and metered. A learner who has generated a
// story once should not need the network to read it again, and a teacher should
// be able to put the same material in front of a class that has no devices at
// all. Both are the same artefact: a printable document. Printing to PDF is
// built into every current browser and phone, so "save it" and "print it" are
// one button.
//
// HOW: no PDF library is used or needed. `buildPrintDocument` returns a complete
// HTML document — its own <style>, no reference to the application's stylesheet —
// which is written into a hidden same-origin iframe and printed from there.
//
// An iframe was chosen over `window.open`, which pop-up blockers refuse without
// a user gesture they recognise, and over printing the live page, which would
// mean fighting the reader's own layout with override rules. The iframe document
// starts empty, so the print stylesheet describes the page completely and there
// is nothing to override. It is also inspectable: the same builder can be called
// on its own to check the output.

const FRAME_ID = "ascals-print-frame";

// Escape text coming from the API before it is put into the document.
function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDate(date = new Date()) {
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

// "pp. 40-41", "p. 52" — the citation line under a chapter, de-duplicated.
function citationFor(sources) {
  if (!sources || sources.length === 0) return "";
  const pages = [...new Set(
    sources
      .map((s) => s.page_citation || (s.page != null ? `p. ${s.page}` : ""))
      .filter(Boolean)
  )];
  return pages.join(", ");
}

// The textbook file(s) the whole story was grounded in, for the footer.
function textbookFiles(story) {
  const files = new Set();
  (story.chapters || []).forEach((chapter) => {
    (chapter.sources || []).forEach((source) => {
      if (source.source_file) files.add(source.source_file);
    });
  });
  return [...files];
}

const PRINT_CSS = `
  @page { size: A4; margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Georgia, "Times New Roman", serif;
    color: #1e293b;
    line-height: 1.6;
    font-size: 11.5pt;
  }
  .doc { max-width: 190mm; margin: 0 auto; padding: 12mm 0; }
  .doc-header { border-bottom: 2px solid #4f46e5; padding-bottom: 10px; margin-bottom: 18px; }
  .doc-title { font-size: 20pt; margin: 0 0 6px; color: #312e81; }
  .doc-meta { margin: 0; font-size: 9.5pt; color: #475569; font-family: "Segoe UI", system-ui, sans-serif; }
  .doc-meta span + span::before { content: " · "; }
  .summary {
    background: #eef2ff;
    border: 1px solid #c7d2fe;
    border-radius: 6px;
    padding: 8px 12px;
    margin: 0 0 20px;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 10pt;
  }
  .summary strong { color: #312e81; }
  .chapter { margin-bottom: 26px; page-break-inside: auto; }
  .chapter h2 {
    font-size: 14pt;
    margin: 0 0 8px;
    color: #312e81;
    page-break-after: avoid;
  }
  .chapter p { margin: 0 0 10px; text-align: justify; }
  .citation {
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 9pt;
    color: #475569;
    border-left: 3px solid #c7d2fe;
    padding-left: 8px;
    margin: 12px 0 16px;
  }
  .question {
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 10pt;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px 12px;
    margin: 0 0 10px;
    page-break-inside: avoid;
  }
  .question h3 { font-size: 10.5pt; margin: 0 0 8px; }
  .options { list-style: none; margin: 0; padding: 0; }
  .options li { padding: 3px 6px; margin-bottom: 3px; border-radius: 4px; }
  .options li.correct { background: #dcfce7; }
  .options li.wrong { background: #fee2e2; }
  .letter { font-weight: 700; margin-right: 8px; }
  .tag {
    font-size: 8pt;
    margin-left: 8px;
    padding: 1px 6px;
    border-radius: 999px;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    color: #475569;
  }
  .unanswered { color: #64748b; font-style: italic; margin: 6px 0 0; font-size: 9pt; }
  .doc-footer {
    margin-top: 28px;
    border-top: 1px solid #cbd5e1;
    padding-top: 10px;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 9pt;
    color: #475569;
  }
  .doc-footer p { margin: 0 0 3px; }
  @media print {
    body { background: #ffffff; }
    .doc { padding: 0; }
    /* Keep the answer shading when the browser's "background graphics" box is on. */
    .options li { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  }
`;

function renderQuestion(question) {
  const answered = question.user_answer_index !== null && question.user_answer_index !== undefined;
  const options = (question.options || []).map((option, i) => {
    const isCorrect = i === question.correct_index;
    const isChosen = answered && i === question.user_answer_index;
    const classes = [isCorrect ? "correct" : "", isChosen && !isCorrect ? "wrong" : ""]
      .filter(Boolean)
      .join(" ");
    const tags =
      (isCorrect ? '<span class="tag">correct answer</span>' : "") +
      (isChosen ? '<span class="tag">your answer</span>' : "");
    return `<li class="${classes}"><span class="letter">${String.fromCharCode(65 + i)}</span>${esc(option)}${tags}</li>`;
  }).join("");

  return `
    <div class="question">
      <h3>${esc(question.question_text)}</h3>
      <ul class="options">${options}</ul>
      ${answered ? "" : '<p class="unanswered">Not answered yet.</p>'}
    </div>`;
}

function renderChapter(chapter, grade) {
  const citation = citationFor(chapter.sources);
  const paragraphs = (chapter.paragraphs || []).map((p) => `<p>${esc(p)}</p>`).join("");
  const questions = (chapter.questions || []).map(renderQuestion).join("");
  return `
    <section class="chapter">
      <h2>Chapter ${esc(chapter.order)}: ${esc(chapter.title)}</h2>
      ${paragraphs}
      ${citation
        ? `<p class="citation">Based on the Grade ${esc(grade)} science textbook (${esc(citation)}).</p>`
        : ""}
      ${questions}
    </section>`;
}

/**
 * Build the complete printable document for a story.
 *
 * @param {object} story    the response from GET /api/sessions/<id>
 * @param {object} options
 * @param {string} options.learnerName  overrides story.learner_name if given
 * @param {Date}   options.date         overridable so the output can be tested
 * @returns {string} a full HTML document
 */
export function buildPrintDocument(story, options = {}) {
  const learnerName = options.learnerName || story.learner_name || "Learner";
  const date = formatDate(options.date instanceof Date ? options.date : new Date());
  const questions = (story.chapters || []).flatMap((c) => c.questions || []);
  const answered = questions.filter((q) => q.user_answer_index !== null && q.user_answer_index !== undefined);
  const correct = answered.filter((q) => q.is_correct).length;
  const badges = (story.badges || []).map((b) => b.name);
  const files = textbookFiles(story);
  const chapterCount = (story.chapters || []).length;
  const title = `${story.topic} — Grade ${story.grade}`;

  const chapters = (story.chapters || []).map((c) => renderChapter(c, story.grade)).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${esc(title)}</title>
<style>${PRINT_CSS}</style>
</head>
<body>
  <div class="doc">
    <header class="doc-header">
      <h1 class="doc-title">${esc(story.topic)}</h1>
      <p class="doc-meta">
        <span>Grade ${esc(story.grade)}</span>
        <span>${esc(learnerName)}</span>
        <span>${esc(date)}</span>
        <span>${esc(chapterCount)} ${chapterCount === 1 ? "chapter" : "chapters"}</span>
        <span>${story.is_complete ? "Completed" : "In progress"}</span>
      </p>
    </header>

    <p class="summary">
      <strong>${esc(story.points)} points</strong> ·
      ${answered.length > 0
        ? `${esc(correct)} of ${esc(answered.length)} questions answered correctly`
        : "no questions answered yet"}${badges.length ? ` · Badges: ${esc(badges.join(", "))}` : ""}
    </p>

    ${chapters}

    <footer class="doc-footer">
      <p>Adapted from the Grade ${esc(story.grade)} science textbook${
        files.length ? ` (${esc(files.join(", "))})` : ""
      }, published by the Sri Lankan Educational Publications Department.</p>
      <p>Story written for ${esc(learnerName)} and printed on ${esc(date)}. Keep this copy to read offline.</p>
    </footer>
  </div>
</body>
</html>`;
}

// Remove any frame left over from an earlier export.
function clearFrame() {
  const existing = document.getElementById(FRAME_ID);
  if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
}

/**
 * Render the printable document into a hidden iframe and (by default) open the
 * browser's print dialogue, from which the learner can save a PDF or print.
 *
 * @param {object}  story    the response from GET /api/sessions/<id>
 * @param {object}  options  as buildPrintDocument, plus:
 * @param {boolean} options.autoPrint  set false to build the document without
 *        opening the dialogue — used to inspect the output.
 * @returns {HTMLIFrameElement} the frame holding the document
 */
export function exportStory(story, options = {}) {
  const { autoPrint = true } = options;
  clearFrame();

  const frame = document.createElement("iframe");
  frame.id = FRAME_ID;
  frame.setAttribute("title", `Printable copy of ${story.topic}`);
  frame.setAttribute("aria-hidden", "true");
  // Off-screen rather than display:none — a frame that is not laid out has
  // nothing to print in some browsers.
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:1px;height:1px;opacity:0;border:0;";
  document.body.appendChild(frame);

  const doc = frame.contentDocument || frame.contentWindow.document;
  doc.open();
  doc.write(buildPrintDocument(story, options));
  doc.close();

  if (autoPrint) {
    const view = frame.contentWindow;
    // Tidy up once the dialogue closes, whichever way it closed.
    view.addEventListener?.("afterprint", () => clearFrame());
    // Give the document a frame to lay out before printing it.
    setTimeout(() => {
      view.focus();
      view.print();
    }, 60);
  }
  return frame;
}

export default exportStory;
