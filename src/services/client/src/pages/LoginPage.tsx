import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { StatusLine } from "../components/StatusLine";
import { friendlyErrorMessage, oidcLoginUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  cardClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";

/** Local username/password login — the path that actually works when the client
 * is reached directly (e.g. http://localhost:8009 or a LAN IP), where the SSO
 * button can't: OIDC redirects the browser to the Traefik-only `*.minder.local`
 * hostnames, which need real DNS + TLS the direct-port access path doesn't have.
 * The api-gateway's local JWT auth (`/v1/auth/login` + `/v1/auth/register`) is
 * reachable on the same `apiBaseUrl` the rest of the client already uses, so this
 * form works over plain localhost. The SSO button below is shown only when
 * VITE_OIDC_LOGIN_URL is configured (a Traefik + real-domain deployment) — no
 * dead-end button over localhost. */
export function LoginPage() {
  const { isAuthenticated, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  // A failed OIDC/SSO redirect (denied consent, expired code, ...) lands here
  // via AuthCallbackPage's navigate("/login", {state: {oidcError}}) -- surface
  // it instead of silently landing on a blank login form.
  const [error, setError] = useState(
    (location.state as { oidcError?: string } | null)?.oidcError ?? "",
  );

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "register") {
        await register(username, email, password);
      }
      // register() only creates the account (no token), so log in either way.
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(friendlyErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
        {mode === "login" ? "Log in" : "Create an account"}
      </h1>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        {mode === "login"
          ? "Sign in with your Minder account to make changes. Browsing stays open without logging in."
          : "Create a local Minder account, then you'll be signed in."}
      </p>

      <form onSubmit={handleSubmit} className={`flex flex-col gap-3 ${cardClass}`}>
        <div>
          <label
            htmlFor="login-username"
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Username
          </label>
          <input
            id="login-username"
            className={inputClass}
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>

        {mode === "register" && (
          <div>
            <label
              htmlFor="login-email"
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Email
            </label>
            <input
              id="login-email"
              className={inputClass}
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
        )}

        <div>
          <label
            htmlFor="login-password"
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Password
          </label>
          <input
            id="login-password"
            className={inputClass}
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <button type="submit" disabled={busy} className={primaryButtonClass}>
          {busy
            ? "Please wait…"
            : mode === "login"
              ? "Log in"
              : "Create account & log in"}
        </button>

        <StatusLine isError>{error}</StatusLine>
      </form>

      <p className="mt-3 text-center text-sm text-gray-600 dark:text-gray-400">
        {mode === "login" ? (
          <>
            No account yet?{" "}
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setError("");
              }}
              className="underline hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              Create one
            </button>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setError("");
              }}
              className="underline hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              Log in
            </button>
          </>
        )}
      </p>

      {/* Only offer SSO when it's actually configured (VITE_OIDC_LOGIN_URL set
          to a real Traefik hostname). Otherwise the button dead-ends: the old
          baked-in api.minder.local can't resolve over a plain localhost/LAN
          address, so a real domain + TLS is required for the OIDC flow to
          complete. Unconfigured → local login above is the working path. */}
      {oidcLoginUrl && (
        <>
          <div className="my-5 flex items-center gap-3 text-xs text-gray-400">
            <span className="h-px flex-1 bg-gray-200 dark:bg-gray-800" />
            or
            <span className="h-px flex-1 bg-gray-200 dark:bg-gray-800" />
          </div>

          <a
            href={oidcLoginUrl}
            className={`block text-center ${secondaryButtonClass}`}
          >
            Sign in with SSO (Authelia)
          </a>
          <p className="mt-2 text-center text-xs text-gray-500 dark:text-gray-400">
            SSO requires reaching Minder through its Traefik hostname with a real
            domain + TLS.
          </p>
        </>
      )}
    </div>
  );
}
