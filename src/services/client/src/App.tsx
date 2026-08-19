import { useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { Sidebar } from "./components/Sidebar";
import { ThemeToggle } from "./components/ThemeToggle";
import { UserMenu } from "./components/UserMenu";
import { AuthProvider } from "./lib/auth";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { AvailableBundlesPage } from "./pages/AvailableBundlesPage";
import { AvailablePluginsPage } from "./pages/AvailablePluginsPage";
import { AvailableToolsPage } from "./pages/AvailableToolsPage";
import { BackupsPage } from "./pages/BackupsPage";
import { GraphExplorerPage } from "./pages/GraphExplorerPage";
import { HomePage } from "./pages/HomePage";
import { InstalledBundlesPage } from "./pages/InstalledBundlesPage";
import { InstalledPluginsPage } from "./pages/InstalledPluginsPage";
import { InstalledToolsPage } from "./pages/InstalledToolsPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelManagementPage } from "./pages/ModelManagementPage";
import { RagPipelinesPage } from "./pages/RagPipelinesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatusPage } from "./pages/StatusPage";
import { VoicePage } from "./pages/VoicePage";

export function App() {
  // Mobile-only: the sidebar is always visible on lg+ (Sidebar.tsx's own
  // lg:translate-x-0 lg:static), this only controls the slide-in overlay
  // below that breakpoint.
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Re-key the ErrorBoundary per route so navigating to another page clears a
  // previous page's crash instead of staying stuck on the fallback.
  const location = useLocation();

  return (
    <AuthProvider>
      <div className="flex min-h-screen bg-white dark:bg-gray-950">
        <Sidebar open={sidebarOpen} onNavigate={() => setSidebarOpen(false)} />
        {sidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/30 lg:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}
        <div className="flex min-h-screen flex-1 flex-col">
          <header className="flex items-center gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-800">
            <button
              type="button"
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded-md p-1.5 text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 lg:hidden"
              aria-label="Toggle navigation"
            >
              ☰
            </button>
            <div className="ml-auto flex items-center gap-2">
              <ThemeToggle />
              <UserMenu />
            </div>
          </header>
          <main className="mx-auto w-full max-w-4xl flex-1 p-6">
            <ErrorBoundary key={location.pathname}>
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/login" element={<LoginPage />} />
                <Route path="/auth/callback" element={<AuthCallbackPage />} />
                <Route path="/settings" element={<SettingsPage />} />

                <Route path="/rag" element={<KnowledgeBasesPage />} />
                <Route path="/rag/pipelines" element={<RagPipelinesPage />} />
                <Route path="/rag/graph" element={<GraphExplorerPage />} />

                <Route
                  path="/plugins"
                  element={<Navigate to="/plugins/available" replace />}
                />
                <Route
                  path="/plugins/available"
                  element={<AvailablePluginsPage />}
                />
                <Route
                  path="/plugins/installed"
                  element={<InstalledPluginsPage />}
                />

                <Route
                  path="/ai-tools"
                  element={<Navigate to="/ai-tools/available" replace />}
                />
                <Route
                  path="/ai-tools/available"
                  element={<AvailableToolsPage />}
                />
                <Route
                  path="/ai-tools/installed"
                  element={<InstalledToolsPage />}
                />

                <Route
                  path="/bundles"
                  element={<Navigate to="/bundles/available" replace />}
                />
                <Route
                  path="/bundles/available"
                  element={<AvailableBundlesPage />}
                />
                <Route
                  path="/bundles/installed"
                  element={<InstalledBundlesPage />}
                />

                <Route path="/platform" element={<ModelManagementPage />} />
                <Route path="/platform/status" element={<StatusPage />} />
                <Route path="/platform/voice" element={<VoicePage />} />
                <Route path="/platform/backups" element={<BackupsPage />} />

                {/* Old flat/pre-restructure routes, kept as redirects so existing
                  bookmarks/links still land somewhere sensible instead of the
                  catch-all. */}
                <Route
                  path="/knowledge-bases"
                  element={<Navigate to="/rag" replace />}
                />
                <Route
                  path="/rag-pipelines"
                  element={<Navigate to="/rag/pipelines" replace />}
                />
                <Route
                  path="/plugin-config"
                  element={<Navigate to="/plugins/installed" replace />}
                />
                <Route
                  path="/marketplace"
                  element={<Navigate to="/plugins/available" replace />}
                />
                <Route
                  path="/marketplace/plugins"
                  element={<Navigate to="/plugins/available" replace />}
                />
                <Route
                  path="/marketplace/plugins/available"
                  element={<Navigate to="/plugins/available" replace />}
                />
                <Route
                  path="/marketplace/plugins/installed"
                  element={<Navigate to="/plugins/installed" replace />}
                />
                <Route
                  path="/marketplace/plugins/ai-tools"
                  element={<Navigate to="/ai-tools/available" replace />}
                />
                <Route
                  path="/marketplace/bundles"
                  element={<Navigate to="/bundles/available" replace />}
                />
                <Route
                  path="/platform/bundles"
                  element={<Navigate to="/bundles/available" replace />}
                />
                <Route
                  path="/plugins/ai-tools"
                  element={<Navigate to="/ai-tools/available" replace />}
                />
                <Route
                  path="/plugins/config"
                  element={<Navigate to="/plugins/installed" replace />}
                />

                {/* Unmatched paths (including the removed /model-management, still
                  served 200 by nginx's SPA fallback since it can't tell client-side
                  routes apart) redirect home instead of rendering a blank page. */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </AuthProvider>
  );
}
