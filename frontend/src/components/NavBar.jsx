// Persistent top navigation. Rendered only when a learner is signed in, so the
// login screen keeps the plain centred layout it had before.
//
// On narrow screens the links collapse behind a menu button; the learner's name
// and the log-out control stay visible throughout.

import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Home", icon: "🏠", end: true },
  { to: "/browse", label: "Syllabus", icon: "📚" },
  { to: "/library", label: "My stories", icon: "📖" },
  { to: "/progress", label: "Progress", icon: "📊" },
  { to: "/revise", label: "Revise", icon: "🎯" },
  { to: "/achievements", label: "Achievements", icon: "🏅" },
];

export default function NavBar({ profile, onLogout }) {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close the mobile menu whenever the route changes.
  useEffect(() => setOpen(false), [location.pathname]);

  return (
    <nav className="navbar" aria-label="Main">
      <div className="navbar-inner">
        <NavLink to="/" className="navbar-brand">
          <span aria-hidden="true">🔬</span> Science Story Quest
        </NavLink>

        <button
          className="navbar-toggle"
          aria-expanded={open}
          aria-label="Toggle navigation"
          onClick={() => setOpen((o) => !o)}
        >
          ☰
        </button>

        <div className={`navbar-links ${open ? "open" : ""}`}>
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `navbar-link ${isActive ? "active" : ""}`}
            >
              <span aria-hidden="true">{l.icon}</span> {l.label}
            </NavLink>
          ))}
        </div>

        <div className="navbar-user">
          {profile && <span className="navbar-name">{profile.display_name}</span>}
          <button className="navbar-logout" onClick={onLogout}>Log out</button>
        </div>
      </div>
    </nav>
  );
}
