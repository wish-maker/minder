import { Link } from "react-router-dom";

import { oidcLoginUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import { secondaryButtonClass } from "../lib/ui";

/** The platform's one login control (#<issue>) -- lives once, in the top
 * nav, instead of a LoginPanel form repeated on every page that needed
 * auth. "Log in" is a full-page navigation (not a fetch/click-handler)
 * into Authelia's real hosted login page; the client never collects a
 * password itself for this path. */
export function UserMenu() {
  const { isAuthenticated, username, logout } = useAuth();

  if (!isAuthenticated) {
    return (
      <a
        href={oidcLoginUrl}
        className="rounded-md bg-indigo-600 px-3 py-1 text-sm font-medium text-white hover:bg-indigo-700"
      >
        Log in
      </a>
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
