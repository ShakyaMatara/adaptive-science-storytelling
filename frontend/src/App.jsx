// Application shell: authentication gate, persistent navigation, and the routes.
//
// Everything that used to be switched by a `screen` state variable is now a
// route, and the story-reading UI lives in its own component. The behaviour of
// each screen is unchanged — see components/StoryReader.jsx and session.jsx,
// which hold the extracted markup and state respectively.

import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { getMe, getToken, login, logout, register, setToken } from "./api";
import AuthScreen from "./components/AuthScreen";
import NavBar from "./components/NavBar";
import { Toast } from "./components/ui";
import AchievementsPage from "./pages/AchievementsPage";
import BrowsePage from "./pages/BrowsePage";
import HomePage from "./pages/HomePage";
import LibraryPage from "./pages/LibraryPage";
import ProgressPage from "./pages/ProgressPage";
import RevisePage from "./pages/RevisePage";
import StoryPage from "./pages/StoryPage";
import { SessionProvider, useSession } from "./session";

export default function App() {
  // Auth state (token persisted in localStorage; profile holds display info)
  const [token, setTokenState] = useState(getToken());
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Clear auth state if the token ever expires. Registered once, not per token.
  useEffect(() => {
    const onExpired = () => {
      setTokenState(null);
      setProfile(null);
    };
    window.addEventListener("auth-expired", onExpired);
    return () => window.removeEventListener("auth-expired", onExpired);
  }, []);

  // Load the profile only when it is not already known: logging in returns the
  // profile with the token, so the common path needs no request at all. This
  // fetch is for a returning visit, where only the stored token survives.
  useEffect(() => {
    if (token && !profile) getMe().then(setProfile).catch(() => {});
  }, [token, profile]);

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
  }

  // Not logged in → show the auth screen (no navigation bar).
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
    <SessionProvider>
      <NavBar profile={profile} onLogout={handleLogout} />
      <div className="app">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/browse" element={<BrowsePage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/revise" element={<RevisePage />} />
          <Route path="/achievements" element={<AchievementsPage />} />
          <Route path="/story/:id" element={<StoryPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <SessionErrorToast />
      </div>
    </SessionProvider>
  );
}

// Surfaces any error raised by the shared story session, wherever it happened.
function SessionErrorToast() {
  const session = useSession();
  return (
    <Toast
      message={session.error}
      tone="error"
      duration={0}
      onDismiss={() => session.setError("")}
    />
  );
}
