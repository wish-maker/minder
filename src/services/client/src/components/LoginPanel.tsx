import { useState } from "react";

import { useAuth } from "../lib/auth";

const inputClass =
  "rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none dark:border-gray-600 dark:bg-gray-800";
const buttonClass =
  "rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-800";

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
      <div className="mb-4 flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm dark:border-gray-700 dark:bg-gray-900">
        <span>
          Logged in as <strong className="font-semibold">{username}</strong>
        </span>
        <button type="button" onClick={logout} className={buttonClass}>
          Log out
        </button>
      </div>
    );
  }

  return (
    <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
      <div className="flex flex-wrap items-center gap-2">
        <input
          className={inputClass}
          placeholder="username"
          autoComplete="username"
          value={user}
          onChange={(e) => setUser(e.target.value)}
        />
        <input
          className={inputClass}
          type="password"
          placeholder="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="button" onClick={handleLogin} className={buttonClass}>
          Log in
        </button>
        <button
          type="button"
          onClick={() => setShowRegister((v) => !v)}
          className="text-sm text-indigo-600 hover:underline dark:text-indigo-400"
        >
          New user? Register
        </button>
      </div>
      {showRegister && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3 dark:border-gray-800">
          <input
            className={inputClass}
            placeholder="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button type="button" onClick={handleRegister} className={buttonClass}>
            Register
          </button>
        </div>
      )}
    </div>
  );
}
