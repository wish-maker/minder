import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { Sidebar } from "./components/Sidebar";
import { UserMenu } from "./components/UserMenu";
import { AuthProvider } from "./lib/auth";
import { AiToolsPage } from "./pages/AiToolsPage";
import { AuthCallbackPage } from "./pages/AuthCallbackPage";
import { AvailablePluginsPage } from "./pages/AvailablePluginsPage";
import { BundleManagementPage } from "./pages/BundleManagementPage";
import { GraphExplorerPage } from "./pages/GraphExplorerPage";
import { InstalledPluginsPage } from "./pages/InstalledPluginsPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { LandingPage } from "./pages/LandingPage";
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
            <div className="ml-auto">
              <UserMenu />
            </div>
          </header>
          <main className="mx-auto w-full max-w-4xl flex-1 p-6">
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/auth/callback" element={<AuthCallbackPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              <Route path="/rag" element={<KnowledgeBasesPage />} />
              <Route path="/rag/pipelines" element={<RagPipelinesPage />} />
              <Route path="/rag/graph" element={<GraphExplorerPage />} />

              {/* Plugins and Bundles are both "things you turn on for this
                  installation" -- grouping them under one Marketplace
                  section (sidebar-level now, not a page-level tab) keeps
                  that relationship visible instead of accidental. */}
              <Route
                path="/marketplace"
                element={<Navigate to="/marketplace/plugins/available" replace />}
              />
              <Route
                path="/marketplace/plugins"
                element={<Navigate to="/marketplace/plugins/available" replace />}
              />
              <Route
                path="/marketplace/plugins/available"
                element={<AvailablePluginsPage />}
              />
              <Route
                path="/marketplace/plugins/installed"
                element={<InstalledPluginsPage />}
              />
              <Route
                path="/marketplace/plugins/ai-tools"
                element={<AiToolsPage />}
              />
              <Route path="/marketplace/bundles" element={<BundleManagementPage />} />

              <Route path="/platform" element={<ModelManagementPage />} />
              <Route path="/platform/status" element={<StatusPage />} />
              <Route path="/platform/voice" element={<VoicePage />} />

              {/* Old flat/pre-restructure routes, kept as redirects so existing
                  bookmarks/links still land somewhere sensible instead of the
                  catch-all. */}
              <Route path="/knowledge-bases" element={<Navigate to="/rag" replace />} />
              <Route
                path="/rag-pipelines"
                element={<Navigate to="/rag/pipelines" replace />}
              />
              <Route
                path="/plugins"
                element={<Navigate to="/marketplace/plugins/available" replace />}
              />
              <Route
                path="/plugins/config"
                element={<Navigate to="/marketplace/plugins/installed" replace />}
              />
              <Route
                path="/plugins/ai-tools"
                element={<Navigate to="/marketplace/plugins/ai-tools" replace />}
              />
              <Route
                path="/plugin-config"
                element={<Navigate to="/marketplace/plugins/installed" replace />}
              />
              <Route
                path="/platform/bundles"
                element={<Navigate to="/marketplace/bundles" replace />}
              />

              {/* Unmatched paths (including the removed /model-management, still
                  served 200 by nginx's SPA fallback since it can't tell client-side
                  routes apart) redirect home instead of rendering a blank page. */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </div>
    </AuthProvider>
  );
}
