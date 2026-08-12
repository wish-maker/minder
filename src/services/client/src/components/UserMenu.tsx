import { Link } from "react-router-dom";

import { useAuth } from "../lib/auth";
import { secondaryButtonClass } from "../lib/ui";

/** The platform's one login control. Routes to the /login page, which offers
 * local username/password auth (works over a direct localhost / LAN-IP address)
 * AND an SSO button for Traefik-fronted deployments. Previously this was a bare
 * link straight into the OIDC flow, which dead-ends over localhost since SSO
 * needs the `*.minder.local` Traefik hostnames (real DNS + TLS). */
export function UserMenu() {
  const { isAuthenticated, username, logout } = useAuth();

  if (!isAuthenticated) {
    return (
      <Link
        to="/login"
        className="rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white hover:bg-indigo-700"
      >
        Log in
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <Link
        to="/settings"
        className="text-sm text-gray-600 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-indigo-400"
      >
        <span aria-hidden="true">👤</span> {username}
      </Link>
      <button type="button" onClick={logout} className={secondaryButtonClass}>
        Log out
      </button>
    </div>
  );
}
