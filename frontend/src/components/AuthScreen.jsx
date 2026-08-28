// Login / register screen, extracted unchanged from App.jsx.

import { useState } from "react";

export default function AuthScreen({ loading, onSubmit }) {
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
