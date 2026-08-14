import { Link, NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
  dividerBefore?: boolean;
}

interface NavSection {
  icon: string;
  label: string;
  items: NavItem[];
}

const SECTIONS: NavSection[] = [
  {
    icon: "🔎",
    label: "RAG",
    items: [
      { to: "/rag", label: "Knowledge Bases", end: true },
      { to: "/rag/pipelines", label: "Pipelines" },
      { to: "/rag/graph", label: "Graph" },
    ],
  },
  {
    icon: "🧩",
    label: "Plugins",
    items: [
      { to: "/plugins/available", label: "Available Plugins" },
      { to: "/plugins/installed", label: "Installed Plugins" },
    ],
  },
  {
    icon: "🧰",
    label: "AI Tools",
    items: [
      { to: "/ai-tools/available", label: "Available Tools" },
      { to: "/ai-tools/installed", label: "Installed Tools" },
    ],
  },
  {
    icon: "📦",
    label: "Bundles",
    items: [
      { to: "/bundles/available", label: "Available Bundles" },
      { to: "/bundles/installed", label: "Installed Bundles" },
    ],
  },
  {
    icon: "⚙️",
    label: "Platform",
    items: [
      { to: "/platform", label: "Models", end: true },
      { to: "/platform/status", label: "Status" },
      { to: "/platform/voice", label: "Voice" },
    ],
  },
];

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-1.5 text-sm ${
    isActive
      ? "bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
  }`;

/** The platform's persistent nav -- a single, always-visible tree, following
 * the instrument-panel convention of infra tools like Grafana rather than a
 * chat app's sidebar (OpenWebUI's own layout is chat-history-first, which
 * isn't what Minder's content actually is). Section labels are deliberately
 * not links -- there is no single destination "RAG" itself would mean beyond
 * its first child, so making it clickable would just be a confusing synonym
 * for that child.
 *
 * Plugins / AI Tools / Bundles were previously flattened into one
 * "Marketplace" section; split into their own top-level sections since each
 * has grown its own real Available/Installed distinction rather than being
 * one flat "things you turn on" list. */
export function Sidebar({
  open,
  onNavigate,
}: {
  open: boolean;
  onNavigate: () => void;
}) {
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-60 flex-shrink-0 transform overflow-y-auto border-r border-gray-200 bg-white p-4 transition-transform duration-200 dark:border-gray-800 dark:bg-gray-950 lg:static lg:translate-x-0 ${
        open ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <Link
        to="/"
        onClick={onNavigate}
        className="mb-6 block text-lg font-bold text-gray-900 dark:text-gray-100"
      >
        Minder
      </Link>
      <nav className="flex flex-col gap-5">
        {SECTIONS.map((section) => (
          <div key={section.label}>
            <p className="mb-1.5 flex items-center gap-1.5 px-3 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
              <span aria-hidden="true">{section.icon}</span> {section.label}
            </p>
            <div className="flex flex-col gap-0.5">
              {section.items.map((item) => (
                <div key={item.to}>
                  {item.dividerBefore && (
                    <div className="my-1.5 border-t border-gray-100 dark:border-gray-800" />
                  )}
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={onNavigate}
                    className={linkClass}
                  >
                    {item.label}
                  </NavLink>
                </div>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
