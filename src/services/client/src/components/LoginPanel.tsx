import { useState } from "react";

import { useAuth } from "../lib/auth";

export function LoginPanel({
  onStatus,
}: {
  onStatus: (msg: string, isError?: boolean) => void;
}) {
  const { isAuthenticated, username, login, register, logout } = useAuth();
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [showRegister, setShowRegister] = useState(false);

  async function handleLogin() {
    onStatus("Logging in…");
    try {
      await login(user, password);
      onStatus("Logged in.");
    } catch (e) {
      onStatus(e instanceof Error ? e.message : String(e), true);
    }
  }

  async function handleRegister() {
    onStatus("Registering…");
    try {
      await register(user, email, password);
      onStatus('Registered — now click "Log in".');
    } catch (e) {
      onStatus(e instanceof Error ? e.message : String(e), true);
    }
  }

  if (isAuthenticated) {
    return (
      <div id="auth">
        <div id="session">
          Logged in as <strong>{username}</strong>{" "}
          <button type="button" onClick={logout}>
            Log out
          </button>
        </div>
      </div>
    );
  }

  return (
    <div id="auth">
      <div id="login-box">
        <input
          placeholder="username"
          autoComplete="username"
          value={user}
          onChange={(e) => setUser(e.target.value)}
        />
        <input
          type="password"
          placeholder="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="button" onClick={handleLogin}>
          Log in
        </button>
        <button type="button" onClick={() => setShowRegister((v) => !v)}>
          New user? Register
        </button>
        {showRegister && (
          <div id="register-box">
            <input
              placeholder="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <button type="button" onClick={handleRegister}>
              Register
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
