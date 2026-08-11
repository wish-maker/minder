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
    const match = window.location.hash.match(/token=([^&]+)/);
    if (match) {
      loginWithToken(decodeURIComponent(match[1]));
    }
    navigate("/", { replace: true });
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
