import { Link, Navigate, Route, Routes } from "react-router-dom";

import { SectionTabs } from "./components/SectionTabs";
import { AuthProvider } from "./lib/auth";
import { AiToolsPage } from "./pages/AiToolsPage";
import { BundleManagementPage } from "./pages/BundleManagementPage";
import { GraphExplorerPage } from "./pages/GraphExplorerPage";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { LandingPage } from "./pages/LandingPage";
import { MarketplacePage } from "./pages/MarketplacePage";
import { ModelManagementPage } from "./pages/ModelManagementPage";
import { PluginConfigPage } from "./pages/PluginConfigPage";
import { RagPipelinesPage } from "./pages/RagPipelinesPage";
import { StatusPage } from "./pages/StatusPage";
import { VoicePage } from "./pages/VoicePage";

export function App() {
  return (
    <AuthProvider>
      <nav className="mb-6 flex flex-wrap gap-x-5 gap-y-1 border-b border-gray-200 pb-3 text-sm font-medium text-gray-700 dark:border-gray-700 dark:text-gray-300">
        <Link className="hover:text-indigo-600 dark:hover:text-indigo-400" to="/">
          Minder
        </Link>
        <Link className="hover:text-indigo-600 dark:hover:text-indigo-400" to="/rag">
          RAG
        </Link>
        <Link
          className="hover:text-indigo-600 dark:hover:text-indigo-400"
          to="/plugins"
        >
          Plugins
        </Link>
        <Link
          className="hover:text-indigo-600 dark:hover:text-indigo-400"
          to="/platform"
        >
          Platform
        </Link>
      </nav>
      <Routes>
        <Route path="/" element={<LandingPage />} />

        <Route
          path="/rag"
          element={
            <SectionTabs
              title="RAG"
              icon="🔎"
              tabs={[
                { to: ".", label: "Knowledge Bases", end: true },
                { to: "pipelines", label: "Pipelines" },
                { to: "graph", label: "Graph" },
              ]}
            />
          }
        >
          <Route index element={<KnowledgeBasesPage />} />
          <Route path="pipelines" element={<RagPipelinesPage />} />
          <Route path="graph" element={<GraphExplorerPage />} />
        </Route>

        <Route
          path="/plugins"
          element={
            <SectionTabs
              title="Plugins"
              icon="🧩"
              tabs={[
                { to: ".", label: "Marketplace", end: true },
                { to: "config", label: "Configure" },
                { to: "ai-tools", label: "AI Tools" },
              ]}
            />
          }
        >
          <Route index element={<MarketplacePage />} />
          <Route path="config" element={<PluginConfigPage />} />
          <Route path="ai-tools" element={<AiToolsPage />} />
        </Route>

        <Route
          path="/platform"
          element={
            <SectionTabs
              title="Platform"
              icon="⚙️"
              tabs={[
                { to: ".", label: "Models", end: true },
                { to: "bundles", label: "Bundles" },
                { to: "status", label: "Status" },
                { to: "voice", label: "Voice" },
              ]}
            />
          }
        >
          <Route index element={<ModelManagementPage />} />
          <Route path="bundles" element={<BundleManagementPage />} />
          <Route path="status" element={<StatusPage />} />
          <Route path="voice" element={<VoicePage />} />
        </Route>

        {/* Old flat routes, kept as redirects so existing bookmarks/links
            still land somewhere sensible instead of the catch-all. */}
        <Route path="/knowledge-bases" element={<Navigate to="/rag" replace />} />
        <Route
          path="/rag-pipelines"
          element={<Navigate to="/rag/pipelines" replace />}
        />
        <Route path="/marketplace" element={<Navigate to="/plugins" replace />} />
        <Route
          path="/plugin-config"
          element={<Navigate to="/plugins/config" replace />}
        />

        {/* Unmatched paths (including the removed /model-management, still
            served 200 by nginx's SPA fallback since it can't tell client-side
            routes apart) redirect home instead of rendering a blank page. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
