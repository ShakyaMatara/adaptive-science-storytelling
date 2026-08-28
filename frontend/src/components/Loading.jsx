// The generation loader, moved here unchanged from App.jsx: an animated spinner
// with a message that cycles every ~2s. Shown during the long model calls
// (starting a session, generating the next chapter).

import { useEffect, useState } from "react";

// Short phrases the loader cycles through while a chapter is being generated.
const LOADING_MESSAGES = [
  "Gathering textbook facts…",
  "Writing your story…",
  "Thinking up the questions…",
  "Almost there…",
];

export default function Loading() {
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
