import { Link, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./lib/auth";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { LandingPage } from "./pages/LandingPage";
import { PluginConfigPage } from "./pages/PluginConfigPage";
import { RagPipelinesPage } from "./pages/RagPipelinesPage";

export function App() {
  return (
    <AuthProvider>
      <nav className="mb-6 flex flex-wrap gap-x-5 gap-y-1 border-b border-gray-200 pb-3 text-sm font-medium text-gray-700 dark:border-gray-700 dark:text-gray-300">
        <Link className="hover:text-indigo-600 dark:hover:text-indigo-400" to="/">
          Minder
        </Link>
        <Link
          className="hover:text-indigo-600 dark:hover:text-indigo-400"
          to="/plugin-config"
        >
          Plugin Config
        </Link>
        <Link
          className="hover:text-indigo-600 dark:hover:text-indigo-400"
          to="/knowledge-bases"
        >
          Knowledge Bases
        </Link>
        <Link
          className="hover:text-indigo-600 dark:hover:text-indigo-400"
          to="/rag-pipelines"
        >
          RAG Pipelines
        </Link>
      </nav>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/plugin-config" element={<PluginConfigPage />} />
        <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
        <Route path="/rag-pipelines" element={<RagPipelinesPage />} />
        {/* Unmatched paths (including the removed /model-management, still
            served 200 by nginx's SPA fallback since it can't tell client-side
            routes apart) redirect home instead of rendering a blank page. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
