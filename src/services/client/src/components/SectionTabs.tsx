import { NavLink, Outlet } from "react-router-dom";

interface Tab {
  to: string;
  label: string;
  end?: boolean;
}

/** Shared layout for a top-level nav section that groups a few related pages
 * as tabs (RAG, Plugins, Platform) -- the section owns the page title/icon;
 * each tab's own page component keeps its descriptive paragraph but drops
 * its old top-level heading to avoid a doubled title. */
export function SectionTabs({
  title,
  icon,
  tabs,
}: {
  title: string;
  icon: string;
  tabs: Tab[];
}) {
  return (
    <>
      <h1 className="mb-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">{icon}</span> {title}
      </h1>
      <div className="mb-6 flex gap-5 overflow-x-auto border-b border-gray-200 dark:border-gray-700">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `flex-shrink-0 whitespace-nowrap border-b-2 pb-2 text-sm font-medium ${
                isActive
                  ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>
      <Outlet />
    </>
  );
}
