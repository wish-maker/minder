import { useState } from "react";

import {
  type Bundle,
  type BundleService,
  type DisableResponse,
  type EnableResponse,
  otherClaimants,
  outcomeSummary,
} from "../lib/bundles";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { badgeClass, cardClass, primaryButtonClass, secondaryButtonClass } from "../lib/ui";
import { useConfirm } from "./ConfirmDialog";

function ServiceRow({
  service,
  bundleName,
}: {
  service: BundleService;
  bundleName: string;
}) {
  const others = otherClaimants(service, bundleName);
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-gray-600 dark:text-gray-400">
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          service.active ? "bg-green-500" : "bg-gray-300 dark:bg-gray-600"
        }`}
        aria-hidden="true"
      />
      {service.name}
      {service.image && (
        <code className="rounded bg-gray-100 px-1 py-0.5 text-[11px] text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          {service.image}
        </code>
      )}
      {!service.image && (
        <span className="text-gray-500 dark:text-gray-400" title="Built locally, no pulled image">
          (custom build)
        </span>
      )}
      {others.length > 0 && (
        <span className="text-gray-500 dark:text-gray-400">
          (also claimed by: {others.join(", ")} — disabling this bundle won't stop it)
        </span>
      )}
    </li>
  );
}

/** Enable/disable card shared by both Available Bundles (shows disabled
 * bundles, "Enable" action) and Installed Bundles (shows enabled bundles,
 * "Disable" action) -- the toggle logic already adapts to bundle.enabled, so
 * one component serves both pages; only which bundles get passed in differs. */
export function BundleCard({
  bundle,
  token,
  isAdmin,
  onChanged,
}: {
  bundle: Bundle;
  token: string;
  isAdmin: boolean;
  onChanged: () => void;
}) {
  const { confirm, dialog } = useConfirm();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleToggle() {
    if (bundle.enabled) {
      // Disabling is the one direction that can silently do less than it
      // looks like -- a service kept alive by another enabled bundle stays
      // running even though THIS bundle now shows "disabled". Say that up
      // front instead of only in the small print next to each service.
      const willStop = bundle.services.filter(
        (s) => otherClaimants(s, bundle.name).length === 0,
      );
      const willStay = bundle.services.filter(
        (s) => otherClaimants(s, bundle.name).length > 0,
      );
      const lines = [
        willStop.length > 0
          ? `Will stop: ${willStop.map((s) => s.name).join(", ")}.`
          : "No services will actually stop -- every one is still claimed by another enabled bundle.",
        willStay.length > 0
          ? `Will keep running (claimed by another enabled bundle too): ${willStay
              .map((s) => `${s.name} (${otherClaimants(s, bundle.name).join(", ")})`)
              .join(", ")}.`
          : "",
      ].filter(Boolean);
      const ok = await confirm({
        title: `Disable "${bundle.name}"?`,
        message: lines.join(" "),
        confirmLabel: "Disable",
        danger: willStop.length > 0,
      });
      if (!ok) return;
    }
    setBusy(true);
    setStatus(bundle.enabled ? "Disabling…" : "Enabling…");
    try {
      const res = await apiFetch<EnableResponse | DisableResponse>(
        `/v1/bundles/${encodeURIComponent(bundle.name)}/${bundle.enabled ? "disable" : "enable"}`,
        { method: "POST", token },
      );
      setStatus(outcomeSummary(res));
      onChanged();
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      {dialog}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">📦</span> {bundle.name}
            {bundle.core && <span className={badgeClass}>core</span>}
            <span
              className={
                bundle.enabled
                  ? "inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-950 dark:text-green-300"
                  : "inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300"
              }
            >
              {bundle.enabled ? "enabled" : "disabled"}
            </span>
          </h2>
          <ul className="mt-2 flex flex-col gap-1">
            {bundle.services.map((s) => (
              <ServiceRow key={s.name} service={s} bundleName={bundle.name} />
            ))}
          </ul>
        </div>
        {bundle.core ? (
          // A disabled "Disable" button only explained the always-on kernel via
          // a hover title -- invisible on touch and easy to miss even with a
          // mouse. Say it in visible text instead of hiding the reason.
          <span
            className="whitespace-nowrap text-xs text-gray-500 dark:text-gray-400"
            title="core is the always-on kernel — it can't be disabled"
          >
            🔒 Always on
          </span>
        ) : (
          <button
            onClick={handleToggle}
            disabled={!isAdmin || busy}
            title={
              !isAdmin
                ? token
                  ? "Admin role required"
                  : "Log in as an admin to enable or disable bundles"
                : undefined
            }
            className={bundle.enabled ? secondaryButtonClass : primaryButtonClass}
          >
            {bundle.enabled ? "Disable" : "Enable"}
          </button>
        )}
      </div>
      {status && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
    </section>
  );
}
