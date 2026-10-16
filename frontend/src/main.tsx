import "@fontsource-variable/inter";
import "./styles/tokens.css";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { ToastProvider } from "./components/Toast";
import { applyTheme, storedTheme } from "./lib/theme";

applyTheme(storedTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
);
