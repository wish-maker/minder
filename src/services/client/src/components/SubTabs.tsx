import { NavLink, Outlet } from "react-router-dom";

interface Tab {
  to: string;
  label: string;
  end?: boolean;
}

/** A second-level tab strip nested inside a SectionTabs page (e.g. Marketplace
 * > Plugins > {Available, Installed, AI Tools}) -- pill-style and visually
 * lighter than the top-level underline tabs, so the hierarchy reads as "one
 * level deeper" rather than a second identical nav bar. No heading of its
 * own -- the parent SectionTabs already renders one. */
export function SubTabs({ tabs }: { tabs: Tab[] }) {
  return (
    <>
      <div className="mb-4 flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `rounded-full px-3 py-1 text-sm font-medium ${
                isActive
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
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
