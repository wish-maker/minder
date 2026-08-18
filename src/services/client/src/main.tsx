import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import "./index.css";
import { initTheme } from "./lib/theme";

// index.html's inline script already applied the right class before first
// paint (see its comment); this call adds the "system" live-update listener
// for the rest of the tab's lifetime, which a one-shot inline script can't.
initTheme();

const container = document.getElementById("root");
if (!container) throw new Error("root element not found");

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
