import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

/** Lands here once, right after api-gateway's /v1/auth/oidc/callback
 * redirects the browser back with a Minder JWT in the URL fragment (never
 * a query param -- browsers never send a fragment back to any server, so
 * the token never lands in an access log). Reads it, stores it via the
 * same auth context every other login path uses, then leaves immediately;
 * this route has no UI of its own worth lingering on. */
export function AuthCallbackPage() {
  const { loginWithToken } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const hash = window.location.hash;
    const tokenMatch = hash.match(/token=([^&]+)/);
    if (tokenMatch) {
      loginWithToken(decodeURIComponent(tokenMatch[1]));
      navigate("/", { replace: true });
      return;
    }
    // A real OIDC failure (denied consent, expired auth code, misconfigured
    // client, ...) redirects back with `#error=...&error_description=...`
    // instead of a token -- this used to fall straight through to
    // navigate("/") with zero indication anything went wrong. Surface it on
    // the login page instead of silently landing logged-out.
    const errorMatch =
      hash.match(/error_description=([^&]+)/) || hash.match(/error=([^&]+)/);
    const message = errorMatch
      ? decodeURIComponent(errorMatch[1].replace(/\+/g, " "))
      : "Sign-in did not complete — please try again.";
    navigate("/login", { replace: true, state: { oidcError: message } });
    // Runs once on mount -- loginWithToken/navigate are stable (useCallback/
    // react-router), and re-running this on their identity would re-read a
    // hash that's already been consumed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <p className="text-sm text-gray-500 dark:text-gray-400">
      Completing sign-in…
    </p>
  );
}
