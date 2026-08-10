import { useCallback, useRef, useState } from "react";

import { destructiveButtonClass, primaryButtonClass, secondaryButtonClass } from "../lib/ui";

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  /** Filled red confirm button for hard-to-undo actions (delete/uninstall),
   * distinct in weight from routine confirmations (disable/reconcile). */
  danger?: boolean;
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (value: boolean) => void;
}

/** Imperative confirm-dialog replacement for `window.confirm()` — a branded
 * modal instead of the browser's native dialog, with distinct visual weight
 * for destructive vs. routine actions. Usage:
 *
 *   const { confirm, dialog } = useConfirm();
 *   async function handleDelete() {
 *     if (!(await confirm({ title: "...", message: "...", danger: true }))) return;
 *     ...
 *   }
 *   return <>{dialog}...</>
 */
export function useConfirm() {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setPending({ ...options, resolve });
    });
  }, []);

  function settle(result: boolean) {
    pending?.resolve(result);
    setPending(null);
  }

  /** Keep Tab/Shift+Tab cycling within the dialog's two buttons instead of
   * escaping to the page behind it -- autoFocus alone only sets the INITIAL
   * focus, it doesn't constrain where Tab can go afterwards. */
  function handleTabTrap(e: React.KeyboardEvent) {
    if (e.key !== "Tab" || !panelRef.current) return;
    const focusable = panelRef.current.querySelectorAll<HTMLElement>("button");
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  const dialog = pending && (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={() => settle(false)}
      onKeyDown={(e) => {
        if (e.key === "Escape") settle(false);
        else handleTabTrap(e);
      }}
    >
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl dark:bg-gray-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="text-base font-semibold text-gray-900 dark:text-gray-100"
        >
          {pending.title}
        </h2>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">{pending.message}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => settle(false)}
          >
            Cancel
          </button>
          <button
            type="button"
            autoFocus
            className={pending.danger ? destructiveButtonClass : primaryButtonClass}
            onClick={() => settle(true)}
          >
            {pending.confirmLabel ?? (pending.danger ? "Delete" : "Confirm")}
          </button>
        </div>
      </div>
    </div>
  );

  return { confirm, dialog };
}
