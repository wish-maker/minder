import { Link, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./lib/auth";
import { LandingPage } from "./pages/LandingPage";
import { PluginConfigPage } from "./pages/PluginConfigPage";

export function App() {
  return (
    <AuthProvider>
      <nav className="top-nav">
        <Link to="/">Minder</Link>
        <Link to="/plugin-config">Plugin Config</Link>
      </nav>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/plugin-config" element={<PluginConfigPage />} />
      </Routes>
    </AuthProvider>
  );
}
