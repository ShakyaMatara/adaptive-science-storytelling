// Thin wrapper around fetch for talking to the Django API.
// All calls are plain JSON; the backend runs on :8000 during development.
//
// ORDERING CONVENTION — please keep to it when adding a call.
// The file has three parts, in this order:
//   1. token helpers and the shared `request()` function;
//   2. `logout()`, which is token-only and belongs with them;
//   3. every endpoint wrapper, in ONE alphabetical list by function name.
// A single alphabetical list (rather than thematic groups) is used because this
// file is edited from several directions at once: alphabetical order gives a new
// call exactly one correct position, so two additions cannot land in the same
// place. Keep one blank line between functions and a short comment naming the
// HTTP method and path.
const BASE_URL = "http://localhost:8000/api";

// --- Auth token, stored in localStorage ---
// (Standard teaching approach for an SPA. Production would use httpOnly cookies
//  + HTTPS + token refresh — noted as future work in the report.)
export function getToken() {
  return localStorage.getItem("token");
}
export function setToken(token) {
  localStorage.setItem("token", token);
}
export function clearToken() {
  localStorage.removeItem("token");
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Token ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  let data = null;
  try {
    data = await res.json();
  } catch {
    // no/invalid JSON body — leave data as null
  }

  // Token missing/expired: clear it and let the app fall back to the login screen.
  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new Event("auth-expired"));
    throw new Error("Your session has expired — please log in again.");
  }
  if (!res.ok) {
    const message =
      data && (data.error || data.detail) ? data.error || data.detail : `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

// Token-only; makes no request.
export function logout() {
  clearToken();
}

// --- Endpoints (alphabetical) -------------------------------------------------

// POST /api/sessions/<id>/ask — grounded Q&A about the topic.
export function ask(sessionId, question) {
  return request(`/sessions/${sessionId}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

// POST /api/sessions/<id>/finish — end a story early and go to the results.
export function finishSession(sessionId) {
  return request(`/sessions/${sessionId}/finish`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// GET /api/auth/me — the signed-in learner's profile.
export function getMe() {
  return request("/auth/me");
}

// GET /api/me/progress — concept mastery and headline counters.
export function getProgress() {
  return request("/me/progress");
}

// GET /api/sessions/<id> — full state of one story: chapters, questions, badges.
export function getSession(sessionId) {
  return request(`/sessions/${sessionId}`);
}

// GET /api/topics — the fixed suggestion list.
export function getTopics() {
  return request("/topics");
}

// POST /api/auth/login
export function login(username, password) {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

// POST /api/sessions/<id>/next — adapt, award badges, and generate the next chapter.
export function nextChapter(sessionId) {
  return request(`/sessions/${sessionId}/next`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// POST /api/auth/register
export function register(username, password, displayName) {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, display_name: displayName }),
  });
}

// POST /api/sessions — start (or resume) a story on a topic.
export function startSession(topic, grade) {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({ topic, grade }),
  });
}

// POST /api/sessions/<id>/answer — record one answer.
export function submitAnswer(sessionId, payload) {
  return request(`/sessions/${sessionId}/answer`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
