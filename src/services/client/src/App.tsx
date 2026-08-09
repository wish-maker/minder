import { Link, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./lib/auth";
import { LandingPage } from "./pages/LandingPage";
import { ModelManagementPage } from "./pages/ModelManagementPage";
import { PluginConfigPage } from "./pages/PluginConfigPage";

export function App() {
  return (
    <AuthProvider>
      <nav className="top-nav">
        <Link to="/">Minder</Link>
        <Link to="/plugin-config">Plugin Config</Link>
        <Link to="/model-management">Model Management</Link>
      </nav>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/plugin-config" element={<PluginConfigPage />} />
        <Route path="/model-management" element={<ModelManagementPage />} />
      </Routes>
    </AuthProvider>
  );
}
