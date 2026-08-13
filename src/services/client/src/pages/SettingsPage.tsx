import { Navigate } from "react-router-dom";

import { autheliaPortalUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import { badgeClass, cardClass, secondaryButtonClass } from "../lib/ui";

/** A real settings page was one of the concrete gaps in "this needs to feel
 * like a platform" -- account identity had nowhere to live before this.
 * Everything shown comes straight from the current JWT's own claims (no
 * new endpoint needed for a first version): editing account details is a
 * job for Authelia's own portal (the actual identity source for SSO
 * logins), not something Minder should grow a duplicate UI for. */
export function SettingsPage() {
  const { isAuthenticated, username, email, role, logout } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <>
      <h1 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Settings
      </h1>
      <p className="mb-6 text-sm text-gray-600 dark:text-gray-400">
        Your account, as Minder currently sees it.
      </p>

      <section className={`mb-6 ${cardClass}`}>
        <h2 className="mb-3 text-base font-semibold text-gray-900 dark:text-gray-100">
          Account
        </h2>
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex items-center gap-2">
            <dt className="w-24 text-gray-500 dark:text-gray-400">Username</dt>
            <dd className="font-medium text-gray-900 dark:text-gray-100">
              {username}
            </dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="w-24 text-gray-500 dark:text-gray-400">Email</dt>
            <dd className="text-gray-900 dark:text-gray-100">{email}</dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="w-24 text-gray-500 dark:text-gray-400">Role</dt>
            <dd>
              <span className={badgeClass}>{role}</span>
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-gray-500 dark:text-gray-400">
          Signed in via Authelia SSO or a local Minder account. To change
          your password, display name, or group membership, use{" "}
          {autheliaPortalUrl ? (
            <a
              href={autheliaPortalUrl}
              className="underline hover:text-indigo-600 dark:hover:text-indigo-400"
            >
              Authelia's own portal
            </a>
          ) : (
            "your identity provider's portal (Authelia)"
          )}{" "}
          — that's the actual identity source for SSO logins, not this page.
        </p>
      </section>

      <button type="button" onClick={logout} className={secondaryButtonClass}>
        Log out
      </button>
    </>
  );
}
