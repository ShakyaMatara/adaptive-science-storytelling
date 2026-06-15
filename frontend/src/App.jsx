import { useState, useEffect } from "react";
import {
  getTopics,
  startSession,
  submitAnswer,
  nextChapter,
  ask,
  finishSession,
  register,
  login,
  logout,
  getMe,
  getProgress,
  getToken,
  setToken,
} from "./api";

// Short phrases the loader cycles through while a chapter is being generated.
const LOADING_MESSAGES = [
  "Gathering textbook facts…",
  "Writing your story…",
  "Thinking up the questions…",
  "Almost there…",
];

// The whole app is one component with a few "screens" switched by `screen`
// (plus the login screen when there is no token). No router is needed for a
// small prototype — conditional rendering is enough.
export default function App() {
  const [screen, setScreen] = useState("start"); // 'start' | 'story' | 'complete' | 'progress'

  // Start-screen inputs
  const [topics, setTopics] = useState([]);
  const [topic, setTopic] = useState(""); // free-typed topic (chips just fill it in)
  const [grade, setGrade] = useState(null); // selected grade (6-9)

  // Live session state
  const [sessionId, setSessionId] = useState(null);
  const [chapter, setChapter] = useState(null); // {chapter_id, order, title, paragraphs, questions}
  const [totalChapters, setTotalChapters] = useState(0); // planned chapters in this story
  const [answers, setAnswers] = useState({}); // question_id -> {selectedIndex, isCorrect, correctIndex, feedback}
  const [chapterComplete, setChapterComplete] = useState(false);
  const [points, setPoints] = useState(0);
  const [difficulty, setDifficulty] = useState(3);
  const [badges, setBadges] = useState([]); // all badge names earned so far
  const [justEarned, setJustEarned] = useState([]); // badges awarded at the last chapter boundary
  const [sources, setSources] = useState([]); // textbook refs for the current chapter (RAG)
  const [chapterStart, setChapterStart] = useState(0); // for response time
  const [resumed, setResumed] = useState(false); // true when continuing an existing story (Phase C)

  // UI state
  const [loading, setLoading] = useState(false);       // any in-flight request
  const [generating, setGenerating] = useState(false); // a long LLM call (start / next chapter)
  const [error, setError] = useState("");

  // Auth state (token persisted in localStorage; profile holds display info)
  const [token, setTokenState] = useState(getToken());
  const [profile, setProfile] = useState(null);
  const [progress, setProgress] = useState([]); // concept mastery (Phase 4)

  // Load the topic list once the user is authenticated.
  useEffect(() => {
    if (!token) return;
    getTopics()
      .then((list) => setTopics(list)) // used only as clickable suggestions now
      .catch((e) => setError(e.message));
  }, [token]);

  // With a token, load the profile; clear auth state if the token ever expires.
  useEffect(() => {
    if (token) getMe().then(setProfile).catch(() => {});
    const onExpired = () => {
      setTokenState(null);
      setProfile(null);
    };
    window.addEventListener("auth-expired", onExpired);
    return () => window.removeEventListener("auth-expired", onExpired);
  }, [token]);

  // Begin a new session: create it and load the first chapter.
  async function handleStart() {
    setError("");
    setLoading(true);
    setGenerating(true);
    try {
      const data = await startSession(topic.trim(), grade);
      // Syllabus gate: the topic isn't in this grade's textbook — explain and stop.
      if (data.in_syllabus === false) {
        setError(
          `"${topic.trim()}" isn't in your Grade ${grade} science syllabus. ` +
            (data.reason || "Try a topic from your textbook.")
        );
        return;
      }
      setSessionId(data.session_id);
      setChapter(data.chapter);
      setTotalChapters(data.total_chapters || 0);
      setPoints(data.points);
      setDifficulty(data.difficulty);
      setBadges(data.badges);
      setJustEarned([]);
      setSources(data.sources || []);
      setAnswers(data.answers || {}); // rehydrate prior answers when resuming a story
      setChapterComplete(data.chapter_complete || false); // 0-question chapters arrive complete
      setResumed(!!data.resumed);
      setChapterStart(Date.now());
      setScreen("story");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  }

  // Submit one question's answer; record per-question feedback.
  async function handleAnswer(question, optionIndex) {
    if (answers[question.question_id] || loading) return; // ignore once answered
    setError("");
    setLoading(true);
    try {
      const res = await submitAnswer(sessionId, {
        question_id: question.question_id,
        answer_index: optionIndex,
        response_time_ms: Date.now() - chapterStart,
      });
      setAnswers((prev) => ({
        ...prev,
        [question.question_id]: {
          selectedIndex: optionIndex,
          isCorrect: res.is_correct,
          correctIndex: res.correct_index,
          feedback: res.feedback,
        },
      }));
      setPoints(res.points);
      setChapterComplete(res.chapter_complete);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Move to the next chapter (where difficulty adapts + badges are awarded), or finish.
  async function handleNext() {
    setError("");
    setLoading(true);
    setGenerating(true);
    try {
      const data = await nextChapter(sessionId);
      setPoints(data.points);
      setBadges(data.badges);
      setJustEarned(data.badges_awarded || []);
      if (data.is_complete) {
        setScreen("complete");
      } else {
        setChapter(data.chapter);
        setTotalChapters(data.total_chapters || totalChapters);
        setDifficulty(data.difficulty);
        setSources(data.sources || []);
        setAnswers({});
        setChapterComplete(data.chapter_complete || false); // 0-question chapters arrive complete
        setResumed(false);
        setChapterStart(Date.now());
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setGenerating(false);
    }
  }

  // End the session early (before the planned last chapter) and jump to the results.
  async function handleFinishEarly() {
    setError("");
    setLoading(true);
    try {
      const data = await finishSession(sessionId);
      setPoints(data.points);
      setBadges(data.badges);
      setScreen("complete");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Reset back to the start screen for a fresh run.
  function handleRestart() {
    setSessionId(null);
    setChapter(null);
    setTotalChapters(0);
    setAnswers({});
    setChapterComplete(false);
    setPoints(0);
    setDifficulty(3);
    setBadges([]);
    setJustEarned([]);
    setSources([]);
    setResumed(false);
    setError("");
    setScreen("start");
  }

  // --- Auth handlers ---
  async function handleAuth(mode, username, password, displayName) {
    setError("");
    setLoading(true);
    try {
      const data =
        mode === "register"
          ? await register(username, password, displayName)
          : await login(username, password);
      setToken(data.token); // persist to localStorage
      setProfile(data.profile);
      setTokenState(data.token); // re-render into the app
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    logout();
    setTokenState(null);
    setProfile(null);
    handleRestart(); // also clear any in-progress session state
  }

  async function handleShowProgress() {
    setError("");
    setLoading(true);
    try {
      const data = await getProgress();
      setProgress(data.progress || []);
      setScreen("progress");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Not logged in → show the auth screen.
  if (!token) {
    return (
      <div className="app">
        <header className="app-header">
          <h1>🔬 Science Story Quest</h1>
          <p className="tagline">Learn science through adaptive stories</p>
        </header>
        {error && <div className="banner banner-error">⚠️ {error}</div>}
        <AuthScreen loading={loading} onSubmit={handleAuth} />
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🔬 Science Story Quest</h1>
        <p className="tagline">Learn science through adaptive stories</p>
        {profile && (
          <p className="userbar">
            Logged in as <strong>{profile.display_name}</strong>{" · "}
            <button className="link-btn" onClick={handleLogout}>Log out</button>
          </p>
        )}
      </header>

      {error && <div className="banner banner-error">⚠️ {error}</div>}

      {screen === "start" &&
        (generating ? (
          <div className="card"><Loading /></div>
        ) : (
          <StartScreen
            topics={topics}
            topic={topic}
            setTopic={setTopic}
            grade={grade}
            setGrade={setGrade}
            loading={loading}
            onStart={handleStart}
            onShowProgress={handleShowProgress}
          />
        ))}

      {screen === "story" && chapter &&
        (generating ? (
          <div className="card"><Loading /></div>
        ) : (
          <StoryScreen
            chapter={chapter}
            sessionId={sessionId}
            grade={grade}
            resumed={resumed}
            sources={sources}
            points={points}
            difficulty={difficulty}
            totalChapters={totalChapters}
            badges={badges}
            justEarned={justEarned}
            answers={answers}
            chapterComplete={chapterComplete}
            loading={loading}
            onAnswer={handleAnswer}
            onNext={handleNext}
            onFinish={handleFinishEarly}
          />
        ))}

      {screen === "complete" && (
        <CompleteScreen
          points={points}
          badges={badges}
          onRestart={handleRestart}
          onShowProgress={handleShowProgress}
        />
      )}

      {screen === "progress" && (
        <ProgressScreen progress={progress} onBack={() => setScreen("start")} />
      )}
    </div>
  );
}

// --- Screen 1: pick a topic + grade ------------------------------------------
function StartScreen({ topics, topic, setTopic, grade, setGrade, loading, onStart, onShowProgress }) {
  const canStart = topic.trim() && grade && !loading;
  return (
    <div className="card">
      <h2>Start your adventure</h2>

      <label className="field-label" htmlFor="topic">What topic do you want to learn?</label>
      <input
        id="topic"
        className="text-input"
        value={topic}
        placeholder="e.g. Photosynthesis"
        onChange={(e) => setTopic(e.target.value)}
      />
      {topics.length > 0 && (
        <div className="chips">
          <span className="chips-label">Try:</span>
          {topics.map((t) => (
            <button key={t.slug} type="button" className="chip" onClick={() => setTopic(t.title)}>
              {t.title}
            </button>
          ))}
        </div>
      )}

      <p className="field-label">Your grade</p>
      <div className="grade-grid">
        {[6, 7, 8, 9].map((g) => (
          <button
            key={g}
            className={`grade-btn ${grade === g ? "selected" : ""}`}
            onClick={() => setGrade(g)}
          >
            Grade {g}
          </button>
        ))}
      </div>

      <button className="primary-btn" disabled={!canStart} onClick={onStart}>
        {loading ? "Starting…" : "Start learning →"}
      </button>

      <p className="auth-switch">
        <button className="link-btn" onClick={onShowProgress}>📊 My progress</button>
      </p>
    </div>
  );
}

// --- Screen 2: read the chapter, answer its questions ------------------------
function StoryScreen({ chapter, sessionId, grade, resumed, sources, points, difficulty, totalChapters, badges, justEarned, answers, chapterComplete, loading, onAnswer, onNext, onFinish }) {
  return (
    <div className="card">
      <StatusBar points={points} difficulty={difficulty} badges={badges} order={chapter.order} total={totalChapters} />

      {resumed && <p className="badge-toast">📖 Continuing your story…</p>}

      {justEarned.length > 0 && (
        <p className="badge-toast">🏅 New badge: {justEarned.join(", ")}</p>
      )}

      <h2 className="chapter-title">{chapter.title}</h2>
      <div className="story">
        {chapter.paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>
      <SourceNote grade={grade} sources={sources} />

      {chapter.questions.map((q) => (
        <QuestionBlock
          key={q.question_id}
          question={q}
          answer={answers[q.question_id]}
          loading={loading}
          onAnswer={onAnswer}
        />
      ))}

      {chapterComplete && (
        <div className="feedback feedback-correct chapter-done">
          <p>Chapter complete! 🎉</p>
          <button className="primary-btn" onClick={onNext}>
            {loading ? "Loading…" : "Continue →"}
          </button>
        </div>
      )}

      {/* Keyed by chapter so the panel (and any previous answer) resets per chapter. */}
      <QnAPanel key={chapter.chapter_id} sessionId={sessionId} />

      <div className="finish-early">
        <button className="link-btn" onClick={onFinish} disabled={loading}>
          Finish &amp; see results →
        </button>
      </div>
    </div>
  );
}

// Collapsible "Ask about this topic" panel — grounded Q&A (Phase 5).
// Answers come only from the grade's textbook; never affects points/difficulty.
function QnAPanel({ sessionId }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    if (!question.trim() || loading) return;
    setLoading(true);
    setErr("");
    setResult(null);
    try {
      setResult(await ask(sessionId, question.trim()));
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="qna">
      <button className="qna-toggle" onClick={() => setOpen(!open)}>
        💬 Ask about this topic {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="qna-body">
          <div className="qna-row">
            <input
              className="text-input"
              value={question}
              placeholder="Ask a question about this topic…"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            />
            <button className="primary-btn qna-ask" disabled={!question.trim() || loading} onClick={submit}>
              {loading ? "…" : "Ask"}
            </button>
          </div>
          {err && <p className="qna-error">⚠️ {err}</p>}
          {result && (
            <div className={`qna-answer ${result.in_syllabus === false || result.blocked ? "qna-refused" : ""}`}>
              <p>{result.answer}</p>
              {result.sources && result.sources.length > 0 && (
                <p className="sources">
                  📖 Sources: {[...new Set(result.sources.map((s) => `p.${s.page}`))].join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// One question with its 4 options and per-question feedback.
function QuestionBlock({ question, answer, loading, onAnswer }) {
  return (
    <div className="question-block">
      <h3 className="question">{question.question}</h3>
      <div className="options">
        {question.options.map((opt, i) => (
          <button
            key={i}
            className={`option-btn ${optionClass(i, answer)}`}
            disabled={!!answer || loading}
            onClick={() => onAnswer(question, i)}
          >
            <span className="option-letter">{String.fromCharCode(65 + i)}</span>
            {opt}
          </button>
        ))}
      </div>
      {answer && (
        <div className={`feedback ${answer.isCorrect ? "feedback-correct" : "feedback-wrong"}`}>
          <p>{answer.feedback}</p>
        </div>
      )}
    </div>
  );
}

// --- Screen 3: final score + badges ------------------------------------------
function CompleteScreen({ points, badges, onRestart, onShowProgress }) {
  return (
    <div className="card center">
      <h2>🎉 Session complete!</h2>
      <p className="final-points">{points} points</p>
      <p className="field-label">Badges earned</p>
      {badges.length ? (
        <BadgeList badges={badges} />
      ) : (
        <p className="muted">No badges this time — try again to earn some!</p>
      )}
      <button className="primary-btn" onClick={onRestart}>Start over</button>
      <p className="auth-switch">
        <button className="link-btn" onClick={onShowProgress}>📊 My progress</button>
      </p>
    </div>
  );
}

// --- Screen 4: cross-session concept mastery (Phase 4) -----------------------
function ProgressScreen({ progress, onBack }) {
  return (
    <div className="card">
      <h2>📊 Your progress</h2>
      {progress.length === 0 ? (
        <p className="muted">No progress yet — finish a session to see your strengths and weaknesses.</p>
      ) : (
        progress.map((t) => (
          <div key={t.topic} className="progress-topic">
            <h3>{t.topic}</h3>
            {t.concepts.map((c) => (
              <div key={c.concept} className="progress-row">
                <span className="progress-concept">{c.concept}</span>
                <span className="mastery-bar">
                  <span className="mastery-fill" style={{ width: `${Math.round(c.mastery * 100)}%` }} />
                </span>
                <span className="progress-num">{c.correct}/{c.attempts}</span>
              </div>
            ))}
          </div>
        ))
      )}
      <button className="primary-btn" onClick={onBack}>← Back</button>
    </div>
  );
}

// --- Small shared pieces ------------------------------------------------------
function StatusBar({ points, difficulty, badges, order, total }) {
  return (
    <div className="status-bar">
      <span className="pill pill-points">⭐ {points} pts</span>
      <span className="pill">{total ? `Chapter ${order} of ${total}` : `Chapter ${order}`}</span>
      <span className="pill difficulty">
        Difficulty <DifficultyDots level={difficulty} />
      </span>
      {badges.length > 0 && <BadgeList badges={badges} small />}
    </div>
  );
}

// Five dots, filled up to the current difficulty level (1–5).
function DifficultyDots({ level }) {
  return (
    <span className="dots">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={`dot ${n <= level ? "filled" : ""}`} />
      ))}
    </span>
  );
}

function BadgeList({ badges, small }) {
  return (
    <span className={`badges ${small ? "badges-small" : ""}`}>
      {badges.map((b) => (
        <span key={b} className="badge-chip">🏅 {b}</span>
      ))}
    </span>
  );
}

// Animated loader with a message that cycles every ~2s. Shown during the long
// LLM calls (starting a session, generating the next chapter).
function Loading() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((n) => (n + 1) % LOADING_MESSAGES.length), 2000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="loading">
      <div className="spinner" aria-hidden="true" />
      <p className="loading-msg">{LOADING_MESSAGES[i]}</p>
    </div>
  );
}

// Small "Based on: Grade X textbook (p.12)" line under a textbook-grounded chapter.
// Renders nothing in mock mode (no sources) or if the chapter wasn't grounded.
function SourceNote({ grade, sources }) {
  if (!sources || sources.length === 0) return null;
  const pages = [...new Set(sources.map((s) => s.page).filter((p) => p != null))];
  const pageText = pages.length ? ` (p.${pages.join(", p.")})` : "";
  return <p className="sources">📖 Based on: Grade {grade} textbook{pageText}</p>;
}

// How an option button should look once its question is answered:
// the correct option turns green; a wrong pick turns red.
function optionClass(index, answer) {
  if (!answer) return "";
  if (index === answer.correctIndex) return "correct";
  if (index === answer.selectedIndex) return "wrong";
  return "dimmed";
}

// --- Login / register screen -------------------------------------------------
function AuthScreen({ loading, onSubmit }) {
  const [mode, setMode] = useState("login"); // 'login' | 'register'
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  const isRegister = mode === "register";
  const canSubmit = username.trim() && password && !loading;

  function submit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit(mode, username.trim(), password, displayName.trim());
  }

  return (
    <div className="card">
      <h2>{isRegister ? "Create an account" : "Welcome back"}</h2>
      <form onSubmit={submit}>
        <label className="field-label" htmlFor="username">Username</label>
        <input
          id="username"
          className="text-input"
          value={username}
          autoComplete="username"
          onChange={(e) => setUsername(e.target.value)}
        />

        {isRegister && (
          <>
            <label className="field-label" htmlFor="display">Display name (optional)</label>
            <input
              id="display"
              className="text-input"
              value={displayName}
              placeholder="e.g. Amaya"
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </>
        )}

        <label className="field-label" htmlFor="password">Password</label>
        <input
          id="password"
          className="text-input"
          type="password"
          value={password}
          autoComplete={isRegister ? "new-password" : "current-password"}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button className="primary-btn" type="submit" disabled={!canSubmit}>
          {loading ? "Please wait…" : isRegister ? "Sign up" : "Log in"}
        </button>
      </form>

      <p className="auth-switch">
        {isRegister ? "Already have an account?" : "New here?"}{" "}
        <button className="link-btn" onClick={() => setMode(isRegister ? "login" : "register")}>
          {isRegister ? "Log in" : "Create one"}
        </button>
      </p>
    </div>
  );
}
