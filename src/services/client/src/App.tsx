import { Link, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./lib/auth";
import { KnowledgeBasesPage } from "./pages/KnowledgeBasesPage";
import { LandingPage } from "./pages/LandingPage";
import { PluginConfigPage } from "./pages/PluginConfigPage";
import { RagPipelinesPage } from "./pages/RagPipelinesPage";

export function App() {
  return (
    <AuthProvider>
      <nav className="top-nav">
        <Link to="/">Minder</Link>
        <Link to="/plugin-config">Plugin Config</Link>
        <Link to="/knowledge-bases">Knowledge Bases</Link>
        <Link to="/rag-pipelines">RAG Pipelines</Link>
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
