// Thin wrapper around fetch for talking to the Django API.
// All calls are plain JSON; the backend runs on :8000 during development.
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

// --- Auth ---
export function register(username, password, displayName) {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, display_name: displayName }),
  });
}
export function login(username, password) {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}
export function getMe() {
  return request("/auth/me");
}

export function getProgress() {
  return request("/me/progress");
}
export function logout() {
  clearToken();
}

// --- App data ---
export function getTopics() {
  return request("/topics");
}

export function startSession(topic, grade) {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({ topic, grade }),
  });
}

export function submitAnswer(sessionId, payload) {
  return request(`/sessions/${sessionId}/answer`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function nextChapter(sessionId) {
  return request(`/sessions/${sessionId}/next`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function ask(sessionId, question) {
  return request(`/sessions/${sessionId}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function finishSession(sessionId) {
  return request(`/sessions/${sessionId}/finish`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
