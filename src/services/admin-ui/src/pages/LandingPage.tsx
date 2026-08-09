import { Link } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function LandingPage() {
  const { isAuthenticated, username } = useAuth();

  return (
    <>
      <h1>Minder Admin</h1>
      <p className="hint">
        {isAuthenticated
          ? `Logged in as ${username}.`
          : "Log in from either tool below to make changes; browsing is open."}
      </p>
      <ul>
        <li>
          <Link to="/plugin-config">Plugin Configuration</Link> — edit news
          feeds, weather locations, and other plugin settings.
        </li>
        <li>
          <Link to="/model-management">Model Management</Link> — list, pull,
          delete, and test-prompt local Ollama models.
        </li>
      </ul>
    </>
  );
}
